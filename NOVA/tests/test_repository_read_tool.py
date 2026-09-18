import asyncio
import hashlib
import os

import pytest

from services.tools.repository_read_tool import MAX_BYTES, RepositoryReadTool
from services.tools.base import ToolResult
from services.agent_runtime.broker import ToolBroker
from services.agent_runtime.events.audit import AuditLog
from services.agent_runtime.ledger import EvidenceLedger
from services.agent_runtime.registry import AgentRegistry
from services.agent_runtime.manager import AgentManager
from test_agent_runtime_phase1 import FakeLLM, WebSearchTool, _ToolRegistry, offline_gate


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "nova-desktop"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src" / "App.tsx").write_text("export const title = 'NOVA';\n")
    return root, RepositoryReadTool(root)


def test_reads_exact_file_with_digest_without_writes(repository):
    root, tool = repository
    before = (root / "src/App.tsx").read_bytes()
    result = asyncio.run(tool.invoke(path="src/App.tsx"))
    assert result.ok
    assert result.data == {"file": {"path": "src/App.tsx", "text": before.decode(),
                                    "sha256": hashlib.sha256(before).hexdigest(), "bytes": len(before)}}
    assert (root / "src/App.tsx").read_bytes() == before
    assert not tool.can_handle("read my project")
    assert not tool.execute("read src/App.tsx")["success"]


@pytest.mark.parametrize("path", ["../other.ts", "/etc/passwd", "src/../App.tsx", "src//App.tsx",
    "src/./App.tsx", "src\\App.tsx", ".env", ".git/config.json", "node_modules/lib/index.js",
    "configs/development.json", "src/credentials.json", "src/private-key.json", "data/profile.json",
    "src/image.png", "src/\x00.ts", "src/\n.ts", "", "a" * 241])
def test_denies_unapproved_paths(repository, path):
    _, tool = repository
    result = asyncio.run(tool.invoke(path=path))
    assert not result.ok
    assert result.error == "REPOSITORY_PATH_DENIED"
    assert not result.data


@pytest.mark.parametrize("link_kind", ["file", "directory", "hardlink"])
def test_denies_links_outside_root(repository, tmp_path, link_kind):
    root, tool = repository
    outside = tmp_path / "outside"
    outside.mkdir()
    source = outside / "outside.ts"
    source.write_text("private repository content")
    if link_kind == "directory":
        (root / "linked").symlink_to(outside, target_is_directory=True)
        path = "linked/outside.ts"
    elif link_kind == "hardlink":
        os.link(source, root / "linked.ts")
        path = "linked.ts"
    else:
        (root / "linked.ts").symlink_to(source)
        path = "linked.ts"
    result = asyncio.run(tool.invoke(path=path))
    assert not result.ok
    assert not result.data


@pytest.mark.parametrize("content", [b"a" * (MAX_BYTES + 1), b"binary\x00data", b"\xff\xfe",
    b'const password = "fixture-only";', b'{"api_key": "fixture-only"}',
    b"-----BEGIN PRIVATE KEY-----\nfixture-only\n-----END PRIVATE KEY-----"],
    ids=["oversized", "nul", "invalid-utf8", "password", "api-key", "private-key"])
def test_denies_oversized_binary_and_sensitive_content(repository, content):
    root, tool = repository
    (root / "src/unsafe.ts").write_bytes(content)
    result = asyncio.run(tool.invoke(path="src/unsafe.ts"))
    assert not result.ok
    assert not result.data
    assert "fixture-only" not in repr(result)


def test_denies_replaced_root(repository):
    root, tool = repository
    root.rename(root.with_name("original"))
    root.mkdir()
    (root / "App.tsx").write_text("replacement")
    result = asyncio.run(tool.invoke(path="App.tsx"))
    assert result.error == "REPOSITORY_ROOT_CHANGED"
    assert not result.data


