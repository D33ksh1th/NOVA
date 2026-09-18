import asyncio
import json
import threading
import subprocess
import sys

import pytest

from services.agent_runtime.contracts.event import EventType, Severity
from services.agent_runtime.events.audit import AuditLog
from test_agent_runtime_phase1 import FakeLLM, WebSearchTool, _ToolRegistry, _URL_RESULTS, offline_gate
from test_agent_runtime_graph import node, plan_data
from services.agent_runtime.factory import build_runtime_async
from services.agent_runtime.graph.task_graph import InvocationContext
from services.agent_runtime.planning.plan_validator import PlanRejected, PlanValidator


def test_audit_reopens_and_continues_chain(tmp_path):
    async def scenario():
        path = tmp_path / "audit.jsonl"
        log = await AuditLog.open(path)
        first = await log.append_async(EventType.TASK_CREATED, task_id="t_one", agent="research_agent")
        await log.close()
        reopened = await AuditLog.open(path)
        second = await reopened.append_async(EventType.TASK_COMPLETED, task_id="t_one")
        assert second.seq == 1
        assert second.prev_hash == first.self_hash
        assert await reopened.verify_async()
        await reopened.close()
        report = await AuditLog.check_file(path, expected_head=second.self_hash)
        assert report.valid
        assert report.record_count == 2

    asyncio.run(scenario())


def test_durable_runtime_graph_and_planner_recover(tmp_path, offline_gate):
    async def scenario():
        path = tmp_path / "runtime.jsonl"
        manager = await build_runtime_async(tool_registry=_ToolRegistry([WebSearchTool(_URL_RESULTS)]),
                                            action_gate=offline_gate, llm=FakeLLM(), audit_path=path)
        try:
            validator = PlanValidator(manager._registry, manager._audit)
            with pytest.raises(PlanRejected):
                await validator.validate_async("{", InvocationContext.HUMAN)
            plan = await validator.validate_async(json.dumps(plan_data([node("Scout"), node("Analyst")])),
                                                   InvocationContext.HUMAN)
            result = await manager.run_graph(plan)
            assert result.status == "COMPLETED"
            assert all(item.evidence for item in result.results.values())
            await manager.halt_all("done")
            events = manager._audit.records
            for event_type in (EventType.PLAN_REJECTED, EventType.PLAN_ACCEPTED, EventType.GRAPH_STARTED,
                               EventType.TOOL_INVOKED, EventType.EVIDENCE_RECORDED, EventType.MODEL_USAGE,
                               EventType.TASK_COMPLETED, EventType.GRAPH_COMPLETED, EventType.HALT_ALL):
                assert any(event.type == event_type for event in events)
            head = events[-1].self_hash
        finally:
            await manager.close()
        async with await AuditLog.open(path) as reopened:
            assert reopened.records == events
            assert await reopened.verify_async()
        assert (await AuditLog.check_file(path, expected_head=head)).valid

    asyncio.run(scenario())


def test_single_writer_and_concurrent_appends(tmp_path):
    async def scenario():
        path = tmp_path / "audit.jsonl"
        async with await AuditLog.open(path) as log:
            with pytest.raises(OSError):
                await AuditLog.open(path)
            with pytest.raises(RuntimeError, match="append_async"):
                log.append(EventType.TASK_CREATED)
            await asyncio.gather(*(log.append_async(EventType.TASK_CREATED, data={"index": index})
                                   for index in range(30)))
            assert [record.seq for record in log.records] == list(range(30))
            assert await log.verify_async()
        assert (path.stat().st_mode & 0o777) == 0o600

    asyncio.run(scenario())


