import asyncio
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock
import threading

import pytest

from services.agent_runtime.reports import ReportStore, finish_report, new_report
from services.agent_runtime.service import RuntimeService, research_plan
from test_agent_runtime_phase1 import FakeLLM, WebSearchTool, _URL_RESULTS, _running_task, build_manager, offline_gate
from services.agent_runtime.contracts.result import AgentResult, Evidence, ResultStatus
from test_agent_runtime_service import attached_service
from services.gateway.agent_dashboard import create_dashboard_app
import httpx


@pytest.mark.parametrize("image_host", ["external-content.duckduckgo.com", "ts1.mm.bing.net"])
def test_report_survives_reopen_and_preserves_verified_findings(tmp_path, offline_gate, monkeypatch, image_host):
    async def scenario():
        original = WebSearchTool.invoke

        async def with_images(tool, *args, **kwargs):
            result = await original(tool, *args, **kwargs)
            result.data["images"] = [{"url": "https://example.com/piper", "image_url": f"https://{image_host}/image.jpg", "title": "Piper TTS"}]
            return result

        monkeypatch.setattr(WebSearchTool, "invoke", with_images)
        manager, audit, ledger, broker, registry = build_manager(_URL_RESULTS, FakeLLM(), offline_gate)
        result = await manager.run_graph(research_plan("local speech models"))
        report = finish_report(new_report("report-test", "local speech models"), result)
        store = ReportStore(tmp_path / "reports.sqlite3")
        await store.open()
        await store.save(report)
        reopened = ReportStore(store.path)
        await reopened.open()
        saved = await reopened.get("report-test")
        assert saved == report and len(saved["findings"]) == 3
        assert saved["sources"][0]["url"] == "https://example.com/piper"
        assert len(saved["images"]) == 1 and saved["images"][0]["source_url"] == "https://example.com/piper"
        assert all(item.kind == "search_result" for node in result.results.values() for item in node.evidence)
        assert all(len(node.media) == len(node.payload["searches"]) for node in result.results.values())
        assert (await reopened.list(query="speech"))["total"] == 1
        assert (await reopened.list(query="missing"))["total"] == 0
        assert await reopened.get("' OR 1=1 --") is None
        await manager.close()

    asyncio.run(scenario())


def test_image_reference_cannot_back_a_factual_claim(offline_gate):
    async def scenario():
        manager, audit, ledger, broker, registry = build_manager(_URL_RESULTS, FakeLLM(), offline_gate)
        task = _running_task(broker, registry)
        image = Evidence(kind="image_reference", ref="https://example.com", digest="hash", trusted=False,
                         task_id=task.id, tool="web_search_tool")
        ledger.record(image)
        result = AgentResult(task_id=task.id, agent="research_agent", status=ResultStatus.SUCCESS, summary="unsupported",
                             payload={"claims": [{"text": "Unsupported specification", "evidence_ids": [image.evidence_id]}]})
        await manager._verify(task, result)
        assert result.status == ResultStatus.FAILED and not result.evidence
        await manager.close()

    asyncio.run(scenario())


