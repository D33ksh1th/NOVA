"""AgentManager — single-task mode (Constitution I1, I6, I9, I12, I13, I16).

The ONE entry point the Brain may call is ``run_task``. It builds a task,
validates the assignment against the registry/policy, runs the assigned agent
under a wall-clock timeout, then verifies the result: schema present, no
fabricated evidence, and SUCCESS only when backed by real ledger evidence.
Verification is done by the manager, never by the executing agent (I6).
"""

from __future__ import annotations

import asyncio
from collections import deque
from copy import deepcopy
import time
from typing import Callable

from services.agent_runtime.agents.research_agent import ResearchAgent
from services.agent_runtime.agents.repository_reader import RepositoryReader
from services.agent_runtime.base import LLM
from services.agent_runtime.broker import BudgetTracker, TaskContext, ToolBroker
from services.agent_runtime.contracts.event import EventType, Severity
from services.agent_runtime.contracts.model_usage import BudgetExceededError, ModelResponseError, MODEL_FAILURE_MESSAGES
from services.agent_runtime.contracts.result import AgentResult, CostRecord, ResultStatus
from services.agent_runtime.contracts.task import AgentTask, RiskTier, TaskStatus
from services.agent_runtime.contracts.task import TaskBudget
from services.agent_runtime.events.audit import AuditLog
from services.agent_runtime.graph.executor import GraphExecutor, GraphResult
from services.agent_runtime.graph.policies import CancellationToken
from services.agent_runtime.graph.task_graph import BoundOutput, GraphPlan, InvocationContext, Node
from services.agent_runtime.ledger import EvidenceLedger
from services.agent_runtime.registry import AgentRegistry

_AGENT_CLASSES = {"research_agent": ResearchAgent, "repo_reader": RepositoryReader}


