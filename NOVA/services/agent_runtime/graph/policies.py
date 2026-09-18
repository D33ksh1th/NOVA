from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass, field
from random import Random

from services.agent_runtime.graph.task_graph import RetryPolicy


@dataclass
class CancellationToken:
    reason: str = ""
    _event: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self, reason: str) -> None:
        self.reason = reason
        self._event.set()

    def check(self) -> None:
        if self.cancelled:
            raise asyncio.CancelledError(self.reason)

    async def wait(self) -> None:
        await self._event.wait()


class CircuitBreaker:
    def __init__(self, threshold: int = 3, window_seconds: float = 60.0) -> None:
        if threshold < 1 or window_seconds <= 0:
            raise ValueError("Invalid circuit breaker limits")
        self.threshold = threshold
        self.window_seconds = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def is_open(self, agent: str, now: float) -> bool:
        history = self._failures[agent]
        while history and now - history[0] >= self.window_seconds:
            history.popleft()
        return len(history) >= self.threshold

    def failure(self, agent: str, now: float) -> bool:
        self._failures[agent].append(now)
        return self.is_open(agent, now)


def retry_delay(policy: RetryPolicy, attempt: int, random: Random) -> float:
    ceiling = min(policy.max_delay_ms, policy.base_delay_ms * 2 ** (attempt - 1))
    return random.uniform(0.5 * ceiling, ceiling) / 1000