"""
Reminder Tool

SQLite-backed reminder storage. A background daemon thread polls every 30 s
and fires a callback (registered by the gateway) when a reminder is due.
"""

from __future__ import annotations

import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, List, Optional

from services.tools.base import Tool
from packages.common import logger

_DB_PATH = Path.home() / ".nova" / "reminders.db"
_POLL_INTERVAL = 30  # seconds


def _parse_reminder(message: str):
    """
    Extract (task_text, due_datetime) from a natural-language reminder request.
    Returns (None, None) if parsing fails.

    Handles:
      "remind me at 5pm to call Priya"
      "remind me in 10 minutes to check the oven"
      "set a reminder for 3:30pm to take medicine"
      "remind me tomorrow at 9am to send the report"
    """
    text = message.lower().strip()
    now = datetime.now()
    due: Optional[datetime] = None
    task: Optional[str] = None

    # ── "in X minutes/hours" ──────────────────────────────────────
    m = re.search(r"\bin\s+(\d+)\s*(minute|min|hour|hr)s?\b", text)
    if m:
        val = int(m.group(1))
        unit = m.group(2)
        delta = timedelta(hours=val) if unit.startswith("h") else timedelta(minutes=val)
        due = now + delta

    # ── "at HH:MM" or "at H:MMam/pm" or "at Xpm" ─────────────────
    if due is None:
        m = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", text)
        if m:
            hour = int(m.group(1))
            minute = int(m.group(2)) if m.group(2) else 0
            meridiem = m.group(3)
            if meridiem == "pm" and hour != 12:
                hour += 12
            elif meridiem == "am" and hour == 12:
                hour = 0
            due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if due <= now:
                due += timedelta(days=1)  # already passed today → tomorrow

    # ── "tomorrow at Xpm" ────────────────────────────────────────
    if "tomorrow" in text and due is not None:
        if due.date() == now.date():
            due += timedelta(days=1)

    # ── Extract task text ─────────────────────────────────────────
    # Try "to <task>" pattern
    m = re.search(r"\bto\s+(.+)$", message, re.IGNORECASE)
    if m:
        task = m.group(1).strip()
    else:
        # Fall back: strip the "remind me …" prefix
        cleaned = re.sub(
            r"(?i)(remind me|set (a|an) reminder|alert me)(.*?)(at|in|by|for)\s+",
            "", message
        ).strip()
        task = cleaned if cleaned else message

    return task, due


class ReminderTool(Tool):

    def __init__(self, speak_callback: Optional[Callable[[str], None]] = None):
        self._speak_callback = speak_callback
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._start_poller()

    # ── Tool protocol ─────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "reminder"

    def can_handle(self, message: str) -> bool:
        text = message.lower()
        return any(k in text for k in ["remind me", "set a reminder", "set an alarm", "alert me"])

    def execute(self, message: str) -> dict:
        task, due = _parse_reminder(message)

        if due is None:
            return {
                "action": "reminder",
                "success": False,
                "response": "I couldn't figure out when you want to be reminded. Try: 'Remind me at 5pm to call Priya'.",
            }

        if not task:
            task = "your reminder"

        self._save(task, due)

        pretty = due.strftime("%-I:%M %p on %A, %d %B")
        return {
            "action": "reminder",
            "success": True,
            "response": f"Got it. I'll remind you to {task} at {pretty}.",
        }

    def set_speak_callback(self, fn: Callable[[str], None]) -> None:
        self._speak_callback = fn

    # ── Persistence ───────────────────────────────────────────────

    def _init_db(self) -> None:
        with sqlite3.connect(str(_DB_PATH)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    task    TEXT    NOT NULL,
                    due_at  TEXT    NOT NULL,
                    fired   INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.commit()

    def _save(self, task: str, due: datetime) -> None:
        with sqlite3.connect(str(_DB_PATH)) as conn:
            conn.execute(
                "INSERT INTO reminders (task, due_at, fired) VALUES (?, ?, 0)",
                (task, due.isoformat()),
            )
            conn.commit()
        logger.info(f"ReminderTool: saved '{task}' due at {due.isoformat()}")

    def _due_reminders(self) -> List[tuple]:
        now = datetime.now().isoformat()
        with sqlite3.connect(str(_DB_PATH)) as conn:
            rows = conn.execute(
                "SELECT id, task FROM reminders WHERE fired=0 AND due_at <= ?",
                (now,),
            ).fetchall()
        return rows

    def _mark_fired(self, reminder_id: int) -> None:
        with sqlite3.connect(str(_DB_PATH)) as conn:
            conn.execute("UPDATE reminders SET fired=1 WHERE id=?", (reminder_id,))
            conn.commit()

    # ── Background poller ─────────────────────────────────────────

    def _start_poller(self) -> None:
        t = threading.Thread(target=self._poll_loop, daemon=True, name="nova-reminder-poller")
        t.start()
        logger.info("ReminderTool: background poller started")

    def _poll_loop(self) -> None:
        while True:
            try:
                for rid, task in self._due_reminders():
                    self._mark_fired(rid)
                    msg = f"Hey boss, just a reminder: {task}."
                    logger.info(f"ReminderTool: firing reminder id={rid} '{task}'")
                    if self._speak_callback:
                        try:
                            self._speak_callback(msg)
                        except Exception as ex:
                            logger.warning(f"ReminderTool: speak_callback error: {ex}")
            except Exception as ex:
                logger.warning(f"ReminderTool: poll error: {ex}")
            time.sleep(_POLL_INTERVAL)