def test_fifo_does_not_block(repository):
    root, tool = repository
    os.mkfifo(root / "pipe.ts")
    result = asyncio.run(tool.invoke(path="pipe.ts"))
    assert result.error == "REPOSITORY_FILE_DENIED"


def test_missing_file_does_not_leak_host_path(repository):
    root, tool = repository
    result = asyncio.run(tool.invoke(path="missing.ts"))
    assert result.error == "REPOSITORY_READ_DENIED"
    assert str(root) not in repr(result)


def test_broker_mints_file_evidence_and_does_not_audit_source(repository):
    _, tool = repository
    audit, ledger = AuditLog(), EvidenceLedger()
    broker = ToolBroker(registry=None, action_gate=None, audit=audit, ledger=ledger)

    async def scenario():
        result = await tool.invoke(path="src/App.tsx")
        call = await broker._ingest("task_fixture", "repo_reader", "repository_read_tool", result)
        assert call.ok and len(call.evidence_ids) == 1
        assert 'source="repo:src/App.tsx"' in call.untrusted_blocks[0]
        assert 'task="task_fixture"' in call.untrusted_blocks[0]
        assert "export const title" in call.untrusted_blocks[0]
        assert "export const title" not in repr(audit.records)
        assert audit.verify()

    asyncio.run(scenario())


@pytest.mark.parametrize("field,value", [("sha256", "bad"), ("bytes", 999), ("path", "../escape.ts"),
                                        ("text", None)])
def test_broker_rejects_tampered_file_evidence(repository, field, value):
    _, tool = repository
    broker = ToolBroker(registry=None, action_gate=None, audit=AuditLog(), ledger=EvidenceLedger())

    async def scenario():
        result = await tool.invoke(path="src/App.tsx")
        result.data["file"][field] = value
        call = await broker._ingest("task_fixture", "repo_reader", "repository_read_tool", result)
        assert not call.ok
        assert call.reason == "INVALID_FILE_EVIDENCE"
        assert not call.evidence_ids and not call.untrusted_blocks

    asyncio.run(scenario())


def test_broker_does_not_mint_file_evidence_for_failed_reads():
    broker = ToolBroker(registry=None, action_gate=None, audit=AuditLog(), ledger=EvidenceLedger())
    call = asyncio.run(broker._ingest("task_fixture", "repo_reader", "repository_read_tool",
                                     ToolResult(ok=False, data={"file": {}})))
    assert not call.ok and not call.evidence_ids


@pytest.mark.parametrize("mode", ["cite_real", "fabricate"])
def test_repository_agent_uses_broker_and_manager_verifies_citations(repository, offline_gate, mode):
    _, tool = repository
    registry = AgentRegistry(_ToolRegistry([WebSearchTool([]), tool])).load(repository_reader=True)
    audit, ledger, model = AuditLog(), EvidenceLedger(), FakeLLM(mode)
    broker = ToolBroker(registry=registry, action_gate=offline_gate, audit=audit, ledger=ledger)
    manager = AgentManager(registry=registry, broker=broker, audit=audit, ledger=ledger, llm=model)
    result = asyncio.run(manager.run_task("Review file", "Explain this file",
        {"repository": "nova-desktop", "files": ["src/App.tsx"]}, assigned_agent="repo_reader"))
    assert result.status == ("SUCCESS" if mode == "cite_real" else "FAILED")
    if mode == "cite_real":
        assert result.evidence[0].kind == "file_content"
        assert result.evidence[0].ref == "repo:src/App.tsx"
    assert audit.verify()


