from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from typing import Any, Iterable

from .base import Collector, CollectorRunResult


@dataclass(slots=True)
class CollectorState:
    last_run_at: float = 0.0
    last_ok: bool = False


class CollectorScheduler:
    def __init__(self, collectors: Iterable[Collector], budget: int = 20, timeout_seconds: int = 30):
        self.collectors = list(collectors)
        self.budget = max(1, int(budget))
        self.timeout_seconds = max(1, int(timeout_seconds))
        self._state: dict[str, CollectorState] = {collector.name: CollectorState() for collector in self.collectors}
        self._results: dict[str, CollectorRunResult] = {}

    def _is_due(self, collector: Collector, now: float) -> bool:
        state = self._state[collector.name]
        return state.last_run_at <= 0 or (now - state.last_run_at) >= max(1, int(collector.interval))

    def _run_one(self, collector: Collector) -> CollectorRunResult:
        start = time.time()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(collector.collect)
            try:
                data = future.result(timeout=self.timeout_seconds)
                duration = int((time.time() - start) * 1000)
                if not isinstance(data, dict):
                    return CollectorRunResult(
                        collector=collector.name,
                        ok=False,
                        data={},
                        error="collector returned non-dict payload",
                        duration_ms=duration,
                    )
                return CollectorRunResult(
                    collector=collector.name,
                    ok=True,
                    data=data,
                    duration_ms=duration,
                )
            except TimeoutError:
                duration = int((time.time() - start) * 1000)
                return CollectorRunResult(
                    collector=collector.name,
                    ok=False,
                    data={},
                    error=f"collector timed out after {self.timeout_seconds}s",
                    duration_ms=duration,
                )
            except Exception as exc:
                duration = int((time.time() - start) * 1000)
                return CollectorRunResult(
                    collector=collector.name,
                    ok=False,
                    data={},
                    error=str(exc),
                    duration_ms=duration,
                )

    def collect_due(self) -> list[CollectorRunResult]:
        now = time.time()
        due = [collector for collector in self.collectors if self._is_due(collector, now)]
        due.sort(key=lambda item: (item.interval, item.cost))

        budget_left = self.budget
        ran: list[CollectorRunResult] = []
        for collector in due:
            if collector.cost > budget_left:
                continue
            result = self._run_one(collector)
            self._results[collector.name] = result
            self._state[collector.name] = CollectorState(last_run_at=now, last_ok=result.ok)
            ran.append(result)
            budget_left -= max(1, int(collector.cost))

        return ran

    def latest_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        failures: list[dict[str, Any]] = []
        for name, result in self._results.items():
            if result.ok:
                payload[name] = result.data
            else:
                failures.append(
                    {
                        "collector": name,
                        "ok": False,
                        "error": result.error or "collector failed",
                        "duration_ms": result.duration_ms,
                    }
                )
        if failures:
            payload["collector_failures"] = failures
        return payload
