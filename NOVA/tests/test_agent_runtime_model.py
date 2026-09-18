import asyncio
import json
import time
from types import SimpleNamespace

import httpx
import pytest

from services.agent_runtime.contracts.model_usage import BudgetExceededError, ModelResponseError
from services.agent_runtime.contracts.model_usage import MeteredCompletion
from services.agent_runtime.contracts.event import EventType
from services.agent_runtime.events.audit import AuditLog
from services.agent_runtime.models.ollama import OllamaRuntimeModel
from services.agent_runtime.models.session import MeteredModelSession
from services.agent_runtime.factory import build_runtime_async
from services.agent_runtime.contracts.result import ResultStatus
from services.agent_runtime.planning.planner import Planner
from services.agent_runtime.planning.plan_validator import PlanRejected, PlanValidator
from services.agent_runtime.graph.task_graph import InvocationContext
from services.agent_runtime.graph.task_graph import GraphPlan
from test_agent_runtime_graph import node, plan_data
from test_agent_runtime_phase1 import (
    FakeLLM, WebSearchTool, _ToolRegistry, _URL_RESULTS, _running_task, build_manager, offline_gate,
)


class Tokenizer:
    def apply_chat_template(self, conversation, *, tokenize, add_generation_prompt, enable_thinking):
        assert not tokenize and add_generation_prompt
        assert not enable_thinking
        assert [message["role"] for message in conversation] == ["system", "user"]
        return json.dumps(conversation)

    def encode(self, text, *, add_special_tokens):
        assert add_special_tokens
        return list(range(10))


def response_data(**changes):
    return {"response": '{"claims": []}', "prompt_eval_count": 10, "eval_count": 3,
            "done": True, "done_reason": "stop", **changes}


def test_local_adapter_caps_and_meters_request():
    async def scenario():
        def respond(request):
            payload = json.loads(request.content)
            assert request.url.path == "/api/generate"
            assert payload["raw"] is True and payload["stream"] is False
            assert payload["think"] is False
            assert payload["options"]["num_predict"] == 5
            assert payload["format"] == "json"
            return httpx.Response(200, json=response_data())

        async with OllamaRuntimeModel(model="local:test", tokenizer=Tokenizer(),
                                      transport=httpx.MockTransport(respond)) as model:
            result = await model.complete_metered(system="policy", content="untrusted", max_tokens=15, max_usd=0)
            assert result.tokens == 13 and result.usd == 0
            assert result.content == {"claims": []}

    asyncio.run(scenario())


def test_unexpected_model_error_records_type_without_sensitive_message():
    async def scenario():
        class BrokenModel:
            async def complete_metered(self, **kwargs):
                raise RuntimeError("private prompt or provider detail")

        audit = AuditLog()
        session = MeteredModelSession(model=BrokenModel(), audit=audit, max_tokens=20,
                                     max_usd=0, timeout_seconds=1)
        with pytest.raises(ModelResponseError, match="MODEL_USAGE_UNCERTAIN"):
            await session.complete(system="policy", content="input")
        event = next(event for event in audit.records if event.type == EventType.MODEL_FAILED)
        assert event.data == {"reason": "MODEL_USAGE_UNCERTAIN", "exception_type": "RuntimeError"}
        assert session.tokens == 20 and session.failed

    asyncio.run(scenario())


def test_research_schema_is_sent_to_ollama():
    from services.agent_runtime.agents.research_agent import ResearchOutput

    async def scenario():
        schema = ResearchOutput.model_json_schema()

        def respond(request):
            payload = json.loads(request.content)
            assert payload["format"] == schema
            assert payload["format"]["additionalProperties"] is False
            return httpx.Response(200, json=response_data())

        async with OllamaRuntimeModel(model="local:test", tokenizer=Tokenizer(), response_schema=schema,
                                      transport=httpx.MockTransport(respond)) as model:
            await model.complete_metered(system="policy", content="input", max_tokens=20, max_usd=0)

    asyncio.run(scenario())


@pytest.mark.parametrize("status,body,code", [
    (200, {"error": "private provider detail"}, "MODEL_PROVIDER_ERROR"),
    (400, {"error": "private provider detail"}, "MODEL_HTTP_400"),
    (503, {"error": "private provider detail"}, "MODEL_HTTP_503"),
    (200, {"response": "{}", "done": True}, "MODEL_USAGE_UNAVAILABLE"),
])
def test_provider_failures_are_distinct_without_logging_response(status, body, code):
    async def scenario():
        async with OllamaRuntimeModel(model="local:test", tokenizer=Tokenizer(), transport=httpx.MockTransport(
                lambda request: httpx.Response(status, json=body))) as model:
            with pytest.raises(ModelResponseError) as caught:
                await model.complete_metered(system="policy", content="input", max_tokens=20, max_usd=0)
            assert str(caught.value) == code
            assert caught.value.tokens is None

    asyncio.run(scenario())