def test_repository_scope_and_cross_tool_denials(repository, offline_gate):
    from services.agent_runtime.contracts.task import AgentTask, TaskStatus
    from services.agent_runtime.broker import BudgetTracker, TaskContext

    _, tool = repository
    registry = AgentRegistry(_ToolRegistry([WebSearchTool([]), tool])).load(repository_reader=True)
    broker = ToolBroker(registry=registry, action_gate=offline_gate, audit=AuditLog(), ledger=EvidenceLedger())
    task = AgentTask(description="Review", objective="Review", assigned_agent="repo_reader",
        required_capabilities=["repo.read"], risk=registry.get("repo_reader").max_risk,
        budget=registry.get("repo_reader").default_budget,
        inputs={"repository": "nova-desktop", "files": ["src/App.tsx"]})
    task.status = TaskStatus.RUNNING
    broker.register_task(TaskContext(task=task, budget=BudgetTracker(task.budget)))

    async def scenario():
        outside = await broker.invoke("repo_reader", task.id, "repository_read_tool", {"path": "src/Other.tsx"})
        assert outside.reason == "RESOURCE_SCOPE_DENIED"
        for name in ("web_search_tool", "terminal_tool", "filesystem_tool"):
            denied = await broker.invoke("repo_reader", task.id, name, {})
            assert denied.denied
        task.inputs["repository"] = "NOVA"
        denied = await broker.invoke("repo_reader", task.id, "repository_read_tool", {"path": "src/App.tsx"})
        assert denied.reason == "RESOURCE_SCOPE_DENIED"

    asyncio.run(scenario())


def test_repository_service_persists_scoped_report(repository, offline_gate, tmp_path):
    from services.agent_runtime.factory import build_runtime
    from services.agent_runtime.service import RuntimeService
    from services.agent_runtime.reports import ReportStore

    root, _ = repository

    async def scenario():
        owner = RuntimeService()
        owner.manager = build_runtime(tool_registry=_ToolRegistry([WebSearchTool([])]),
            action_gate=offline_gate, llm=FakeLLM(), repository_root=root)
        owner.state = "READY"
        owner.repository_enabled = True
        owner.reports = ReportStore(tmp_path / "reports.sqlite3")
        await owner.reports.open()
        reply = await owner.repository_review("Explain the selected file", ["src/App.tsx"])
        assert reply["action"] == "agent_repository_started"
        stored = await owner.reports.get(reply["data"]["report_id"])
        assert stored["scope"] == {"repository": "nova-desktop", "files": ["src/App.tsx"], "mode": "READ_ONLY"}
        assert (await owner.repository_review("another", ["src/App.tsx"]))["action"] == "agent_busy"
        await asyncio.gather(*tuple(owner.jobs))
        stored = await owner.reports.get(reply["data"]["report_id"])
        assert stored["status"] == "COMPLETED"
        assert stored["sources"][0]["kind"] == "file_content"
        assert stored["sources"][0]["url"] == "repo:src/App.tsx"
        assert stored["findings"]
        assert "export const title" not in repr(stored)
        assert stored["coverage"]["evidence_scope"] == "selected_repository_files"
        await owner.close()

    asyncio.run(scenario())


def test_repository_submission_cancellation_clears_reservation():
    from unittest.mock import AsyncMock
    from services.agent_runtime.service import RuntimeService

    async def scenario():
        owner = RuntimeService()
        owner.state, owner.repository_enabled, owner.manager = "READY", True, object()
        started = asyncio.Event()
        saved = []

        async def save(report):
            saved.append(dict(report))
            if len(saved) == 1:
                started.set()
                await asyncio.Future()

        owner.reports = type("Store", (), {"save": AsyncMock(side_effect=save)})()
        submission = asyncio.create_task(owner.repository_review("Explain routing", ["src/App.tsx"]))
        await started.wait()
        submission.cancel()
        with pytest.raises(asyncio.CancelledError):
            await submission
        assert saved[-1]["status"] == "CANCELLED"
        assert not owner._repository_submitting and not owner.jobs
        owner.reports.save = AsyncMock(side_effect=OSError("private storage detail"))
        reply = await owner.repository_review("Explain routing", ["src/App.tsx"])
        assert reply["action"] == "agent_unavailable"
        assert "private" not in repr(reply) and not owner.jobs

    asyncio.run(scenario())