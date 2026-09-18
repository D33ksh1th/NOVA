"""Task contracts: AgentTask, TaskStatus, TaskBudget, RiskTier."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum

from services.agent_runtime.ids import new_id


class TaskStatus(StrEnum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    ASSIGNED = "ASSIGNED"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    BLOCKED = "BLOCKED"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


class RiskTier(StrEnum):
    READ_ONLY = "READ_ONLY"  # no state change anywhere
    LOW = "LOW"              # local, reversible, no external effect
    MEDIUM = "MEDIUM"        # writes code/config, installs packages
    HIGH = "HIGH"            # destructive, security-changing, or externally visible


_RISK_ORDER = {
    RiskTier.READ_ONLY: 0,
    RiskTier.LOW: 1,
    RiskTier.MEDIUM: 2,
    RiskTier.HIGH: 3,
}


def risk_rank(tier: RiskTier) -> int:
    return _RISK_ORDER[RiskTier(tier)]


def risk_at_most(candidate: RiskTier, ceiling: RiskTier) -> bool:
    return risk_rank(candidate) <= risk_rank(ceiling)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class TaskBudget:
    wall_clock_ms: int
    max_tool_calls: int
    max_llm_tokens: int
    max_usd: float
    max_retries: int


@dataclass
class AgentTask:
    description: str          # human intent, not raw user text passed through
    objective: str           # machine-checkable success condition
    assigned_agent: str
    required_capabilities: list[str]
    risk: RiskTier
    budget: TaskBudget
    inputs: dict = field(default_factory=dict)   # already sanitized, no secrets (I10)
    depends_on: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: new_id("t"))
    graph_id: str | None = None
    parent_id: str | None = None
    status: TaskStatus = TaskStatus.CREATED
    created_at: datetime = field(default_factory=_now)
    deadline_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.deadline_at is None:
            self.deadline_at = self.created_at + timedelta(
                milliseconds=self.budget.wall_clock_ms
            )
