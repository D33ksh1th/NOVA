"""Notification policy engine.

Scores events, enforces DND, batches low-priority items, and gates
delivery on user presence. Every proactive utterance flows through here.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from packages.common import logger
from packages.events import bus, Event, EventEnvelope


@dataclass
class NotificationItem:
    event_type: str
    source: str
    summary: str
    severity: int = 0
    score: float = 0.0
    timestamp: float = field(default_factory=time.time)
    payload: Dict[str, Any] = field(default_factory=dict)
    spoken: bool = False
    dismissed: bool = False


# Score weights
W_IMPORTANCE = 0.4
W_URGENCY = 0.3
W_RECENCY = 0.2
W_INTERRUPTION_PENALTY = 0.1

# DND defaults (24h clock)
DEFAULT_DND_START = 23  # 11 PM
DEFAULT_DND_END = 7     # 7 AM

# Batching
BATCH_WINDOW_SECONDS = 120  # batch low-priority items within 2 min
MAX_INTERRUPTIONS_PER_HOUR = 8


class NotificationPolicy:

    def __init__(
        self,
        presence_fn: Optional[Callable[[], bool]] = None,
        speak_fn: Optional[Callable[[str], None]] = None,
    ):
        self._presence_fn = presence_fn or (lambda: True)
        self._speak_fn = speak_fn
        self._queue: deque[NotificationItem] = deque(maxlen=200)
        self._batch_buffer: List[NotificationItem] = []
        self._last_batch_flush = time.time()
        self._interruption_log: deque[float] = deque(maxlen=100)
        self._dnd_start = DEFAULT_DND_START
        self._dnd_end = DEFAULT_DND_END
        self._dnd_override = False
        self._feedback: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._running = True

        # Start batch flusher
        self._flush_thread = threading.Thread(
            target=self._batch_flush_loop, daemon=True, name="notif-batch-flush",
        )
        self._flush_thread.start()

        # Subscribe to key events
        bus.subscribe("nova.mail.>", self._on_mail)
        bus.subscribe("nova.security.anomaly", self._on_security)
        bus.subscribe("nova.security.scan_completed", self._on_scan_complete)

    def _on_mail(self, env: EventEnvelope) -> None:
        payload = env.payload or {}
        sender = str(payload.get("from", "unknown"))
        subject = str(payload.get("subject", "(no subject)"))
        urgency = str(payload.get("urgency", "normal"))
        severity = {"critical": 4, "high": 3, "normal": 1, "low": 0}.get(urgency, 1)
        item = NotificationItem(
            event_type=env.type,
            source="gmail",
            summary=f"Mail from {sender}: {subject}",
            severity=severity,
            payload=payload,
        )
        self._enqueue(item)

    def _on_security(self, env: EventEnvelope) -> None:
        payload = env.payload or {}
        item = NotificationItem(
            event_type=env.type,
            source="security",
            summary=str(payload.get("title", "Security anomaly detected")),
            severity=env.severity,
            payload=payload,
        )
        self._enqueue(item)

    def _on_scan_complete(self, env: EventEnvelope) -> None:
        payload = env.payload or {}
        findings = payload.get("findings", 0)
        if findings > 0:
            item = NotificationItem(
                event_type=env.type,
                source="security",
                summary=f"Security scan complete: {findings} finding(s)",
                severity=2,
                payload=payload,
            )
            self._enqueue(item)

    def _enqueue(self, item: NotificationItem) -> None:
        item.score = self._score(item)
        with self._lock:
            if item.severity >= 3:
                # High severity → deliver immediately
                self._deliver(item)
            else:
                # Low/medium → batch
                self._batch_buffer.append(item)
            self._queue.append(item)

    def _score(self, item: NotificationItem) -> float:
        importance = item.severity / 4.0
        urgency = min(1.0, item.severity / 3.0)
        recency = max(0, 1.0 - (time.time() - item.timestamp) / 300)
        interruption_penalty = self._recent_interruption_rate()
        return (
            W_IMPORTANCE * importance
            + W_URGENCY * urgency
            + W_RECENCY * recency
            - W_INTERRUPTION_PENALTY * interruption_penalty
        )

    def _recent_interruption_rate(self) -> float:
        now = time.time()
        recent = sum(1 for t in self._interruption_log if now - t < 3600)
        return min(1.0, recent / MAX_INTERRUPTIONS_PER_HOUR)

    def _is_dnd(self) -> bool:
        if self._dnd_override:
            return True
        hour = int(time.strftime("%H"))
        if self._dnd_start > self._dnd_end:
            return hour >= self._dnd_start or hour < self._dnd_end
        return self._dnd_start <= hour < self._dnd_end

    def _is_present(self) -> bool:
        try:
            return self._presence_fn()
        except Exception:
            return True

    def _deliver(self, item: NotificationItem) -> None:
        if self._is_dnd() and item.severity < 4:
            logger.info(f"NotificationPolicy: suppressed during DND | {item.summary[:60]}")
            return

        if not self._is_present() and item.severity < 3:
            logger.info(f"NotificationPolicy: suppressed (not present) | {item.summary[:60]}")
            return

        self._interruption_log.append(time.time())
        item.spoken = True

        if self._speak_fn:
            try:
                self._speak_fn(item.summary)
            except Exception as ex:
                logger.error(f"NotificationPolicy: speak failed: {ex}")

        bus.emit(
            "nova.notification.delivered",
            source="notification-policy",
            payload={"summary": item.summary, "severity": item.severity, "source": item.source},
            severity=item.severity,
        )
        logger.info(f"NotificationPolicy: delivered | {item.summary[:80]} (score={item.score:.2f})")

    def _batch_flush_loop(self) -> None:
        while self._running:
            time.sleep(10)
            with self._lock:
                if not self._batch_buffer:
                    continue
                if time.time() - self._last_batch_flush < BATCH_WINDOW_SECONDS:
                    continue
                self._flush_batch()

    def _flush_batch(self) -> None:
        if not self._batch_buffer:
            return
        items = list(self._batch_buffer)
        self._batch_buffer.clear()
        self._last_batch_flush = time.time()

        # Group by source
        by_source: Dict[str, List[NotificationItem]] = {}
        for item in items:
            by_source.setdefault(item.source, []).append(item)

        parts = []
        for source, group in by_source.items():
            if len(group) == 1:
                parts.append(group[0].summary)
            else:
                parts.append(f"{len(group)} {source} notifications")

        summary = ". ".join(parts) + "."
        batch_item = NotificationItem(
            event_type="nova.notification.batch",
            source="batch",
            summary=summary,
            severity=max(i.severity for i in items),
        )
        self._deliver(batch_item)

    # Public API

    def set_dnd(self, enabled: bool) -> None:
        self._dnd_override = enabled
        logger.info(f"NotificationPolicy: DND {'enabled' if enabled else 'disabled'}")

    def set_dnd_hours(self, start: int, end: int) -> None:
        self._dnd_start = max(0, min(23, start))
        self._dnd_end = max(0, min(23, end))

    def record_feedback(self, engaged: bool) -> None:
        self._feedback.append({"engaged": engaged, "ts": time.time()})

    def recent_notifications(self, limit: int = 20) -> List[Dict[str, Any]]:
        return [
            {
                "summary": item.summary,
                "source": item.source,
                "severity": item.severity,
                "score": round(item.score, 2),
                "spoken": item.spoken,
                "timestamp": item.timestamp,
            }
            for item in list(self._queue)[-limit:]
        ]

    def stats(self) -> Dict[str, Any]:
        now = time.time()
        return {
            "queued": len(self._queue),
            "batch_pending": len(self._batch_buffer),
            "interruptions_last_hour": sum(1 for t in self._interruption_log if now - t < 3600),
            "dnd_active": self._is_dnd(),
            "dnd_hours": f"{self._dnd_start}:00-{self._dnd_end}:00",
            "present": self._is_present(),
        }

    def stop(self) -> None:
        self._running = False
