import asyncio

from services.agent_runtime.contracts.result import AgentResult, CostRecord, ResultStatus
from services.agent_runtime.graph.executor import GraphExecutor
from services.agent_runtime.graph.task_graph import GraphPlan
from test_agent_runtime_graph import node, plan_data
from test_agent_runtime_phase1 import FakeLLM, build_manager, offline_gate


def test_status_retains_honest_partial_outcome(offline_gate):
    async def scenario():
        manager, audit, ledger, broker, registry = build_manager([], FakeLLM(), offline_gate)
        await manager.run_graph(GraphPlan.model_validate(plan_data([node("Scout")])))
        assert not manager.graph_status()
        status = manager.runtime_status()
        graph = status["graphs"][0]
        assert graph["status"] == "PARTIAL"
        assert graph["finished_percent"] == 100 and graph["successful_tasks"] == 0
        assert graph["nodes"][0]["name"] == "Scout"
        assert graph["nodes"][0]["result_status"] == "PARTIAL"
        assert "payload" not in str(status) and "description" not in str(status)
        graph["nodes"][0]["name"] = "changed"
        assert manager.runtime_status()["graphs"][0]["nodes"][0]["name"] == "Scout"
        assert status["agents"][0]["concurrency_limit"] == 2

    asyncio.run(scenario())


def test_recent_graph_history_is_bounded(offline_gate):
    async def scenario():
        manager, audit, ledger, broker, registry = build_manager([], FakeLLM(), offline_gate)
        first_id = None
        for index in range(21):
            result = await manager.run_graph(GraphPlan.model_validate(plan_data([node(f"Scout-{index}")])))
            if first_id is None:
                first_id = result.graph_id
        status = manager.runtime_status()
        assert len(status["graphs"]) == status["history_limit"] == 20
        assert status["graphs"][0]["nodes"][0]["name"] == "Scout-20"
        assert all(graph["graph_id"] != first_id for graph in status["graphs"])

    asyncio.run(scenario())


def test_budget_rejected_success_is_not_counted_as_successful(offline_gate):
    async def scenario():
        manager, audit, ledger, broker, registry = build_manager([], FakeLLM(), offline_gate)

        async def worker(task, inputs, token):
            return AgentResult(task_id=task.id, agent=task.agent, status=ResultStatus.SUCCESS,
                               summary="Over budget", cost=CostRecord(tool_calls=2))

        executor = GraphExecutor(registry, worker, audit)
        result = await executor.run(GraphPlan.model_validate(plan_data([node("Scout")])))
        assert result.status == "FAILED"
        assert executor.snapshot()["successful_tasks"] == 0
        assert executor.snapshot()["finished_percent"] == 100

    asyncio.run(scenario())


def test_status_exposes_active_named_task_without_fake_progress(offline_gate):
    async def scenario():
        manager, audit, ledger, broker, registry = build_manager([], FakeLLM(), offline_gate)
        started = asyncio.Event()
        release = asyncio.Event()

        class WaitingAgent:
            async def run(self, task):
                started.set()
                await release.wait()
                return AgentResult(task_id=task.id, agent=task.assigned_agent, status=ResultStatus.PARTIAL,
                                   summary="No evidence")

        manager._agents["research_agent"] = WaitingAgent()
        running = asyncio.create_task(manager.run_graph(GraphPlan.model_validate(plan_data([node("Atlas")]))))
        try:
            await asyncio.wait_for(started.wait(), 1)
            graph = manager.runtime_status()["graphs"][0]
            assert graph["status"] == "RUNNING" and graph["finished_percent"] == 0
            assert graph["nodes"][0]["state"] == "RUNNING"
            assert graph["nodes"][0]["result_status"] is None
        finally:
            release.set()
            await running

    asyncio.run(scenario())