class AgentManager:
    def __init__(
        self,
        *,
        registry: AgentRegistry,
        broker: ToolBroker,
        audit: AuditLog,
        ledger: EvidenceLedger,
        llm: LLM,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._registry = registry
        self._broker = broker
        self._audit = audit
        self._ledger = ledger
        self._llm = llm
        self._clock = clock
        self._halted = False
        self._active_tasks = 0
        self._running: dict[str, asyncio.Task[AgentResult]] = {}
        self._graphs: dict[str, GraphExecutor] = {}
        self._graph_history: deque[dict[str, object]] = deque(maxlen=20)
        self._slots = asyncio.Semaphore(4)
        self._agent_slots = {name: asyncio.Semaphore(registry.get(name).concurrency_limit)
                     for name in registry.names()}
        self._agents = {
            name: cls(registry.get(name), broker, llm)
            for name, cls in _AGENT_CLASSES.items()
            if registry.has(name)
        }

    async def run_task(
        self,
        description: str,
        objective: str,
        hints: dict | None = None,
        *,
        assigned_agent: str = "research_agent",
    ) -> AgentResult:
        if self._halted:
            raise RuntimeError("Agent runtime is halted")
        spec = self._registry.get(assigned_agent)  # UnknownAgentError if absent (I1)
        if not spec.enabled:
            raise RuntimeError("Agent is disabled")

        task = AgentTask(
            description=description,
            objective=objective,
            assigned_agent=assigned_agent,
            required_capabilities=list(spec.capabilities),
            risk=RiskTier.READ_ONLY,
            budget=spec.default_budget,
            inputs=dict(hints or {}),
        )
        self._active_tasks += 1
        try:
            return await self._execute_task(task)
        finally:
            self._active_tasks -= 1

    async def _execute_task(self, task: AgentTask) -> AgentResult:
        assigned_agent = task.assigned_agent
        agent = self._agents[assigned_agent]
        await self._audit.append_async(EventType.TASK_CREATED, task_id=task.id, agent=assigned_agent,
                           data={"description": task.description, "objective": task.objective,
                               "graph_id": task.graph_id,
                               **({"repository": task.inputs.get("repository"), "files": task.inputs.get("files")}
                                if assigned_agent == "repo_reader" else {})})

        ctx = TaskContext(task=task, budget=BudgetTracker(task.budget, self._clock))
        task.status = TaskStatus.ASSIGNED
        await self._audit.append_async(EventType.TASK_ASSIGNED, task_id=task.id, agent=assigned_agent, data={})
        self._broker.register_task(ctx)

        async def execute() -> AgentResult:
            async with self._agent_slots[assigned_agent], self._slots:
                if self._halted:
                    raise asyncio.CancelledError()
                task.status = TaskStatus.RUNNING
                await self._audit.append_async(EventType.TASK_STARTED, task_id=task.id, agent=assigned_agent, data={})
                if self._halted or ctx.cancelled:
                    raise asyncio.CancelledError()
                return await agent.run(task)

        execution = asyncio.create_task(execute(), name=task.id)
        self._running[task.id] = execution
        try:
            async with asyncio.timeout(task.budget.wall_clock_ms / 1000):
                result = await execution
        except asyncio.CancelledError:
            self._broker.cancel_task(task.id)
            task.status = TaskStatus.CANCELLED
            await self._audit.append_async(EventType.TASK_CANCELLED, task_id=task.id, agent=assigned_agent,
                               data={"reason": "cancelled"})
            if not self._halted:
                raise
            return AgentResult(task_id=task.id, agent=assigned_agent, status=ResultStatus.FAILED,
                               summary="Task cancelled by the user.",
                               errors=["CANCELLED"], cost=self._cost(ctx))
        except TimeoutError:
            self._broker.cancel_task(task.id)
            task.status = TaskStatus.TIMED_OUT
            await self._audit.append_async(EventType.TASK_TIMED_OUT, task_id=task.id, agent=assigned_agent,
                               data={}, severity=Severity.HIGH)
            self._broker.unregister_task(task.id)
            return AgentResult(task_id=task.id, agent=assigned_agent, status=ResultStatus.FAILED,
                               summary="Task exceeded its wall-clock budget.",
                               errors=["TIMED_OUT"], cost=self._cost(ctx))
        except Exception as error:
            task.status = TaskStatus.FAILED
            reason = ("BUDGET_EXCEEDED" if isinstance(error, BudgetExceededError)
                      else str(error) if isinstance(error, ModelResponseError) and str(error) in MODEL_FAILURE_MESSAGES
                      else type(error).__name__)
            await self._audit.append_async(EventType.TASK_FAILED, task_id=task.id, agent=assigned_agent,
                               data={"reason": reason}, severity=Severity.HIGH)
            return AgentResult(task_id=task.id, agent=assigned_agent, status=ResultStatus.FAILED,
                               summary="Task failed during execution.",
                               errors=[reason], cost=self._cost(ctx))
        finally:
            self._running.pop(task.id, None)
            self._broker.unregister_task(task.id)

        result.cost = self._cost(ctx)
        if ctx.cancelled:
            result.status = ResultStatus.FAILED
            result.errors.append("BUDGET_EXCEEDED")
        await self._verify(task, result)
        self._broker.unregister_task(task.id)
        return result

    async def run_graph(self, plan: GraphPlan,
                        context: InvocationContext = InvocationContext.HUMAN) -> GraphResult:
        if self._halted:
            raise RuntimeError("Agent runtime is halted")

        async def run_node(node: Node, inputs: dict[str, BoundOutput],
                           token: CancellationToken) -> AgentResult:
            token.check()
            task = AgentTask(
                description=node.description, objective=node.objective, assigned_agent=node.agent,
                required_capabilities=list(node.capabilities), risk=node.risk,
                budget=TaskBudget(**node.budget.model_dump()), graph_id=executor.graph_id,
                inputs={"query": node.description,
                    "repository": node.repository, "files": node.files,
                    "research_role": node.name.casefold(),
                        "upstream": {key: value.model_dump() for key, value in inputs.items()}},
            )
            await self._audit.append_async(EventType.TASK_ASSIGNED, task_id=task.id, agent=node.agent,
                               data={"graph_id": executor.graph_id, "node_id": node.id, "name": node.name})
            return await self._execute_task(task)

        executor = GraphExecutor(self._registry, run_node, self._audit, clock=self._clock)
        self._graphs[executor.graph_id] = executor
        final_status = "FAILED"
        try:
            result = await executor.run(plan, context)
            final_status = result.status
            return result
        finally:
            snapshot = executor.snapshot()
            snapshot["status"] = final_status
            self._graph_history.appendleft(snapshot)
            self._graphs.pop(executor.graph_id, None)

    def graph_status(self) -> list[dict[str, object]]:
        return [executor.snapshot() for executor in self._graphs.values()]

    def runtime_status(self) -> dict[str, object]:
        """Read-only operational projection; excludes prompts, outputs and evidence."""
        graphs = [{**executor.snapshot(), "status": "RUNNING"} for executor in self._graphs.values()]
        graphs.extend(deepcopy(list(self._graph_history)))
        return {
            "state": "HALTED" if self._halted else "READY",
            "history_limit": self._graph_history.maxlen,
            "agents": [{"id": name, "enabled": self._registry.get(name).enabled,
                        "concurrency_limit": self._registry.get(name).concurrency_limit,
                        "capabilities": list(self._registry.get(name).capabilities),
                        "risk": str(self._registry.get(name).max_risk)} for name in self._registry.names()],
            "graphs": graphs,
        }

    async def _verify(self, task: AgentTask, result: AgentResult) -> None:
        task.status = TaskStatus.VERIFYING
        await self._audit.append_async(EventType.TASK_VERIFYING, task_id=task.id, agent=result.agent, data={})

        cited = self._cited_ids(result)

        # (I16) any cited id absent from the ledger => fabrication. Never trust it.
        fabricated = [eid for eid in cited if not self._ledger.contains(task.id, eid)
                  or self._ledger.get(task.id, eid).kind == "image_reference"]
        if fabricated:
            result.status = ResultStatus.FAILED
            result.errors.append(f"FABRICATED_EVIDENCE: {fabricated}")
            await self._audit.append_async(EventType.FABRICATED_EVIDENCE, task_id=task.id, agent=result.agent,
                               data={"evidence_ids": fabricated}, severity=Severity.HIGH)
            task.status = TaskStatus.FAILED
            await self._audit.append_async(EventType.TASK_FAILED, task_id=task.id, agent=result.agent,
                               data={"reason": "fabricated_evidence"}, severity=Severity.HIGH)
            return

        # Attach the resolved, runtime-minted evidence (never agent-authored).
        result.evidence = [self._ledger.get(task.id, eid) for eid in cited]

        # SUCCESS must be backed by real evidence; PARTIAL-with-empty is valid (4D).
        if result.status == ResultStatus.SUCCESS and not result.evidence:
            result.status = ResultStatus.FAILED
            result.errors.append("SUCCESS with empty evidence is rejected")
            task.status = TaskStatus.FAILED
            await self._audit.append_async(EventType.TASK_FAILED, task_id=task.id, agent=result.agent,
                               data={"reason": "empty_evidence"}, severity=Severity.HIGH)
            return

        if result.status == ResultStatus.FAILED:
            task.status = TaskStatus.FAILED
            await self._audit.append_async(EventType.TASK_FAILED, task_id=task.id, agent=result.agent,
                               data={"errors": result.errors})
            return

        result.media = [item for item in self._ledger.all_for(task.id) if item.kind == "image_reference"]
        task.status = TaskStatus.COMPLETED
        await self._audit.append_async(EventType.TASK_COMPLETED, task_id=task.id, agent=result.agent,
                           data={"status": str(result.status),
                                 "evidence_count": len(result.evidence)})

    @staticmethod
    def _cited_ids(result: AgentResult) -> list[str]:
        ids: list[str] = []
        for claim in result.payload.get("claims", []) or []:
            ids.extend(claim.get("evidence_ids", []) or [])
        # de-dupe, preserve order
        seen: set[str] = set()
        return [i for i in ids if not (i in seen or seen.add(i))]

    def _cost(self, ctx: TaskContext) -> CostRecord:
        b = ctx.budget
        return CostRecord(wall_clock_ms=int(b.elapsed_ms()), tool_calls=b.tool_calls,
                          llm_tokens=b.llm_tokens, usd=b.usd, retries=b.retries)

    async def halt_all(self, reason: str) -> None:
        """Global kill switch (Constitution I12)."""
        self._halted = True
        for executor in tuple(self._graphs.values()):
            executor.cancel(reason)
        for task_id, execution in tuple(self._running.items()):
            self._broker.cancel_task(task_id)
            execution.cancel()
        await self._audit.append_async(EventType.HALT_ALL, task_id=None, agent=None,
                           data={"reason": reason}, severity=Severity.HIGH)

    async def close(self) -> None:
        if self._active_tasks or self._running or self._graphs:
            raise RuntimeError("Await active tasks and graphs before closing the runtime")
        self._halted = True
        await self._audit.close()
