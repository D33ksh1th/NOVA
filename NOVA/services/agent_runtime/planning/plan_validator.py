from __future__ import annotations

from pydantic import ValidationError

from services.agent_runtime.contracts.event import EventType, Severity
from services.agent_runtime.events.audit import AuditLog
from services.agent_runtime.exceptions import PolicyError
from services.agent_runtime.graph.task_graph import (
    GraphError, GraphLimits, GraphPlan, InvocationContext, validate_policy,
)
from services.agent_runtime.registry import AgentRegistry


class PlanRejected(ValueError):
    def __init__(self, reason: str, repairable: bool = False) -> None:
        self.reason = reason
        self.repairable = repairable
        super().__init__(reason)


class PlanValidator:
    def __init__(self, registry: AgentRegistry, audit: AuditLog, limits: GraphLimits | None = None) -> None:
        self.registry = registry
        self.audit = audit
        self.limits = limits or GraphLimits()

    def validate(self, raw: str, context: InvocationContext) -> GraphPlan:
        try:
            plan = self._validate(raw, context)
        except PlanRejected as error:
            self.audit.append(EventType.PLAN_REJECTED, data={"reason_code": error.reason}, severity=Severity.HIGH)
            raise
        self.audit.append(EventType.PLAN_ACCEPTED, data={"node_count": len(plan.nodes), "context": context})
        return plan

    async def validate_async(self, raw: str, context: InvocationContext) -> GraphPlan:
        try:
            plan = self._validate(raw, context)
        except PlanRejected as error:
            await self.audit.append_async(EventType.PLAN_REJECTED, data={"reason_code": error.reason}, severity=Severity.HIGH)
            raise
        await self.audit.append_async(EventType.PLAN_ACCEPTED, data={"node_count": len(plan.nodes), "context": context})
        return plan

    def _validate(self, raw: str, context: InvocationContext) -> GraphPlan:
        if not isinstance(raw, str) or len(raw.encode("utf-8")) > 131072:
            raise PlanRejected("PLAN_SIZE_OR_TYPE")
        try:
            plan = GraphPlan.model_validate_json(raw)
        except ValidationError as error:
            errors = error.errors(include_input=False, include_context=False, include_url=False)
            semantic = any(item["type"] == "value_error" for item in errors)
            raise PlanRejected("GRAPH_INVALID" if semantic else "SCHEMA_INVALID", not semantic) from error
        try:
            validate_policy(plan, self.registry, context, self.limits)
        except (GraphError, PolicyError) as error:
            raise PlanRejected(getattr(error, "reason", type(error).__name__)) from error
        return plan