def test_session_timeout_does_not_mix_monotonic_and_loop_clock(monkeypatch):
    import services.agent_runtime.models.session as session_module

    monotonic = time.monotonic
    monkeypatch.setattr(session_module, "time", SimpleNamespace(monotonic=lambda: monotonic() - 1000000))

    async def scenario():
        class YieldingModel:
            async def complete_metered(self, **kwargs):
                loop = asyncio.get_running_loop()
                completed = loop.create_future()
                loop.call_soon(lambda: None if completed.done() else completed.set_result(None))
                await completed
                return MeteredCompletion(content={"ok": True}, tokens=3, usd=0)

        session = MeteredModelSession(model=YieldingModel(), audit=AuditLog(), max_tokens=20,
                                     max_usd=0, timeout_seconds=120)
        result = await session.complete(system="policy", content="input")
        assert result.content == {"ok": True}
        assert session.tokens == 3 and not session.failed

    asyncio.run(scenario())


def test_adapter_research_task_persists_usage_and_evidence(tmp_path, offline_gate):
    async def scenario():
        fake = FakeLLM()

        async def respond(request):
            prompt = json.loads(json.loads(request.content)["prompt"])
            output = await fake.complete(system=prompt[0]["content"], content=prompt[1]["content"])
            return httpx.Response(200, json=response_data(response=json.dumps(output)))

        path = tmp_path / "audit.jsonl"
        async with OllamaRuntimeModel(model="local:test", tokenizer=Tokenizer(),
                                      transport=httpx.MockTransport(respond)) as model:
            manager = await build_runtime_async(tool_registry=_ToolRegistry([WebSearchTool(_URL_RESULTS)]),
                                                action_gate=offline_gate, llm=model, audit_path=path)
            try:
                result = await manager.run_task("research", "compare")
                assert result.status == ResultStatus.SUCCESS and result.evidence
                assert result.cost.llm_tokens == 13 and result.cost.usd == 0
                events = manager._audit.records
                requested = next(index for index, event in enumerate(events) if event.type == EventType.MODEL_REQUESTED)
                usage = next(index for index, event in enumerate(events) if event.type == EventType.MODEL_USAGE)
                assert requested < usage
                assert events[usage].data["accounting"] == "reported"
            finally:
                await manager.close()
        assert (await AuditLog.check_file(path)).valid

    asyncio.run(scenario())


def test_broker_rechecks_cancellation_after_model_audit(offline_gate, monkeypatch):
    async def scenario():
        model = FakeLLM()
        manager, audit, ledger, broker, registry = build_manager([], model, offline_gate)
        task = _running_task(broker, registry)
        append = audit.append_async

        async def cancel_after_requested(event_type, **kwargs):
            event = await append(event_type, **kwargs)
            if event_type == EventType.MODEL_REQUESTED:
                broker.cancel_task(task.id)
            return event

        monkeypatch.setattr(audit, "append_async", cancel_after_requested)
        with pytest.raises(asyncio.CancelledError):
            await broker.complete(task.assigned_agent, task.id, model, system="policy", content="input")
        assert model.calls == 0
        assert broker.context(task.id).budget.llm_tokens == 0

    asyncio.run(scenario())


def test_model_dispatch_requires_audit_acknowledgement(monkeypatch):
    async def scenario():
        model = FakeLLM()
        audit = AuditLog()

        async def fail_audit(*args, **kwargs):
            raise OSError("audit unavailable")

        monkeypatch.setattr(audit, "append_async", fail_audit)
        session = MeteredModelSession(model=model, audit=audit, max_tokens=20, max_usd=0, timeout_seconds=1)
        with pytest.raises(OSError):
            await session.complete(system="policy", content="input")
        assert model.calls == 0

    asyncio.run(scenario())


