from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Set


class Collector(Protocol):
    name: str
    interval: int
    cost: int
    zones: Set[str]

    def collect(self) -> dict[str, Any]: ...


@dataclass(slots=True)
class CollectorRunResult:
    collector: str
    ok: bool
    data: dict[str, Any]
    error: str | None = None
    duration_ms: int = 0
