import asyncio
import ast
from pathlib import Path
import subprocess
import sys

import httpx
from test_agent_runtime_service import attached_service

from services.gateway.agent_dashboard import create_dashboard_app
from services.agent_runtime.graph.task_graph import GraphPlan
from test_agent_runtime_graph import node, plan_data
from test_agent_runtime_phase1 import FakeLLM, build_manager, offline_gate


def test_conversation_http_entrypoints_guard_agent_commands():
    source = Path(__file__).resolve().parents[1] / "services/gateway/routes.py"
    module = ast.parse(source.read_text())
    for name in ("chat", "think", "voice_text"):
        handler = next(item for item in module.body if isinstance(item, ast.FunctionDef) and item.name == name)
        assert any(argument.arg == "request" for argument in handler.args.args)
        guard = next(item for item in handler.body if isinstance(item, ast.If)
                     and any(isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
                             and child.func.id == "agent_command" for child in ast.walk(item.test)))
        assert any(isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
                   and child.func.id == "require_local" for child in ast.walk(guard))
        registry_lines = [child.lineno for child in ast.walk(handler)
                          if isinstance(child, ast.Name) and child.id == "registry"]
        assert guard.lineno < min(registry_lines)


def test_monitor_import_does_not_boot_service_container():
    result = subprocess.run([sys.executable, "-c",
        "import services.gateway.agent_dashboard; import sys; "
        "assert 'packages.registry' not in sys.modules; "
        "assert 'services.gateway.main' not in sys.modules"], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert "Creating Service Registry" not in result.stdout


def test_disabled_dashboard_is_read_only_and_local():
    async def scenario():
        app = create_dashboard_app()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            response = await client.get("/api/agent-runtime/status")
            assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
            page = await client.get("/agents")
            assert page.status_code == 200 and "Agent Monitor" in page.text
            assert 'id="task-announcement" class="sr-only" role="status" aria-live="polite" aria-atomic="true"' in page.text
            assert 'id="speak-updates" type="button" aria-pressed="false"' in page.text
            for asset in ("agents.js", "agents.css", "lucide.min.js"):
                assert (await client.get(f"/ui-static/{asset}")).status_code == 200
            assert response.json()["state"] == "DISABLED" and response.json()["graphs"] == []
            assert (await client.post("/api/agent-runtime/status", json={})).status_code == 405
            assert (await client.get("/api/agent-runtime/status", headers={"Origin": "https://other.test"})).status_code == 403
            for origin in ("http://localhost:1420", "http://127.0.0.1:1420", "tauri://localhost"):
                assert (await client.get("/api/agent-runtime/status", headers={"Origin": origin})).status_code == 200
            for origin in ("http://localhost:1421", "http://localhost:1420.evil.test", "null"):
                assert (await client.get("/api/agent-runtime/status", headers={"Origin": origin})).status_code == 403
            assert (await client.get("/api/agent-runtime/status", headers={"Host": "other.test"})).status_code == 403
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("192.0.2.1", 1234)),
                                     base_url="http://127.0.0.1") as client:
            assert (await client.get("/api/agent-runtime/status")).status_code == 403
            assert (await client.get("/api/agent-runtime/status", headers={"Origin": "http://localhost:1420"})).status_code == 403

    asyncio.run(scenario())


def test_attached_runtime_exposes_only_status_fields(offline_gate):
    async def scenario():
        manager, audit, ledger, broker, registry = build_manager([], FakeLLM(), offline_gate)
        await manager.run_graph(GraphPlan.model_validate(plan_data([node("Atlas")])))
        app = create_dashboard_app(manager)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            response = await client.get("/api/agent-runtime/status")
            data = response.json()
            assert data["state"] == "READY"
            graph = data["graphs"][0]
            assert graph["status"] == "PARTIAL" and graph["finished_percent"] == 100
            assert graph["nodes"][0]["name"] == "Atlas"
            assert set(graph["nodes"][0]) == {"id", "name", "agent", "depends_on", "state", "result_status", "attempts"}
            await manager.halt_all("user stop")
            assert (await client.get("/api/agent-runtime/status")).json()["state"] == "HALTED"

    asyncio.run(scenario())


def test_dashboard_and_conversation_share_owned_runtime(offline_gate):
    async def scenario():
        manager, audit, ledger, broker, registry = build_manager([], FakeLLM(), offline_gate)
        owner = attached_service(manager)
        app = create_dashboard_app(owner)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            denied = await client.post("/api/agent-runtime/command", json={"action": "research", "objective": "topic"},
                                       headers={"Origin": "https://elsewhere.test"})
            assert denied.status_code == 403 and not owner.jobs
            response = await client.post("/api/agent-runtime/command", json={"action": "research", "objective": "topic"},
                                         headers={"Origin": "http://localhost:1420"})
            assert response.json()["action"] == "agent_research_started"
            await asyncio.gather(*tuple(owner.jobs))
            report = (await client.get("/api/agent-runtime/status")).json()
            assert report["state"] == "READY" and report["graphs"][0]["finished_tasks"] == 3
            spoken = (await client.post("/api/agent-runtime/command", json={"action": "status"})).json()
            assert "3 of 3" in spoken["response"]
            assert (await client.post("/api/agent-runtime/command", json={"action": "shell"})).status_code == 422
        await owner.close()

    asyncio.run(scenario())


def test_repository_endpoint_rejects_remote_and_unbounded_scope():
    from unittest.mock import AsyncMock
    from types import SimpleNamespace

    async def scenario():
        app = create_dashboard_app()
        review = AsyncMock(return_value={"action": "agent_repository_started", "data": {"report_id": "fixture"}})
        app.state.agent_runtime = SimpleNamespace(repository_review=review)
        body = {"repository": "nova-desktop", "objective": "Explain routing", "files": ["src/App.tsx"]}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            assert (await client.post("/api/agent-runtime/repository-review", json=body,
                                      headers={"Origin": "https://other.test"})).status_code == 403
            for invalid in ({**body, "repository": "NOVA"}, {**body, "files": []},
                            {**body, "files": ["a"] * 4}, {**body, "files": ["a" * 241]},
                            {**body, "root": "/tmp"}):
                assert (await client.post("/api/agent-runtime/repository-review", json=invalid)).status_code == 422
            review.assert_not_awaited()
            response = await client.post("/api/agent-runtime/repository-review", json=body,
                                         headers={"Origin": "http://127.0.0.1:1420"})
            assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
            review.assert_awaited_once_with("Explain routing", ["src/App.tsx"])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("192.0.2.1", 1234)),
                                     base_url="http://127.0.0.1") as client:
            assert (await client.post("/api/agent-runtime/repository-review", json=body)).status_code == 403

    asyncio.run(scenario())