def test_graph_does_not_retry_unknown_model_usage(offline_gate):
    async def scenario():
        class FailingModel:
            calls = 0

            async def complete_metered(self, **kwargs):
                self.calls += 1
                raise ModelResponseError("MODEL_USAGE_UNAVAILABLE")

        model = FailingModel()
        manager, audit, ledger, broker, registry = build_manager(_URL_RESULTS, model, offline_gate)
        data = plan_data([node("Scout")])
        data["nodes"][0]["budget"]["max_retries"] = 2
        data["nodes"][0]["retry"] = {"max_attempts": 3, "base_delay_ms": 0, "max_delay_ms": 0}
        data["budget"]["max_retries"] = 2
        result = await manager.run_graph(GraphPlan.model_validate(data))
        assert result.status == "FAILED" and model.calls == 1
        assert not any(event.type == EventType.RETRY_SCHEDULED for event in audit.records)
        assert result.cost.llm_tokens == data["nodes"][0]["budget"]["max_llm_tokens"]

    asyncio.run(scenario())


def test_unknown_usage_exhausts_session_and_blocks_retry():
    async def scenario():
        class FailingModel:
            calls = 0

            async def complete_metered(self, **kwargs):
                self.calls += 1
                raise RuntimeError("sensitive provider response")

        model = FailingModel()
        audit = AuditLog()
        session = MeteredModelSession(model=model, audit=audit, max_tokens=20, max_usd=0.5, timeout_seconds=1)
        with pytest.raises(ModelResponseError, match="MODEL_USAGE_UNCERTAIN"):
            await session.complete(system="policy", content="input")
        with pytest.raises(ModelResponseError, match="MODEL_SESSION_FAILED"):
            await session.complete(system="policy", content="input")
        assert model.calls == 1
        assert session.tokens == 20 and session.usd == 0.5
        usage = next(event for event in audit.records if event.type == EventType.MODEL_USAGE)
        assert usage.data["accounting"] == "reserved"
        assert "sensitive provider response" not in audit.dump()

    asyncio.run(scenario())


def test_concurrent_model_calls_share_remaining_budget():
    async def scenario():
        class MeasuredModel:
            limits = []

            async def complete_metered(self, *, max_tokens, max_usd, **kwargs):
                self.limits.append((max_tokens, max_usd))
                await asyncio.sleep(0)
                return MeteredCompletion(content={}, tokens=6, usd=0.25)

        model = MeasuredModel()
        session = MeteredModelSession(model=model, audit=AuditLog(), max_tokens=12, max_usd=0.5,
                                      timeout_seconds=1)
        await asyncio.gather(*(session.complete(system="policy", content="input") for index in range(2)))
        assert model.limits == [(12, 0.5), (6, 0.25)]
        assert session.tokens == 12 and session.usd == 0.5
        with pytest.raises(BudgetExceededError):
            await session.complete(system="policy", content="input")

    asyncio.run(scenario())


def test_planner_repair_uses_remaining_allowance(offline_gate):
    async def scenario():
        manager, audit, ledger, broker, registry = build_manager([], FakeLLM(), offline_gate)

        class InvalidModel:
            limits = []

            async def complete_metered(self, *, max_tokens, **kwargs):
                self.limits.append(max_tokens)
                raise ModelResponseError("MODEL_JSON_INVALID", tokens=6)

        model = InvalidModel()
        planner = Planner(model, PlanValidator(registry, audit), max_tokens=12)
        with pytest.raises(PlanRejected):
            await planner.propose("research", InvocationContext.HUMAN)
        assert model.limits == [12, 6]
        assert sum(event.data["tokens"] for event in audit.records if event.type == EventType.MODEL_USAGE) == 12

        model.limits = []
        planner = Planner(model, PlanValidator(registry, audit), max_tokens=6)
        with pytest.raises(BudgetExceededError):
            await planner.propose("research", InvocationContext.HUMAN)
        assert model.limits == [6]

    asyncio.run(scenario())


def test_session_timeout_cleans_up_worker_and_reserves_usage():
    async def scenario():
        stopped = asyncio.Event()

        class WaitingModel:
            async def complete_metered(self, **kwargs):
                try:
                    await asyncio.Event().wait()
                finally:
                    stopped.set()

        session = MeteredModelSession(model=WaitingModel(), audit=AuditLog(), max_tokens=20,
                                      max_usd=0, timeout_seconds=0.02)
        with pytest.raises(ModelResponseError, match="MODEL_USAGE_UNCERTAIN"):
            await session.complete(system="policy", content="input")
        assert stopped.is_set() and session.failed and session.tokens == 20

    asyncio.run(scenario())