def test_partial_record_and_trusted_head_detect_truncation(tmp_path):
    async def scenario():
        path = tmp_path / "audit.jsonl"
        async with await AuditLog.open(path) as log:
            await log.append_async(EventType.TASK_CREATED)
            final = await log.append_async(EventType.TASK_COMPLETED)
        original = path.read_bytes()
        path.write_bytes(original.splitlines(keepends=True)[0])
        assert (await AuditLog.check_file(path)).valid
        assert not (await AuditLog.check_file(path, expected_head=final.self_hash)).valid
        path.write_bytes(original[:-1])
        assert not (await AuditLog.check_file(path)).valid
        with pytest.raises(ValueError, match="malformed"):
            await AuditLog.open(path)
        assert path.read_bytes() == original[:-1]

    asyncio.run(scenario())


def test_public_snapshots_cannot_mutate_chain(tmp_path):
    async def scenario():
        async with await AuditLog.open(tmp_path / "audit.jsonl") as log:
            data = {"nested": {"value": "original"}}
            event = await log.append_async(EventType.TASK_CREATED, data=data)
            data["nested"]["value"] = "input changed"
            event.data["nested"]["value"] = "return changed"
            log.records[0].data["nested"]["value"] = "snapshot changed"
            assert log.records[0].data["nested"]["value"] == "original"
            assert await log.verify_async()

    asyncio.run(scenario())


def test_fsync_failure_blocks_further_writes(tmp_path, monkeypatch):
    async def scenario():
        async with await AuditLog.open(tmp_path / "audit.jsonl") as log:
            def fail_sync(descriptor):
                raise OSError("disk failure")

            monkeypatch.setattr("services.agent_runtime.events.journal.os.fsync", fail_sync)
            with pytest.raises(OSError):
                await log.append_async(EventType.TASK_CREATED)
            assert log.records == []
            assert not await log.verify_async()
            with pytest.raises((OSError, RuntimeError, ValueError)):
                await log.append_async(EventType.TASK_CREATED)

    asyncio.run(scenario())


@pytest.mark.parametrize("stop_at", [EventType.TASK_CREATED, EventType.TOOL_INVOKED])
def test_halt_during_audit_prevents_dispatch_and_close(tmp_path, offline_gate, monkeypatch, stop_at):
    async def scenario():
        tool = WebSearchTool(_URL_RESULTS)
        calls = []
        invoke = tool.invoke

        async def counted_invoke(**args):
            calls.append(args)
            return await invoke(**args)

        monkeypatch.setattr(tool, "invoke", counted_invoke)
        manager = await build_runtime_async(tool_registry=_ToolRegistry([tool]), action_gate=offline_gate,
                                            llm=FakeLLM(), audit_path=tmp_path / "audit.jsonl")
        entered = asyncio.Event()
        release = asyncio.Event()
        append = manager._audit.append_async

        async def paused_append(event_type, **kwargs):
            event = await append(event_type, **kwargs)
            if event_type == stop_at:
                entered.set()
                await release.wait()
            return event

        monkeypatch.setattr(manager._audit, "append_async", paused_append)
        running = asyncio.create_task(manager.run_task("research", "compare"))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            with pytest.raises(RuntimeError, match="active"):
                await manager.close()
            await manager.halt_all("stop")
            release.set()
            result = await asyncio.wait_for(running, 2)
            assert "CANCELLED" in result.errors
            assert calls == []
            assert not manager._running
            assert manager._broker.context(result.task_id) is None
            assert await manager._audit.verify_async()
        finally:
            release.set()
            if not running.done():
                running.cancel()
            await asyncio.gather(running, return_exceptions=True)
            await manager.close()

    asyncio.run(scenario())


