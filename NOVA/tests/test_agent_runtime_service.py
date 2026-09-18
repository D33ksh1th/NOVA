import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import services.agent_runtime.service as service_module

from services.agent_runtime.service import RuntimeService, attach_runtime, research_plan
from services.agent_runtime.conversation import AgentConversation
from packages.application.conversation_service import ConversationService
from test_agent_runtime_phase1 import FakeLLM, _URL_RESULTS, build_manager, offline_gate


def attached_service(manager):
    owner = RuntimeService()
    owner.manager = manager
    owner.state = "READY"
    owner.loop = asyncio.get_running_loop()
    return owner


def test_owned_graph_and_shared_conversation_status(offline_gate):
    async def scenario():
        model = FakeLLM()
        manager, audit, ledger, broker, registry = build_manager(_URL_RESULTS, model, offline_gate)
        owner = attached_service(manager)
        conversation = ConversationService(SimpleNamespace(process=lambda message: "normal"),
                                           agent_runtime=AgentConversation(owner))
        reply = await asyncio.to_thread(conversation.handle, "use agents to research local speech models")
        assert reply["action"] == "agent_research_started"
        assert reply["response"] == "On it. I'll let you know when the report is ready."
        await asyncio.gather(*tuple(owner.jobs))
        status = await asyncio.to_thread(conversation.handle, "agent status")
        assert "3 of 3" in status["response"] and "3 successful" in status["response"]
        assert {node["name"] for node in owner.runtime_status()["graphs"][0]["nodes"]} == {"Scout", "Atlas", "Prism"}
        for parent in ("scout", "atlas"):
            for evidence in owner.last_result.results[parent].evidence:
                assert evidence.evidence_id not in model.seen_content
        assert "Piper is a fast local TTS." in model.seen_content
        results = await asyncio.to_thread(conversation.handle, "agent results")
        assert "https://example.com/piper" in results["response"]
        owner.last_result.gaps.update({node_id: "BUDGET_EXCEEDED" for node_id in owner.last_result.results})
        assert "https://example.com/piper" not in owner.command("results")["response"]
        assert owner.command("research", "another topic")["action"] == "agent_research_started"
        assert "do not have completed" in owner.command("results")["response"]
        await owner.close()
        assert owner.state == "HALTED" and not owner.jobs

    asyncio.run(scenario())


def test_stop_blocks_new_submissions(offline_gate):
    async def scenario():
        manager, audit, ledger, broker, registry = build_manager([], FakeLLM(), offline_gate)
        owner = attached_service(manager)
        assert owner.command("research", "topic")["action"] == "agent_research_started"
        assert owner.command("research", "another")["action"] == "agent_busy"
        assert owner.command("stop")["action"] == "agent_halt_requested"
        assert owner.command("research", "again")["action"] == "agent_unavailable"
        await asyncio.gather(*tuple(owner.jobs), return_exceptions=True)
        await owner.close()

    asyncio.run(scenario())


def test_empty_search_explains_missing_findings(offline_gate):
    async def scenario():
        model = FakeLLM()
        manager, audit, ledger, broker, registry = build_manager([], model, offline_gate)
        owner = attached_service(manager)
        owner.command("research", "gaming laptops")
        await asyncio.gather(*tuple(owner.jobs))
        reply = owner.command("results")["response"]
        assert "3 research tasks received no attributable search sources" in reply
        assert "no findings" in reply and model.calls == 0
        await owner.close()

    asyncio.run(scenario())


def test_model_failure_explains_stage_without_claiming_measured_usage(offline_gate):
    async def scenario():
        class BrokenModel:
            async def complete_metered(self, **kwargs):
                raise RuntimeError("private provider details")

        manager, audit, ledger, broker, registry = build_manager(_URL_RESULTS, BrokenModel(), offline_gate)
        owner = attached_service(manager)
        owner.command("research", "topic")
        await asyncio.gather(*tuple(owner.jobs))
        reply = owner.command("results")["response"]
        assert "research model failed" in reply
        assert "not confirmed model usage" in reply
        assert "private provider details" not in reply
        await owner.close()

    asyncio.run(scenario())


def test_disabled_backend_attaches_honest_status_and_detaches():
    async def scenario():
        app = SimpleNamespace(state=SimpleNamespace())
        conversation = ConversationService(SimpleNamespace(process=lambda message: "normal"))
        registry = SimpleNamespace(conversation=conversation, tool_registry=None, action_gate=None)
        async with attach_runtime(app, registry, SimpleNamespace(AGENT_RUNTIME_ENABLED=False)) as owner:
            assert app.state.agent_runtime is owner
            assert conversation.handle("agent status")["action"] == "agent_status"
            assert "not ready" in conversation.handle("agent status")["response"]
        assert conversation.agent_runtime is None and app.state.agent_runtime is None

    asyncio.run(scenario())


def test_research_workflow_never_requests_write_capabilities():
    plan = research_plan("local speech models")
    assert plan.layers() == (("scout", "atlas"), ("prism",))
    assert all(node.capabilities == ("web.search",) and node.risk == "READ_ONLY" for node in plan.nodes)


@pytest.mark.parametrize("blocked", [False, True])
def test_backend_preflight_and_resource_lifecycle(monkeypatch, blocked):
    async def scenario():
        settings = SimpleNamespace(AGENT_RUNTIME_ENABLED=True, AGENT_RUNTIME_MODEL="qualified-model",
            AGENT_RUNTIME_MODEL_DIGEST="pinned-digest", AGENT_RUNTIME_MODEL_URL="http://127.0.0.1:11434",
            AGENT_RUNTIME_TOKENIZER_PATH="models/local", AGENT_RUNTIME_AUDIT_PATH="data/test-audit.jsonl")
        preflight = AsyncMock(return_value=SimpleNamespace(status="BLOCKED" if blocked else "PREFLIGHT_ONLY",
                                                          reason="MODEL_DIGEST_MISMATCH" if blocked else ""))
        model = SimpleNamespace(close=AsyncMock())
        manager = SimpleNamespace(halt_all=AsyncMock(), close=AsyncMock())
        factory = AsyncMock(return_value=manager)
        monkeypatch.setattr(service_module, "qualify", preflight)
        monkeypatch.setattr(service_module, "load_local_tokenizer", lambda path: object())
        monkeypatch.setattr(service_module, "OllamaRuntimeModel", lambda **kwargs: model)
        monkeypatch.setattr(service_module, "build_runtime_async", factory)
        conversation = ConversationService(None)
        registry = SimpleNamespace(conversation=conversation, tool_registry=object(), action_gate=object())
        app = SimpleNamespace(state=SimpleNamespace())
        async with attach_runtime(app, registry, settings) as owner:
            assert app.state.agent_runtime is conversation.agent_runtime.owner is owner
            assert owner.state == ("UNAVAILABLE" if blocked else "READY")
            assert preflight.call_args.kwargs["expected_digest"] == "pinned-digest"
            if blocked:
                assert owner.reason_code == "MODEL_DIGEST_MISMATCH"
                factory.assert_not_called()
            else:
                assert factory.call_args.kwargs["tool_registry"] is registry.tool_registry
                assert factory.call_args.kwargs["llm"] is model
        assert conversation.agent_runtime is None and app.state.agent_runtime is None
        if not blocked:
            manager.halt_all.assert_awaited_once()
            manager.close.assert_awaited_once()
            model.close.assert_awaited_once()

    asyncio.run(scenario())