def test_cancellation_closes_real_http_connection():
    async def scenario():
        received = asyncio.Event()
        disconnected = asyncio.Event()
        connections = set()

        async def respond(reader, writer):
            connections.add(asyncio.current_task())
            try:
                headers = await reader.readuntil(b"\r\n\r\n")
                length = next(int(line.split(b":", 1)[1]) for line in headers.split(b"\r\n")
                              if line.lower().startswith(b"content-length:"))
                await reader.readexactly(length)
                received.set()
                assert await reader.read() == b""
            finally:
                writer.close()
                await writer.wait_closed()
                disconnected.set()
                connections.discard(asyncio.current_task())

        server = await asyncio.start_server(respond, "127.0.0.1", 0)
        async with server:
            port = server.sockets[0].getsockname()[1]
            async with OllamaRuntimeModel(model="local:test", tokenizer=Tokenizer(),
                                          base_url=f"http://127.0.0.1:{port}") as model:
                pending = asyncio.create_task(model.complete_metered(system="policy", content="input",
                                                                     max_tokens=20, max_usd=0))
                try:
                    await asyncio.wait_for(received.wait(), 1)
                finally:
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
                await asyncio.wait_for(disconnected.wait(), 1)
                assert not connections

    asyncio.run(scenario())


@pytest.mark.parametrize("url", ["https://example.com", "http://localhost:11434", "http://127.0.0.1/api",
                                 "http://user:secret@127.0.0.1", "http://127.0.0.1?key=value"])
def test_remote_or_credential_bearing_endpoints_rejected(url):
    with pytest.raises(ValueError, match="LOCAL_MODEL_ENDPOINT_REQUIRED"):
        OllamaRuntimeModel(model="local:test", tokenizer=Tokenizer(), base_url=url)


def test_http_failure_never_falls_back_and_hides_response():
    async def scenario():
        calls = []

        def respond(request):
            calls.append(request)
            return httpx.Response(500, text="secret-provider-body")

        async with OllamaRuntimeModel(model="local:test", tokenizer=Tokenizer(),
                                      transport=httpx.MockTransport(respond)) as model:
            with pytest.raises(ModelResponseError) as caught:
                await model.complete_metered(system="policy", content="input", max_tokens=20, max_usd=0)
            assert "secret-provider-body" not in str(caught.value)
            assert len(calls) == 1

    asyncio.run(scenario())


def test_prompt_exhaustion_never_dispatches():
    async def scenario():
        def unexpected(request):
            raise AssertionError("over-budget request")

        async with OllamaRuntimeModel(model="local:test", tokenizer=Tokenizer(),
                                      transport=httpx.MockTransport(unexpected)) as model:
            with pytest.raises(BudgetExceededError):
                await model.complete_metered(system="policy", content="input", max_tokens=10, max_usd=0)

    asyncio.run(scenario())


@pytest.mark.parametrize("changes,code,tokens", [
    ({"eval_count": None}, "MODEL_USAGE_UNAVAILABLE", None),
    ({"eval_count": True}, "MODEL_USAGE_UNAVAILABLE", None),
    ({"prompt_eval_count": 11}, "MODEL_TOKEN_CONTRACT_VIOLATION", 14),
    ({"eval_count": 1000}, "MODEL_TOKEN_CONTRACT_VIOLATION", 1010),
    ({"done_reason": "length"}, "MODEL_INCOMPLETE", 13),
    ({"response": "not JSON"}, "MODEL_JSON_INVALID", 13),
    ({"response": '{"claims": [], "claims": []}'}, "MODEL_JSON_INVALID", 13),
    ({"response": '{"value": NaN}'}, "MODEL_JSON_INVALID", 13),
])
def test_invalid_responses_fail_closed(changes, code, tokens):
    async def scenario():
        async with OllamaRuntimeModel(model="local:test", tokenizer=Tokenizer(), transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=response_data(**changes)))) as model:
            with pytest.raises(ModelResponseError, match=code) as caught:
                await model.complete_metered(system="policy", content="input", max_tokens=20, max_usd=0)
            assert caught.value.tokens == tokens

    asyncio.run(scenario())


def test_cancellation_reaches_transport_without_retry():
    async def scenario():
        started = asyncio.Event()
        stopped = asyncio.Event()
        calls = []

        async def respond(request):
            calls.append(request)
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        async with OllamaRuntimeModel(model="local:test", tokenizer=Tokenizer(),
                                      transport=httpx.MockTransport(respond)) as model:
            pending = asyncio.create_task(model.complete_metered(system="policy", content="input",
                                                                 max_tokens=20, max_usd=0))
            await asyncio.wait_for(started.wait(), 1)
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(pending, 1)
            assert stopped.is_set() and len(calls) == 1

    asyncio.run(scenario())