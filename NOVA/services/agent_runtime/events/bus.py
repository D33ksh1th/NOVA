"""In-process async pub/sub bus for agent-runtime events (Constitution I13-friendly).

Deterministic and offline: subscribers are plain async callables invoked in
registration order. No threads, no network.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Awaitable, Callable

from services.agent_runtime.contracts.event import AgentEvent

Subscriber = Callable[[AgentEvent], Awaitable[None]]


class AsyncEventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Subscriber]] = defaultdict(list)
        self._all: list[Subscriber] = []

    def subscribe(self, event_type: str, handler: Subscriber) -> None:
        self._subs[event_type].append(handler)

    def subscribe_all(self, handler: Subscriber) -> None:
        self._all.append(handler)

    async def publish(self, event: AgentEvent) -> None:
        for handler in self._all:
            await handler(event)
        for handler in self._subs.get(str(event.type), []):
            await handler(event)
