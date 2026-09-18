import asyncio
import pytest

from test_agent_runtime_phase1 import FakeLLM, _running_task, build_manager, offline_gate
from services.agent_runtime.contracts.model_usage import MeteredCompletion
from services.agent_runtime.contracts.result import ResultStatus
from services.agent_runtime.exceptions import PolicyError


def test_cannot_borrow_another_tasks_identity(offline_gate):
    manager, audit, ledger, broker, registry = build_manager([], FakeLLM(), offline_gate)
    task = _running_task(broker, registry)
    result = asyncio.run(broker.invoke("unknown_agent", task.id, "web_search_tool", {"query": "x"}))
    assert result.reason == "TASK_AGENT_MISMATCH"


def test_idempotency_reserved_before_parallel_dispatch(offline_gate):
    async def scenario():
        manager, audit, ledger, broker, registry = build_manager([], FakeLLM(), offline_gate)
        task = _running_task(broker, registry)
        tool = registry.resolve_tool("web_search_tool")
        tool.NON_IDEMPOTENT = True
        results = await asyncio.gather(*[
            broker.invoke("research_agent", task.id, "web_search_tool", {"query": "x"},
                          idempotency_key="same-operation") for attempt in range(2)
        ])
        assert sum(result.ok for result in results) == 1
        assert sum(result.reason == "IDEMPOTENCY_REPLAY" for result in results) == 1
        assert broker.context(task.id).budget.tool_calls == 1

    asyncio.run(scenario())


def test_failed_attempt_still_charged(offline_gate):
    manager, audit, ledger, broker, registry = build_manager([], FakeLLM(), offline_gate)
    task = _running_task(broker, registry)

    async def fail(**args):
        raise RuntimeError("backend unavailable")

    registry.resolve_tool("web_search_tool").invoke = fail
    result = asyncio.run(broker.invoke("research_agent", task.id, "web_search_tool", {"query": "x"}))
    assert not result.ok
    assert broker.context(task.id).budget.tool_calls == 1


def test_real_model_budget_exhaustion_cancels_task(offline_gate):
    from test_agent_runtime_phase1 import _URL_RESULTS

    class OverBudget(FakeLLM):
        async def complete_metered(self, *, system, content, max_tokens, max_usd):
            return MeteredCompletion(content={}, tokens=max_tokens + 1, usd=0)

    manager, audit, ledger, broker, registry = build_manager(_URL_RESULTS, OverBudget(), offline_gate)
    result = asyncio.run(manager.run_task("research", "compare"))
    assert result.status == ResultStatus.FAILED
    assert "BUDGET_EXCEEDED" in result.errors
    assert result.cost.llm_tokens == 40001
    assert any(event.type == "BUDGET_EXCEEDED" for event in audit.records)
    assert broker.context(result.task_id) is None


def test_policy_cannot_be_reloaded_or_mutated(offline_gate):
    manager, audit, ledger, broker, registry = build_manager([], FakeLLM(), offline_gate)
    with pytest.raises(PolicyError, match="startup-only"):
        registry.load()
    with pytest.raises(TypeError):
        registry.get("research_agent").resource_scopes["new_grant"] = {}