def test_report_persists_broker_scores_and_ranks_sources_and_images(tmp_path, offline_gate, monkeypatch):
    class CiteAll(FakeLLM):
        async def complete(self, **kwargs):
            identities = re.findall(r'evidence_id="(ev_[0-9a-f]+)"', kwargs["content"])
            return {"summary": "Comparison", "claims": [{"text": "Comparison", "evidence_ids": identities}]}

    async def scenario():
        original = WebSearchTool.invoke

        async def scored_results(tool, *args, **kwargs):
            assert kwargs["relevance_query"] == "Piper TTS"
            result = await original(tool, *args, **kwargs)
            result.data["coverage"] = {"candidate_sources": 40, "pages_crawled": 0}
            result.data["images"] = [{"url": source["url"], "title": source["title"],
                                      "image_url": f"https://ts1.mm.bing.net/{index}", "relevance": {"score": -999}}
                                     for index, source in enumerate(result.data["results"])]
            return result

        monkeypatch.setattr(WebSearchTool, "invoke", scored_results)
        candidates = [{**source, "relevance": {"score": -999}} for source in reversed(_URL_RESULTS)]
        manager, *_ = build_manager(candidates, CiteAll(), offline_gate)
        try:
            result = await manager.run_graph(research_plan("Piper TTS"))
            report = finish_report(new_report("scores", "Piper TTS"), result)
            store = ReportStore(tmp_path / "scores.sqlite3")
            await store.open()
            await store.save(report)
            saved = await ReportStore(store.path).get("scores")
            for records in (saved["sources"], saved["images"]):
                assert len(records) >= 2
                scores = [record["relevance"]["score"] for record in records]
                assert scores == sorted(scores, reverse=True) and scores[0] == 100 and min(scores) < 100
                assert records[0]["title"] == "Piper TTS"
                assert all(record["relevance"]["query"] == "Piper TTS" for record in records)
            assert all(search["retrieval"] == {"candidate_sources": 40, "pages_crawled": 0}
                       for search in saved["coverage"]["searches"])
        finally:
            await manager.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("page,keep", [
    ("https://example.com/piper#photo", True),
    ("https://example.com/unrelated", False),
    ("https://example.com/kokoro", False),
    ("https://other.test/piper", False),
])
def test_report_images_must_belong_to_cited_findings(offline_gate, monkeypatch, page, keep):
    async def scenario():
        original = WebSearchTool.invoke

        async def with_image(tool, *args, **kwargs):
            result = await original(tool, *args, **kwargs)
            result.data["images"] = [{"url": page, "image_url": "https://ts1.mm.bing.net/photo",
                                      "title": "Search provider candidate"}]
            return result

        monkeypatch.setattr(WebSearchTool, "invoke", with_image)
        manager, *_ = build_manager(_URL_RESULTS, FakeLLM(), offline_gate)
        try:
            result = await manager.run_graph(research_plan("Piper TTS"))
            report = finish_report(new_report("image-scope", "Piper TTS"), result)
            assert bool(report["images"]) is keep
            assert report["findings"]
            for task in result.results.values():
                task.payload["claims"] = []
            assert finish_report(new_report("no-claims", "Piper TTS"), result)["images"] == []
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_rejected_task_claims_are_not_published(offline_gate):
    async def scenario():
        manager, audit, ledger, broker, registry = build_manager(_URL_RESULTS, FakeLLM(), offline_gate)
        result = await manager.run_graph(research_plan("topic"))
        result.gaps["prism"] = "BUDGET_EXCEEDED"
        report = finish_report(new_report("report-test", "topic"), result)
        assert {finding["task_id"] for finding in report["findings"]} == {"scout", "atlas"}
        assert report["gaps"][0]["task_id"] == "prism"
        await manager.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("code,expected", [
    ("MODEL_USAGE_UNAVAILABLE", "lacked valid token counts"),
    ("MODEL_TIMEOUT", "within its time limit"),
    ("MODEL_SCHEMA_INVALID", "required research schema"),
    ("MODEL_HTTP_503", "server was unavailable"),
    ("private provider detail", "failed before verification"),
])
def test_report_preserves_safe_model_failure_reason(offline_gate, code, expected):
    from services.agent_runtime.contracts.model_usage import ModelResponseError

    class FailingModel(FakeLLM):
        async def complete(self, **kwargs):
            raise ModelResponseError(code)

    async def scenario():
        manager, *_ = build_manager(_URL_RESULTS, FailingModel(), offline_gate)
        try:
            result = await manager.run_graph(research_plan("speech models"))
            report = finish_report(new_report("failure", "speech models"), result)
            assert expected in next(gap["reason"] for gap in report["gaps"] if gap["task_id"] == "scout")
            assert "private provider detail" not in str(report)
            assert "required research task failed" in next(gap["reason"] for gap in report["gaps"] if gap["task_id"] == "prism")
        finally:
            await manager.close()

    asyncio.run(scenario())


def test_interrupted_runs_are_recovered_without_overwriting_completed_reports(tmp_path):
    async def scenario():
        store = ReportStore(tmp_path / "reports.sqlite3")
        await store.open()
        await store.save(new_report("pending", "unfinished topic"))
        await store.save({**new_report("done", "finished topic"), "status": "COMPLETED"})
        await store.recover()
        assert (await store.get("pending"))["status"] == "INTERRUPTED"
        assert (await store.get("done"))["status"] == "COMPLETED"
        assert len((await store.list(limit=1))["items"]) == 1

    asyncio.run(scenario())


