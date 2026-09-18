from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal


RiskLevel = Literal["low", "medium", "high", "critical"]
CollectorState = Literal["planned", "ready", "monitoring", "degraded", "disabled"]


@dataclass
class SecurityFinding:
    id: str
    source: str
    title: str
    summary: str
    risk: RiskLevel
    confidence: float = 0.0
    tags: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TimelineEvent:
    id: str
    category: str
    title: str
    detail: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    related_finding_id: str | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SecurityCollectorStatus:
    name: str
    state: CollectorState
    coverage: List[str] = field(default_factory=list)
    description: str = ""
    platform: str = "macOS"
    last_heartbeat: str | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
