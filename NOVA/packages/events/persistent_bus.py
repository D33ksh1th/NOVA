"""
Persistent event bus backed by SQLite.

Replaces the simple in-memory pub/sub with:
- Subject-wildcard matching (nova.mail.received matches nova.mail.> and nova.>)
- Persistent event log with replay from any sequence number
- Error isolation — one failing subscriber never blocks others
- Async publish via background thread (non-blocking for producers)

Drop-in replacement: existing code using bus.subscribe / bus.publish still works.
"""

from __future__ import annotations

import fnmatch
import json
import sqlite3
import threading
import time
from collections import defaultdict
from pathlib import Path
from queue import Queue, Empty
from typing import Any, Callable, Dict, List, Optional

from packages.common import logger
from packages.events.envelope import EventEnvelope


_DEFAULT_DB = Path.home() / ".nova" / "events.db"


class PersistentEventBus:

    def __init__(self, db_path: str | Path | None = None):
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._write_queue: Queue[EventEnvelope] = Queue()
        self._lock = threading.Lock()
        self._running = True
        self._init_db()
        self._writer_thread = threading.Thread(
            target=self._writer_loop, name="event-bus-writer", daemon=True
        )
        self._writer_thread.start()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=10)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS event_log (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    type TEXT NOT NULL,
                    ts TEXT NOT NULL,
                    severity INTEGER NOT NULL DEFAULT 0,
                    payload TEXT,
                    requires_speech INTEGER NOT NULL DEFAULT 0,
                    correlation_id TEXT,
                    created_at REAL NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_event_type ON event_log(type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_event_ts ON event_log(created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_event_correlation ON event_log(correlation_id)")

    def subscribe(self, event_pattern: str, callback: Callable) -> None:
        with self._lock:
            self._subscribers[event_pattern].append(callback)
        logger.info(f"Subscribed -> {event_pattern}")

    def publish(self, event: str | EventEnvelope, data: Any = None) -> EventEnvelope:
        if isinstance(event, str):
            envelope = EventEnvelope(
                source="legacy",
                type=event,
                payload=data,
            )
        else:
            envelope = event

        self._write_queue.put(envelope)
        self._dispatch(envelope)
        return envelope

    def emit(
        self,
        event_type: str,
        source: str,
        payload: Any = None,
        severity: int = 0,
        requires_speech: bool = False,
        correlation_id: str | None = None,
    ) -> EventEnvelope:
        envelope = EventEnvelope(
            source=source,
            type=event_type,
            payload=payload,
            severity=severity,
            requires_speech=requires_speech,
            correlation_id=correlation_id,
        )
        return self.publish(envelope)

    def _dispatch(self, envelope: EventEnvelope) -> None:
        with self._lock:
            patterns = list(self._subscribers.items())

        for pattern, callbacks in patterns:
            if not _subject_matches(pattern, envelope.type):
                continue
            for cb in callbacks:
                try:
                    cb(envelope)
                except Exception as exc:
                    logger.error(
                        f"Subscriber error on {envelope.type}: {exc}",
                    )

    def _writer_loop(self) -> None:
        while self._running:
            batch: list[EventEnvelope] = []
            try:
                batch.append(self._write_queue.get(timeout=0.5))
                while len(batch) < 100:
                    batch.append(self._write_queue.get_nowait())
            except Empty:
                pass
            if not batch:
                continue
            try:
                with self._connect() as conn:
                    conn.executemany(
                        """INSERT INTO event_log
                           (id, source, type, ts, severity, payload, requires_speech, correlation_id, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        [
                            (
                                e.id,
                                e.source,
                                e.type,
                                e.ts,
                                e.severity,
                                json.dumps(e.payload) if e.payload is not None else None,
                                1 if e.requires_speech else 0,
                                e.correlation_id,
                                time.time(),
                            )
                            for e in batch
                        ],
                    )
            except Exception as exc:
                logger.error(f"Event persistence failed: {exc}")

    def replay(
        self,
        event_type: str | None = None,
        since_seq: int = 0,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        query = "SELECT seq, id, source, type, ts, severity, payload, requires_speech, correlation_id FROM event_log WHERE seq > ?"
        params: list[Any] = [since_seq]
        if event_type:
            query += " AND type LIKE ?"
            params.append(event_type.replace(">", "%").replace("*", "%"))
        query += " ORDER BY seq ASC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        results = []
        for row in rows:
            payload_raw = row[6]
            try:
                payload = json.loads(payload_raw) if payload_raw else None
            except (json.JSONDecodeError, TypeError):
                payload = payload_raw
            results.append({
                "seq": row[0],
                "id": row[1],
                "source": row[2],
                "type": row[3],
                "ts": row[4],
                "severity": row[5],
                "payload": payload,
                "requires_speech": bool(row[7]),
                "correlation_id": row[8],
            })
        return results

    def last_seq(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT MAX(seq) FROM event_log").fetchone()
        return int(row[0]) if row and row[0] else 0

    def stop(self) -> None:
        self._running = False
        self._writer_thread.join(timeout=5)

    def event_count(self, event_type: str | None = None, since: float = 0) -> int:
        query = "SELECT COUNT(*) FROM event_log WHERE created_at > ?"
        params: list[Any] = [since]
        if event_type:
            query += " AND type LIKE ?"
            params.append(event_type.replace(">", "%").replace("*", "%"))
        with self._connect() as conn:
            row = conn.execute(query, params).fetchone()
        return int(row[0]) if row else 0


def _subject_matches(pattern: str, subject: str) -> bool:
    if pattern == subject:
        return True
    if pattern.endswith(".>"):
        prefix = pattern[:-2]
        return subject == prefix or subject.startswith(prefix + ".")
    if "*" in pattern:
        return fnmatch.fnmatch(subject, pattern)
    return False