def test_runtime_saves_report_and_serves_history_after_restart(tmp_path, offline_gate):
    async def scenario():
        manager, audit, ledger, broker, registry = build_manager(_URL_RESULTS, FakeLLM(), offline_gate)
        owner = attached_service(manager)
        owner.reports = ReportStore(tmp_path / "reports.sqlite3")
        await owner.reports.open()
        reply = owner.command("research", "local speech models")
        report_id = reply["data"]["report_id"]
        await asyncio.gather(*tuple(owner.jobs))
        assert owner.command("results")["data"]["report_id"] == report_id
        await owner.close()
        restarted = RuntimeService()
        await restarted.start(settings=SimpleNamespace(AGENT_RUNTIME_ENABLED=False, AGENT_RUNTIME_REPORTS_PATH=str(owner.reports.path)), tool_registry=None, action_gate=None)
        assert restarted.command("results")["data"]["report_id"] == report_id
        app = create_dashboard_app(restarted)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            history = await client.get("/api/agent-runtime/reports", headers={"Origin": "http://localhost:1420"})
            assert history.status_code == 200 and history.json()["items"][0]["topic"] == "local speech models"
            detail = await client.get(f"/api/agent-runtime/reports/{report_id}")
            assert detail.headers["cache-control"] == "no-store"
            assert detail.json()["status"] == "COMPLETED" and len(detail.json()["findings"]) == 3
            assert (await client.get("/api/agent-runtime/reports/missing")).status_code == 404
            assert (await client.get("/api/agent-runtime/reports?limit=1000")).status_code == 422
            assert (await client.get("/api/agent-runtime/reports", headers={"Origin": "https://evil.test"})).status_code == 403

    asyncio.run(scenario())


@pytest.mark.parametrize("stop", [True, False])
def test_immediate_cancellation_preserves_history(tmp_path, offline_gate, stop):
    async def scenario():
        manager, *_ = build_manager(_URL_RESULTS, FakeLLM(), offline_gate)
        owner = attached_service(manager)
        owner.reports = ReportStore(tmp_path / "reports.sqlite3")
        await owner.reports.open()
        identity = owner.command("research", "cancel immediately")["data"]["report_id"]
        if stop:
            owner.command("stop")
            await asyncio.gather(*tuple(owner.jobs), return_exceptions=True)
            assert (await owner.reports.get(identity))["status"] == "CANCELLED"
        await owner.close()
        assert (await owner.reports.get(identity))["status"] == "CANCELLED"

    asyncio.run(scenario())


def test_cancelled_write_finishes_before_terminal_write(tmp_path, monkeypatch):
    async def scenario():
        store = ReportStore(tmp_path / "reports.sqlite3")
        await store.open()
        entered, release = threading.Event(), threading.Event()
        original = store._save

        def blocked_save(report, body):
            if report["status"] == "RUNNING":
                entered.set()
                assert release.wait(timeout=5)
            original(report, body)

        monkeypatch.setattr(store, "_save", blocked_save)
        report = {**new_report("cancelled", "topic"), "status": "RUNNING"}
        write = asyncio.create_task(store.save(report))
        assert await asyncio.to_thread(entered.wait, 5)
        write.cancel()
        report["status"] = "CANCELLED"
        final_write = asyncio.create_task(store.save(report))
        release.set()
        await asyncio.gather(write, return_exceptions=True)
        await final_write
        assert (await store.get(report["id"]))["status"] == "CANCELLED"

    asyncio.run(scenario())


def test_recovery_failure_closes_runtime_resources(tmp_path, monkeypatch):
    import services.agent_runtime.service as service_module

    async def scenario():
        model = SimpleNamespace(close=AsyncMock())
        manager = SimpleNamespace(close=AsyncMock())
        monkeypatch.setattr(service_module, "qualify", AsyncMock(return_value=SimpleNamespace(status="PREFLIGHT_ONLY")))
        monkeypatch.setattr(service_module, "load_local_tokenizer", lambda path: object())
        monkeypatch.setattr(service_module, "OllamaRuntimeModel", lambda **kwargs: model)
        monkeypatch.setattr(service_module, "build_runtime_async", AsyncMock(return_value=manager))
        monkeypatch.setattr(ReportStore, "recover", AsyncMock(side_effect=OSError("unavailable")))
        settings = SimpleNamespace(AGENT_RUNTIME_ENABLED=True, AGENT_RUNTIME_REPORTS_PATH=str(tmp_path / "reports.sqlite3"),
            AGENT_RUNTIME_TOKENIZER_PATH="models/local", AGENT_RUNTIME_MODEL="model", AGENT_RUNTIME_MODEL_DIGEST="digest",
            AGENT_RUNTIME_MODEL_URL="http://127.0.0.1:11434", AGENT_RUNTIME_AUDIT_PATH="unused")
        owner = RuntimeService()
        await owner.start(settings=settings, tool_registry=None, action_gate=None)
        assert owner.state == "UNAVAILABLE" and owner.manager is None and owner.model is None
        manager.close.assert_awaited_once()
        model.close.assert_awaited_once()

    asyncio.run(scenario())