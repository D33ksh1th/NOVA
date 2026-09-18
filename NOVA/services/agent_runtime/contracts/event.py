"""Audit event contracts (Constitution I8). Events are append-only and
hash-chained by the audit writer; this module only defines their shape."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum

from services.agent_runtime.ids import new_id


class EventType(StrEnum):
    TASK_CREATED = "TASK_CREATED"
    TASK_ASSIGNED = "TASK_ASSIGNED"
    TASK_STARTED = "TASK_STARTED"
    PLAN_PROPOSED = "PLAN_PROPOSED"
    PLAN_ACCEPTED = "PLAN_ACCEPTED"
    PLAN_REJECTED = "PLAN_REJECTED"
    GRAPH_STARTED = "GRAPH_STARTED"
    GRAPH_NODE_STATE = "GRAPH_NODE_STATE"
    GRAPH_COMPLETED = "GRAPH_COMPLETED"
    GRAPH_CANCELLED = "GRAPH_CANCELLED"
    GRAPH_FAILED = "GRAPH_FAILED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    CIRCUIT_OPENED = "CIRCUIT_OPENED"
    TOOL_INVOKED = "TOOL_INVOKED"
    TOOL_RETURNED = "TOOL_RETURNED"
    TOOL_DENIED = "TOOL_DENIED"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPROVAL_GRANTED = "APPROVAL_GRANTED"
    APPROVAL_DENIED = "APPROVAL_DENIED"
    EVIDENCE_RECORDED = "EVIDENCE_RECORDED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    MODEL_USAGE = "MODEL_USAGE"
    MODEL_REQUESTED = "MODEL_REQUESTED"
    MODEL_FAILED = "MODEL_FAILED"
    TASK_VERIFYING = "TASK_VERIFYING"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    TASK_CANCELLED = "TASK_CANCELLED"
    TASK_TIMED_OUT = "TASK_TIMED_OUT"
    FABRICATED_EVIDENCE = "FABRICATED_EVIDENCE"
    HALT_ALL = "HALT_ALL"


class Severity(StrEnum):
    INFO = "INFO"
    WARN = "WARN"
    HIGH = "HIGH"


@dataclass(frozen=True)
class AgentEvent:
    seq: int
    type: EventType
    task_id: str | None
    agent: str | None
    data: dict
    prev_hash: str
    self_hash: str
    severity: Severity = Severity.INFO
    event_id: str = field(default_factory=lambda: new_id("evt"))
    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