def test_audit_failure_prevents_tool_dispatch(tmp_path, offline_gate, monkeypatch):
    async def scenario():
        tool = WebSearchTool(_URL_RESULTS)
        calls = []

        async def unexpected_invoke(**args):
            calls.append(args)
            raise AssertionError("unlogged tool dispatch")

        monkeypatch.setattr(tool, "invoke", unexpected_invoke)
        manager = await build_runtime_async(tool_registry=_ToolRegistry([tool]), action_gate=offline_gate,
                                            llm=FakeLLM(), audit_path=tmp_path / "audit.jsonl")
        write = manager._audit._journal.write

        def fail_tool_record(data):
            if json.loads(data)["type"] == EventType.TOOL_INVOKED:
                manager._audit._journal.failed = True
                raise OSError("disk failure")
            write(data)

        monkeypatch.setattr(manager._audit._journal, "write", fail_tool_record)
        try:
            with pytest.raises(RuntimeError, match="failed"):
                await manager.run_task("research", "compare")
            assert calls == []
            assert not manager._running
            assert not manager._broker._tasks
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_verifier_cli_exit_codes_and_no_modification(tmp_path):
    path = tmp_path / "audit.jsonl"

    async def prepare():
        async with await AuditLog.open(path) as log:
            return await log.append_async(EventType.TASK_CREATED)

    event = asyncio.run(prepare())
    original = path.read_bytes()
    command = [sys.executable, "-m", "services.agent_runtime.events.verify_audit", str(path)]
    valid = subprocess.run(command + ["--expected-head", event.self_hash], capture_output=True, text=True)
    assert valid.returncode == 0
    assert json.loads(valid.stdout)["record_count"] == 1
    invalid = subprocess.run(command + ["--expected-head", "0" * 64], capture_output=True, text=True)
    assert invalid.returncode == 1
    assert not json.loads(invalid.stdout)["valid"]
    assert path.read_bytes() == original


def test_cancelled_commit_finishes_before_next_write(tmp_path, monkeypatch):
    async def scenario():
        async with await AuditLog.open(tmp_path / "audit.jsonl") as log:
            entered = asyncio.Event()
            release = threading.Event()
            loop = asyncio.get_running_loop()
            write = log._journal.write

            def blocked_write(data):
                loop.call_soon_threadsafe(entered.set)
                if not release.wait(5):
                    raise TimeoutError("test did not release journal")
                write(data)

            monkeypatch.setattr(log._journal, "write", blocked_write)
            pending = asyncio.create_task(log.append_async(EventType.TASK_CREATED))
            try:
                await asyncio.wait_for(entered.wait(), 1)
                pending.cancel()
            finally:
                release.set()
            with pytest.raises(asyncio.CancelledError):
                await pending
            event = await log.append_async(EventType.TASK_COMPLETED)
            assert event.seq == 1
            assert await log.verify_async()

    asyncio.run(scenario())


@pytest.mark.parametrize("field,value", [
    ("severity", "HIGH"), ("event_id", "evt_changed"),
    ("ts", "2000-01-01T00:00:00+00:00"), ("agent", "other_agent"),
])
def test_metadata_tampering_is_detected(tmp_path, field, value):
    async def scenario():
        path = tmp_path / "audit.jsonl"
        log = await AuditLog.open(path)
        await log.append_async(EventType.TASK_CREATED)
        await log.close()
        record = json.loads(path.read_text())
        record[field] = value
        path.write_text(json.dumps(record) + "\n")
        report = await AuditLog.check_file(path)
        assert not report.valid
        assert report.break_index == 0
        with pytest.raises(ValueError, match="audit"):
            await AuditLog.open(path)

    asyncio.run(scenario())


def test_secrets_are_removed_before_disk_write(tmp_path):
    async def scenario():
        path = tmp_path / "audit.jsonl"
        log = await AuditLog.open(path)
        await log.append_async(EventType.TOOL_INVOKED, data={
            "api_key": "arbitrary-secret-value",
            "stdout": "-----BEGIN PRIVATE KEY-----\nsecret-body\n-----END PRIVATE KEY-----",
            "Authorization": "Basic encoded-credentials",
            "handle": "cred:gmail_oauth",
        }, severity=Severity.INFO)
        await log.close()
        serialized = path.read_text()
        assert "arbitrary-secret-value" not in serialized
        assert "secret-body" not in serialized
        assert "encoded-credentials" not in serialized
        assert "cred:gmail_oauth" in serialized
        assert (await AuditLog.check_file(path)).valid

    asyncio.run(scenario())