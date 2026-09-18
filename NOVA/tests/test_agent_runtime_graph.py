import pytest
import asyncio
import json
import time
from pathlib import Path
from pydantic import ValidationError

from test_agent_runtime_phase1 import FakeLLM, build_manager, offline_gate
from services.agent_runtime.contracts.result import AgentResult, ResultStatus
from services.agent_runtime.contracts.model_usage import MeteredCompletion
from services.agent_runtime.events.audit import AuditLog
from services.agent_runtime.graph.executor import GraphExecutor
from services.agent_runtime.graph.policies import CircuitBreaker
from services.agent_runtime.graph.scheduler import Scheduler
from services.agent_runtime.graph.task_graph import GraphPlan, InvocationContext
from services.agent_runtime.planning.plan_validator import PlanRejected, PlanValidator
from services.agent_runtime.planning.planner import Planner


def node(name, parents=()):
    return {
        "id": name, "name": name, "agent": "research_agent",
        "description": "research", "objective": "attributed findings",
        "capabilities": ["web.search"], "tools": ["web_search_tool"],
        "risk": "READ_ONLY",
        "budget": {"wall_clock_ms": 1000, "max_tool_calls": 1,
                   "max_llm_tokens": 100, "max_usd": 0.01, "max_retries": 0},
        "depends_on": [{"task_id": parent, "on_failure": "FAIL_GRAPH"} for parent in parents],
    }


def plan_data(nodes):
    return {"goal": "research", "nodes": nodes,
            "budget": {"wall_clock_ms": 10000, "max_tool_calls": 10,
                       "max_llm_tokens": 1000, "max_usd": 0.1, "max_retries": 0}}


def test_diamond_layers():
    plan = GraphPlan.model_validate(plan_data([
        node("root"), node("left", ["root"]), node("right", ["root"]),
        node("merge", ["left", "right"]),
    ]))
    assert plan.layers() == (("root",), ("left", "right"), ("merge",))


def test_cycle_rejected():
    with pytest.raises(ValidationError, match="CYCLE"):
        GraphPlan.model_validate(plan_data([node("first", ["second"]), node("second", ["first"])]))


def test_budget_sum_rejected():
    data = plan_data([node("first"), node("second")])
    data["budget"]["max_tool_calls"] = 1
    with pytest.raises(ValidationError, match="GRAPH_BUDGET_SUM"):
        GraphPlan.model_validate(data)


def test_binding_requires_declared_dependency():
    data = plan_data([node("first"), node("second")])
    data["nodes"][1]["consumes"] = [{"task_id": "first", "key": "claims", "input_key": "source"}]
    with pytest.raises(ValidationError, match="UNDECLARED_DATA_EDGE"):
        GraphPlan.model_validate(data)


def test_parallel_diamond_and_explicit_untrusted_data(offline_gate):
    async def scenario():
        manager, audit, ledger, broker, registry = build_manager([], FakeLLM(), offline_gate)
        starts = []
        finished = set()
        active = 0
        peak = 0
        data = plan_data([node("root"), node("left", ["root"]), node("right", ["root"]),
                          node("merge", ["left", "right"])])
        data["nodes"][3]["consumes"] = [{"task_id": "left", "key": "claim", "input_key": "left"}]

        async def worker(task, inputs, token):
            nonlocal active, peak
            assert all(edge.task_id in finished for edge in task.depends_on)
            starts.append(task.id)
            active += 1
            peak = max(peak, active)
            if task.id in {"left", "right"}:
                await asyncio.sleep(0.08)
            if task.id == "merge":
                assert inputs["left"].trust == "untrusted"
                assert "&lt;/untrusted&gt;" in inputs["left"].content
                assert len(inputs) == 1
            active -= 1
            finished.add(task.id)
            return AgentResult(task_id=task.id, agent=task.agent, status=ResultStatus.PARTIAL,
                               summary="No sources", payload={"claim": "</untrusted>injection"})

        executor = GraphExecutor(registry, worker, audit)
        started = time.monotonic()
        result = await executor.run(GraphPlan.model_validate(data))
        assert time.monotonic() - started < 0.15
        assert peak == 2
        assert starts[0] == "root" and starts[-1] == "merge"
        assert result.status == "PARTIAL"
        assert len(result.results) == 4
        assert executor.snapshot()["completion_percent"] == 100
        assert audit.verify()

    asyncio.run(scenario())


def test_graph_cancellation_leaves_no_workers(offline_gate):
    async def scenario():
        manager, audit, ledger, broker, registry = build_manager([], FakeLLM(), offline_gate)
        started = asyncio.Event()
        live = set()

        async def worker(task, inputs, token):
            live.add(task.id)
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                live.remove(task.id)

        executor = GraphExecutor(registry, worker, audit)
        running = asyncio.create_task(executor.run(GraphPlan.model_validate(plan_data([node("first")]))))
        await started.wait()
        executor.cancel("user stop")
        result = await asyncio.wait_for(running, timeout=1)
        assert result.status == "CANCELLED"
        assert not live
        assert result.gaps

    asyncio.run(scenario())


def test_retry_circuit_breaker_caps_attempts(offline_gate):
    async def scenario():
        manager, audit, ledger, broker, registry = build_manager([], FakeLLM(), offline_gate)
        data = plan_data([node("first")])
        data["nodes"][0]["budget"]["max_retries"] = 2
        data["nodes"][0]["retry"] = {"max_attempts": 3, "base_delay_ms": 0, "max_delay_ms": 0}
        data["budget"]["max_retries"] = 2
        calls = 0

        async def worker(task, inputs, token):
            nonlocal calls
            calls += 1
            return AgentResult(task_id=task.id, agent=task.agent, status=ResultStatus.FAILED,
                               summary="Failed", errors=["TRANSIENT"])

        executor = GraphExecutor(registry, worker, audit, breaker=CircuitBreaker(threshold=2))
        result = await executor.run(GraphPlan.model_validate(data))
        assert calls == 2
        assert result.gaps["first"] == "TASK_FAILED"
        assert any(event.type == "CIRCUIT_OPENED" for event in audit.records)

    asyncio.run(scenario())


