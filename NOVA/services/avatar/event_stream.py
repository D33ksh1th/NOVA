"""Avatar event stream for the Phase 2 macOS companion.

This service subscribes to internal NOVA bus events and exposes a simple
SSE-compatible queue model so external avatar clients can animate in real time.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Set

from packages.common import logger
from packages.events import Event, bus


class AvatarEventStream:
    """Collect and broadcast avatar animation events to subscribers."""

    def __init__(self, queue_size: int = 100, history_size: int = 100):
        self._queue_size = queue_size
        self._history_size = history_size
        self._subscribers: Set[asyncio.Queue] = set()
        self._history: List[Dict[str, Any]] = []
        self._current_state = "idle"
        self._bridge_registered = False

    def register_bridge(self) -> None:
        """Subscribe to core bus events once."""
        if self._bridge_registered:
            return

        bus.subscribe(Event.AVATAR_LISTENING_STARTED, lambda env: self.publish("listening_started", env.payload if hasattr(env, 'payload') else env))
        bus.subscribe(Event.AVATAR_LISTENING_COMPLETED, lambda env: self.publish("listening_completed", env.payload if hasattr(env, 'payload') else env))
        bus.subscribe(Event.AVATAR_THINKING_STARTED, lambda env: self.publish("thinking_started", env.payload if hasattr(env, 'payload') else env))
        bus.subscribe(Event.AVATAR_THINKING_COMPLETED, lambda env: self.publish("thinking_completed", env.payload if hasattr(env, 'payload') else env))
        bus.subscribe(Event.AVATAR_SPEAKING_STARTED, lambda env: self.publish("speaking_started", env.payload if hasattr(env, 'payload') else env))
        bus.subscribe(Event.AVATAR_SPEAKING_COMPLETED, lambda env: self.publish("speaking_completed", env.payload if hasattr(env, 'payload') else env))
        bus.subscribe(Event.AVATAR_IDLE, lambda env: self.publish("idle", env.payload if hasattr(env, 'payload') else env))
        bus.subscribe(Event.MAIL_RECEIVED, lambda env: self.publish("gmail_new_message", env.payload if hasattr(env, 'payload') else env))
        bus.subscribe(Event.MAIL_SEND_COMPLETED, lambda env: self.publish("gmail_send_completed", env.payload if hasattr(env, 'payload') else env))

        self._bridge_registered = True
        logger.info("AvatarEventStream bridge subscribed to bus events")

    def publish(self, event: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Publish an event to all active subscribers."""
        data = payload or {}
        timestamp = datetime.now(timezone.utc).isoformat()
        if event.endswith("_started"):
            self._current_state = event.replace("_started", "")
        elif event in {"listening_completed", "thinking_completed", "speaking_completed", "idle"}:
            self._current_state = "idle"

        envelope = {
            "event": event,
            "state": self._current_state,
            "timestamp": timestamp,
            "payload": data,
        }
        self._history.append(envelope)
        if len(self._history) > self._history_size:
            self._history.pop(0)

        sse_line = self._format_sse(envelope)
        for queue in list(self._subscribers):
            self._queue_put_latest(queue, sse_line)

        return envelope

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "state": self._current_state,
            "subscribers": len(self._subscribers),
            "history": self._history[-20:],
        }

    def _queue_put_latest(self, queue: asyncio.Queue, item: str) -> None:
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            queue.put_nowait(item)
        except asyncio.QueueFull:
            logger.warning("AvatarEventStream subscriber queue remained full; dropping event")

    def _format_sse(self, envelope: Dict[str, Any]) -> str:
        return f"event: {envelope['event']}\ndata: {json.dumps(envelope)}\n\n"
