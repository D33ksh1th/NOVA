from __future__ import annotations

from collections import deque
from typing import Deque, List
from uuid import uuid4

from .types import TimelineEvent


class SecurityTimeline:
    def __init__(self, limit: int = 500):
        self._events: Deque[TimelineEvent] = deque(maxlen=limit)

    def add(self, category: str, title: str, detail: str, related_finding_id: str | None = None, **metadata):
        event = TimelineEvent(
            id=str(uuid4()),
            category=category,
            title=title,
            detail=detail,
            related_finding_id=related_finding_id,
            metadata=metadata,
        )
        self._events.appendleft(event)
        return event

    def list_recent(self, limit: int = 50) -> List[dict]:
        return [event.to_dict() for event in list(self._events)[:limit]]

    def restore(self, events: List[dict]) -> int:
        """Restore timeline from serialized events (newest first)."""
        self._events.clear()
        restored = 0
        for item in events or []:
            if not isinstance(item, dict):
                continue
            try:
                event = TimelineEvent(
                    id=str(item.get("id") or str(uuid4())),
                    category=str(item.get("category") or "security"),
                    title=str(item.get("title") or "Event"),
                    detail=str(item.get("detail") or ""),
                    timestamp=str(item.get("timestamp") or ""),
                    related_finding_id=item.get("related_finding_id"),
                    metadata=dict(item.get("metadata") or {}),
                )
                self._events.append(event)
                restored += 1
            except Exception:
                continue
        return restored