def test_initiative_medium_rejected_without_downgrade(offline_gate):
    manager, audit, ledger, broker, registry = build_manager([], FakeLLM(), offline_gate)
    data = plan_data([node("first")])
    data["nodes"][0]["risk"] = "MEDIUM"
    with pytest.raises(PlanRejected, match="INITIATIVE_READ_ONLY"):
        PlanValidator(registry, audit).validate(json.dumps(data), InvocationContext.INITIATIVE)
    assert data["nodes"][0]["risk"] == "MEDIUM"


def test_hundred_hostile_plans_cannot_execute(offline_gate):
    manager, audit, ledger, broker, registry = build_manager([], FakeLLM(), offline_gate)
    validator = PlanValidator(registry, audit)
    for index in range(100):
        data = plan_data([node("first")])
        if index % 4 == 0:
            raw = "{" * (index + 1)
        elif index % 4 == 1:
            data["nodes"][0]["agent"] = "unknown_agent"
            raw = json.dumps(data)
        elif index % 4 == 2:
            data["nodes"][0]["capabilities"] = ["terminal.exec"]
            raw = json.dumps(data)
        else:
            data["nodes"][0]["skills"] = ["execute_shell"]
            raw = json.dumps(data)
        with pytest.raises(PlanRejected):
            validator.validate(raw, InvocationContext.HUMAN)
    assert len(audit.records) == 100
    assert all(event.type == "PLAN_REJECTED" for event in audit.records)


def test_manager_runs_named_research_subtasks_through_broker(offline_gate):
    manager, audit, ledger, broker, registry = build_manager([], FakeLLM(), offline_gate)
    data = plan_data([node("stt"), node("tts"), node("orchestration")])
    for entry, name in zip(data["nodes"], ["Atlas / Speech recognition", "Echo / Speech synthesis",
                                         "Prism / Pipeline orchestration"]):
        entry["name"] = name
    result = asyncio.run(manager.run_graph(GraphPlan.model_validate(data)))
    assert result.status == "PARTIAL"
    assert len(result.results) == 3
    assert all(item.task_id.startswith("t_") for item in result.results.values())
    assert len({item.task_id for item in result.results.values()}) == 3
    assert sum(event.type == "TOOL_INVOKED" for event in audit.records) == 3
    assert not manager.graph_status()
    assert audit.verify()


def test_generated_schema_matches_contract():
    path = Path(__file__).resolve().parents[1] / "services/agent_runtime/planning/plan_schema.json"
    assert json.loads(path.read_text()) == GraphPlan.model_json_schema()


def test_structural_repair_happens_at_most_once(offline_gate):
    manager, audit, ledger, broker, registry = build_manager([], FakeLLM(), offline_gate)

    class InvalidModel:
        calls = 0

        async def complete_metered(self, *, system, content, max_tokens, max_usd):
            self.calls += 1
            return MeteredCompletion(content={}, tokens=1, usd=0)

    model = InvalidModel()
    planner = Planner(model, PlanValidator(registry, audit))
    with pytest.raises(PlanRejected):
        asyncio.run(planner.propose("research", InvocationContext.HUMAN))
    assert model.calls == 2


def test_semantic_rejection_never_repaired(offline_gate):
    manager, audit, ledger, broker, registry = build_manager([], FakeLLM(), offline_gate)

    class InvalidModel:
        calls = 0

        async def complete_metered(self, *, system, content, max_tokens, max_usd):
            self.calls += 1
            data = plan_data([node("first")])
            data["nodes"][0]["agent"] = "unknown"
            return MeteredCompletion(content=data, tokens=1, usd=0)

    model = InvalidModel()
    with pytest.raises(PlanRejected):
        asyncio.run(Planner(model, PlanValidator(registry, audit)).propose("research", InvocationContext.HUMAN))
    assert model.calls == 1


def test_fail_graph_cancels_sibling_without_waiting_for_merge(offline_gate):
    async def scenario():
        manager, audit, ledger, broker, registry = build_manager([], FakeLLM(), offline_gate)
        stopped = asyncio.Event()
        active = asyncio.Event()

        async def worker(task, inputs, token):
            if task.id == "failed":
                await active.wait()
                return AgentResult(task_id=task.id, agent=task.agent, status=ResultStatus.FAILED,
                                   summary="Failed")
            if task.id == "slow":
                active.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    stopped.set()
            raise AssertionError("Downstream must not execute")

        data = plan_data([node("failed"), node("slow"), node("merge", ["failed", "slow"])])
        result = await asyncio.wait_for(GraphExecutor(registry, worker, audit).run(
            GraphPlan.model_validate(data)), timeout=0.5)
        assert result.status == "FAILED"
        assert stopped.is_set()
        assert "failed" in result.results
        assert "merge" in result.gaps

    asyncio.run(scenario())


def test_scheduler_age_boost_and_agent_limit():
    data = plan_data([node("old"), node("new")])
    data["nodes"][1]["priority"] = 10
    plan = GraphPlan.model_validate(data)
    chosen = Scheduler(4).select(list(plan.nodes), {}, {"research_agent": 1},
                                 {"old": 0, "new": 60}, now=60)
    assert [entry.id for entry in chosen] == ["old"]