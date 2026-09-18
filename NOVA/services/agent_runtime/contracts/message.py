"""Structured inter-agent message (inert data; agents never spawn agents — I5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from services.agent_runtime.ids import new_id


@dataclass(frozen=True)
class AgentMessage:
    from_agent: str
    to_agent: str | None
    task_id: str
    kind: str                 # e.g. "suggested_followup" | "note"
    payload: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: new_id("msg"))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
