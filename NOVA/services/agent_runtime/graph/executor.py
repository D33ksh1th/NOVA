from __future__ import annotations

import asyncio
import time
from collections import Counter
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from random import Random
from typing import Callable, Protocol

from services.agent_runtime.contracts.content import wrap_untrusted
from services.agent_runtime.contracts.event import EventType
from services.agent_runtime.contracts.result import AgentResult, CostRecord, ResultStatus
from services.agent_runtime.events.audit import AuditLog
from services.agent_runtime.graph.policies import CancellationToken, CircuitBreaker, retry_delay
from services.agent_runtime.graph.scheduler import Scheduler
from services.agent_runtime.graph.task_graph import (
    BoundOutput, FailureMode, GraphLimits, GraphPlan, InvocationContext, Node, validate_policy,
)
from services.agent_runtime.ids import new_id
from services.agent_runtime.policy.canonical import canonical_json
from services.agent_runtime.registry import AgentRegistry


class NodeState(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    RETRYING = "RETRYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


TERMINAL = {NodeState.COMPLETED, NodeState.FAILED, NodeState.SKIPPED, NodeState.CANCELLED}


class NodeRunner(Protocol):
    async def __call__(
        self, node: Node, inputs: dict[str, BoundOutput], token: CancellationToken,
    ) -> AgentResult: ...


@dataclass
class NodeRecord:
    id: str
    name: str
    agent: str
    depends_on: tuple[str, ...]
    state: NodeState = NodeState.QUEUED
    attempts: int = 0
    started_at: float | None = None
    finished_at: float | None = None
    reason: str = ""
    result_status: str | None = None


@dataclass
class GraphResult:
    graph_id: str
    status: str
    results: dict[str, AgentResult]
    gaps: dict[str, str]
    nodes: list[NodeRecord]
    elapsed_ms: int
    cost: CostRecord


class GraphExecutor:
    def __init__(
        self, registry: AgentRegistry, runner: NodeRunner, audit: AuditLog, *,
        limits: GraphLimits | None = None, clock: Callable[[], float] = time.monotonic,
        random: Random | None = None, breaker: CircuitBreaker | None = None,
    ) -> None:
        self.registry = registry
        self.runner = runner
        self.audit = audit
        self.limits = limits or GraphLimits()
        self.clock = clock
        self.random = random or Random()
        self.breaker = breaker or CircuitBreaker()
        self.graph_id = new_id("g")
        self.token = CancellationToken()
        self.records: dict[str, NodeRecord] = {}
        self._started: float | None = None
        self._finished: float | None = None
        self._used = False

    def cancel(self, reason: str) -> None:
        self.token.cancel(reason)

    def snapshot(self) -> dict[str, object]:
        terminal = sum(record.state in TERMINAL for record in self.records.values())
        successful = sum(record.state == NodeState.COMPLETED for record in self.records.values())
        total = len(self.records)
        return {
            "graph_id": self.graph_id, "nodes": [asdict(record) for record in self.records.values()],
            "finished_tasks": terminal, "completed_tasks": successful, "total_tasks": total,
            "finished_percent": round(100 * terminal / total, 1) if total else None,
            "successful_tasks": sum(record.state == NodeState.COMPLETED and record.result_status == ResultStatus.SUCCESS
                                    for record in self.records.values()),
            "completion_percent": round(100 * successful / total, 1) if total else None,
            "elapsed_ms": int(((self._finished if self._finished is not None else self.clock())
                               - self._started) * 1000) if self._started is not None else 0,
        }

    async def _state(self, node_id: str, state: NodeState, reason: str = "") -> None:
        record = self.records[node_id]
        record.state = state
        record.reason = reason
        if state == NodeState.RUNNING and record.started_at is None:
            record.started_at = self.clock()
        if state in TERMINAL:
            record.finished_at = self.clock()
        await self.audit.append_async(EventType.GRAPH_NODE_STATE, task_id=node_id, agent=record.agent,
                          data={"graph_id": self.graph_id, "state": state, "reason": reason,
                                "attempt": record.attempts})

    async def run(self, plan: GraphPlan, context: InvocationContext = InvocationContext.HUMAN) -> GraphResult:
        if self._used:
            raise RuntimeError("Graph executor is single-use")
        self._used = True
        validate_policy(plan, self.registry, context, self.limits)
        self._started = self.clock()
        self.records = {node.id: NodeRecord(node.id, node.name, node.agent,
                        tuple(edge.task_id for edge in node.depends_on)) for node in plan.nodes}
        await self.audit.append_async(EventType.GRAPH_STARTED, data={"graph_id": self.graph_id})
        lookup = {node.id: node for node in plan.nodes}
        queued_at = {node.id: self._started for node in plan.nodes}
        retry_at: dict[str, float] = {}
        results: dict[str, AgentResult] = {}
        running: dict[str, asyncio.Task[AgentResult]] = {}
        scheduler = Scheduler(self.limits.max_parallel)
        agent_limits = {node.agent: self.registry.get(node.agent).concurrency_limit for node in plan.nodes}
        spent = {node.id: CostRecord() for node in plan.nodes}
        retries = 0
        failure_reason = ""
        cancellation = asyncio.create_task(self.token.wait())

        async def invoke(node: Node, inputs: dict[str, BoundOutput]) -> AgentResult:
            self.token.check()
            started = self.clock()
            try:
                async with asyncio.timeout(node.budget.wall_clock_ms / 1000):
                    result = await self.runner(node, inputs, self.token)
            except Exception as error:
                result = AgentResult(task_id=node.id, agent=node.agent, status=ResultStatus.FAILED,
                                     summary="Task execution failed.", errors=[type(error).__name__])
            measured = int((self.clock() - started) * 1000)
            result.cost = replace(result.cost, wall_clock_ms=max(measured, result.cost.wall_clock_ms))
            return result

        try:
            async with asyncio.timeout(plan.budget.wall_clock_ms / 1000):
                while any(record.state not in TERMINAL for record in self.records.values()):
                    self.token.check()
                    ready: list[Node] = []
                    for node in plan.nodes:
                        record = self.records[node.id]
                        if record.state not in {NodeState.QUEUED, NodeState.RETRYING}:
                            continue
                        bad = [edge for edge in node.depends_on
                               if self.records[edge.task_id].state in TERMINAL
                               and self.records[edge.task_id].state != NodeState.COMPLETED]
                        if any(edge.on_failure == FailureMode.FAIL_GRAPH for edge in bad):
                            failure_reason = "UPSTREAM_FAILED"
                            self.token.cancel(failure_reason)
                            break
                        if any(edge.on_failure == FailureMode.SKIP_DOWNSTREAM for edge in bad):
                            await self._state(node.id, NodeState.SKIPPED, "UPSTREAM_FAILED")
                            continue
                        if any(self.records[edge.task_id].state not in TERMINAL for edge in node.depends_on):
                            continue
                        if self.breaker.is_open(node.agent, self.clock()):
                            await self._state(node.id, NodeState.FAILED, "CIRCUIT_OPEN")
                            continue
                        if retry_at.get(node.id, 0) <= self.clock():
                            ready.append(node)
                    self.token.check()
                    counts = dict(Counter(lookup[node_id].agent for node_id in running))
                    for node in scheduler.select(ready, counts, agent_limits, queued_at, self.clock()):
                        inputs: dict[str, BoundOutput] = {}
                        for binding in node.consumes:
                            upstream = results.get(binding.task_id)
                            if upstream is None or binding.key not in upstream.payload:
                                await self._state(node.id, NodeState.FAILED, "MISSING_UPSTREAM_OUTPUT")
                                break
                            inputs[binding.input_key] = BoundOutput(
                                task_id=upstream.task_id, key=binding.key,
                                content=wrap_untrusted(canonical_json(upstream.payload[binding.key]),
                                                       source=f"task:{upstream.task_id}", task=node.id),
                            )
                        else:
                            record = self.records[node.id]
                            record.attempts += 1
                            previous = spent[node.id]
                            remaining = node.budget.model_copy(update={
                                "wall_clock_ms": node.budget.wall_clock_ms - previous.wall_clock_ms,
                                "max_tool_calls": node.budget.max_tool_calls - previous.tool_calls,
                                "max_llm_tokens": node.budget.max_llm_tokens - previous.llm_tokens,
                                "max_usd": node.budget.max_usd - previous.usd,
                            })
                            if remaining.wall_clock_ms <= 0:
                                await self._state(node.id, NodeState.FAILED, "BUDGET_EXCEEDED")
                                failure_reason = "BUDGET_EXCEEDED"
                                self.token.cancel(failure_reason)
                                break
                            await self._state(node.id, NodeState.RUNNING)
                            self.token.check()
                            running[node.id] = asyncio.create_task(
                                invoke(node.model_copy(update={"budget": remaining}), inputs),
                                name=f"{self.graph_id}:{node.id}",
                            )
                    if not running:
                        future = [retry_at[node_id] for node_id, record in self.records.items()
                                  if record.state == NodeState.RETRYING and node_id in retry_at]
                        if future:
                            await asyncio.wait({cancellation}, timeout=max(0, min(future) - self.clock()))
                            continue
                        if all(record.state in TERMINAL for record in self.records.values()):
                            break
                        continue
                    done, pending = await asyncio.wait(
                        {*running.values(), cancellation}, return_when=asyncio.FIRST_COMPLETED,
                    )
                    self.token.check()
                    for node_id, execution in tuple(running.items()):
                        if execution not in done:
                            continue
                        del running[node_id]
                        node = lookup[node_id]
                        record = self.records[node_id]
                        try:
                            result = execution.result()
                        except Exception as error:
                            result = AgentResult(task_id=node_id, agent=node.agent, status=ResultStatus.FAILED,
                                                 summary="Task execution failed.", errors=[type(error).__name__])
                        results[node_id] = result
                        record.result_status = result.status
                        prior = spent[node_id]
                        spent[node_id] = CostRecord(
                            wall_clock_ms=prior.wall_clock_ms + result.cost.wall_clock_ms,
                            tool_calls=prior.tool_calls + result.cost.tool_calls,
                            llm_tokens=prior.llm_tokens + result.cost.llm_tokens,
                            usd=prior.usd + result.cost.usd,
                            retries=record.attempts - 1,
                        )
                        usage = spent[node_id]
                        exhausted = (usage.wall_clock_ms > node.budget.wall_clock_ms
                                     or usage.tool_calls > node.budget.max_tool_calls
                                     or usage.llm_tokens > node.budget.max_llm_tokens
                                     or usage.usd > node.budget.max_usd
                                     or any("BUDGET" in error for error in result.errors))
                        if exhausted:
                            failure_reason = "BUDGET_EXCEEDED"
                            await self._state(node_id, NodeState.FAILED, failure_reason)
                            self.token.cancel(failure_reason)
                            break
                        if result.status in {ResultStatus.SUCCESS, ResultStatus.PARTIAL}:
                            await self._state(node_id, NodeState.COMPLETED)
                            continue
                        opened = self.breaker.failure(node.agent, self.clock())
                        if opened:
                            await self.audit.append_async(EventType.CIRCUIT_OPENED, agent=node.agent,
                                              data={"graph_id": self.graph_id})
                        fatal = any("FABRICATED_EVIDENCE" in error or "MODEL_" in error
                                    or "ModelResponseError" in error for error in result.errors)
                        if (not opened and not fatal and result.status != ResultStatus.REFUSED
                                and record.attempts < node.retry.max_attempts):
                            if retries >= plan.budget.max_retries:
                                failure_reason = "RETRY_BUDGET_EXCEEDED"
                                self.token.cancel(failure_reason)
                                break
                            retries += 1
                            delay = retry_delay(node.retry, record.attempts, self.random)
                            retry_at[node_id] = self.clock() + delay
                            await self._state(node_id, NodeState.RETRYING)
                            await self.audit.append_async(EventType.RETRY_SCHEDULED, task_id=node_id, agent=node.agent,
                                              data={"graph_id": self.graph_id, "delay_ms": int(delay * 1000)})
                        else:
                            await self._state(node_id, NodeState.FAILED, "TASK_FAILED")
        except TimeoutError:
            failure_reason = "GRAPH_TIMED_OUT"
            self.token.cancel(failure_reason)
        except asyncio.CancelledError:
            self.token.cancel(self.token.reason or "CANCELLED")
        finally:
            for execution in running.values():
                execution.cancel()
            cancellation.cancel()
            await asyncio.gather(*running.values(), cancellation, return_exceptions=True)
            for node_id, record in self.records.items():
                if record.state not in TERMINAL:
                    await self._state(node_id, NodeState.CANCELLED, self.token.reason)

        gaps = {node_id: record.reason or record.state for node_id, record in self.records.items()
                if record.state != NodeState.COMPLETED}
        for node_id, result in results.items():
            if result.status == ResultStatus.PARTIAL:
                gaps[node_id] = "PARTIAL_RESULT"
        failed_nodes = any(record.state == NodeState.FAILED for record in self.records.values())
        status = ("FAILED" if failure_reason else "CANCELLED" if self.token.cancelled
              else "FAILED" if failed_nodes
                  else "PARTIAL" if gaps else "COMPLETED")
        self._finished = self.clock()
        elapsed = int((self._finished - self._started) * 1000)
        cost = CostRecord(elapsed, sum(value.tool_calls for value in spent.values()),
                          sum(value.llm_tokens for value in spent.values()),
                          sum(value.usd for value in spent.values()), retries)
        event_type = (EventType.GRAPH_FAILED if status == "FAILED" else EventType.GRAPH_CANCELLED
                      if status == "CANCELLED" else EventType.GRAPH_COMPLETED)
        await self.audit.append_async(event_type, data={"graph_id": self.graph_id, "status": status,
                                          "gaps": gaps, "cost": asdict(cost)})
        return GraphResult(self.graph_id, status, results, gaps, list(self.records.values()), elapsed, cost)