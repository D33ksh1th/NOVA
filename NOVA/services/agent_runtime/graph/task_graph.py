from __future__ import annotations

from enum import StrEnum
from graphlib import CycleError, TopologicalSorter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from services.agent_runtime.contracts.task import RiskTier
from services.agent_runtime.registry import AgentRegistry


class GraphError(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Budget(Contract):
    wall_clock_ms: int = Field(gt=0, strict=True)
    max_tool_calls: int = Field(ge=0, strict=True)
    max_llm_tokens: int = Field(ge=0, strict=True)
    max_usd: float = Field(ge=0, allow_inf_nan=False)
    max_retries: int = Field(ge=0, strict=True)


class FailureMode(StrEnum):
    FAIL_GRAPH = "FAIL_GRAPH"
    SKIP_DOWNSTREAM = "SKIP_DOWNSTREAM"
    CONTINUE = "CONTINUE"


class Edge(Contract):
    task_id: str = Field(min_length=1)
    on_failure: FailureMode


class OutputBinding(Contract):
    task_id: str = Field(min_length=1)
    key: str = Field(min_length=1)
    input_key: str = Field(min_length=1)


class RetryPolicy(Contract):
    max_attempts: int = Field(default=1, ge=1, le=5, strict=True)
    base_delay_ms: int = Field(default=100, ge=0, le=10000, strict=True)
    max_delay_ms: int = Field(default=1000, ge=0, le=30000, strict=True)


class Node(Contract):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    name: str = Field(min_length=1, max_length=80)
    agent: str
    description: str = Field(min_length=1, max_length=2048)
    objective: str = Field(min_length=1, max_length=2048)
    capabilities: tuple[str, ...]
    tools: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    risk: RiskTier
    budget: Budget
    depends_on: tuple[Edge, ...] = ()
    consumes: tuple[OutputBinding, ...] = ()
    priority: int = Field(default=0, ge=0, le=10, strict=True)
    retry: RetryPolicy = Field(default_factory=RetryPolicy)
    repository: Literal["nova-desktop"] | None = None
    files: tuple[str, ...] = Field(default=(), max_length=3)


class GraphPlan(Contract):
    goal: str = Field(min_length=1, max_length=2048)
    budget: Budget
    nodes: tuple[Node, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def check_graph(self) -> GraphPlan:
        lookup = {node.id: node for node in self.nodes}
        if len(lookup) != len(self.nodes):
            raise GraphError("DUPLICATE_NODE")
        for node in self.nodes:
            parents = [edge.task_id for edge in node.depends_on]
            if len(set(parents)) != len(parents):
                raise GraphError("DUPLICATE_EDGE")
            if any(parent not in lookup for parent in parents):
                raise GraphError("UNKNOWN_DEPENDENCY")
            keys = [binding.input_key for binding in node.consumes]
            if len(set(keys)) != len(keys):
                raise GraphError("DUPLICATE_INPUT")
            if any(binding.task_id not in parents for binding in node.consumes):
                raise GraphError("UNDECLARED_DATA_EDGE")
            if node.retry.max_attempts - 1 > node.budget.max_retries:
                raise GraphError("TASK_RETRY_BUDGET")
        self.layers()
        for dimension in Budget.model_fields:
            total = sum(getattr(node.budget, dimension) for node in self.nodes)
            if total > getattr(self.budget, dimension) + (1e-9 if dimension == "max_usd" else 0):
                raise GraphError("GRAPH_BUDGET_SUM:" + dimension)
        return self

    def layers(self) -> tuple[tuple[str, ...], ...]:
        sorter = TopologicalSorter({
            node.id: {edge.task_id for edge in node.depends_on} for node in self.nodes
        })
        try:
            sorter.prepare()
        except CycleError as error:
            raise GraphError("CYCLE") from error
        layers: list[tuple[str, ...]] = []
        while sorter.is_active():
            ready = tuple(sorter.get_ready())
            layers.append(ready)
            sorter.done(*ready)
        if len(layers) > 6:
            raise GraphError("MAX_DEPTH")
        return tuple(layers)


class InvocationContext(StrEnum):
    HUMAN = "HUMAN"
    INITIATIVE = "INITIATIVE"


class GraphLimits(Contract):
    max_nodes: int = Field(default=32, ge=1, le=32)
    max_depth: int = Field(default=6, ge=1, le=6)
    max_parallel: int = Field(default=4, ge=1, le=4)
    max_graph_wall_clock_ms: int = Field(default=480000, gt=0)
    max_graph_usd: float = Field(default=2.0, ge=0, allow_inf_nan=False)


class BoundOutput(Contract):
    task_id: str
    key: str
    content: str
    trust: Literal["untrusted"] = "untrusted"


def validate_policy(
    plan: GraphPlan, registry: AgentRegistry,
    context: InvocationContext, limits: GraphLimits,
) -> None:
    from services.agent_runtime.contracts.task import risk_at_most

    if len(plan.nodes) > limits.max_nodes or len(plan.layers()) > limits.max_depth:
        raise GraphError("GRAPH_LIMIT")
    if (plan.budget.wall_clock_ms > limits.max_graph_wall_clock_ms
            or plan.budget.max_usd > limits.max_graph_usd):
        raise GraphError("GRAPH_BUDGET_LIMIT")
    for node in plan.nodes:
        spec = registry.get(node.agent)
        if not spec.enabled:
            raise GraphError("AGENT_DISABLED")
        if context == InvocationContext.INITIATIVE and node.risk != RiskTier.READ_ONLY:
            raise GraphError("INITIATIVE_READ_ONLY")
        if not risk_at_most(node.risk, spec.max_risk):
            raise GraphError("RISK_EXCEEDS_AGENT")
        if not set(node.capabilities).issubset(spec.capabilities):
            raise GraphError("CAPABILITY_NOT_GRANTED")
        if not set(node.tools).issubset(spec.allowed_tools):
            raise GraphError("TOOL_NOT_GRANTED")
        if not set(node.skills).issubset(spec.skills):
            raise GraphError("SKILL_NOT_GRANTED")
        for dimension in Budget.model_fields:
            if getattr(node.budget, dimension) > getattr(spec.default_budget, dimension):
                raise GraphError("TASK_BUDGET_EXCEEDS_GRANT:" + dimension)