"""Proactive daemon — scheduled watchers and ambient awareness.

Runs background tasks:
- Morning brief (once per day when presence detected after 6 AM)
- End-of-day summary (once when presence detected after 6 PM)
- Periodic security digest
- Cert expiry watcher (stub for Phase 6)
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional

from packages.common import logger
from packages.events import bus


class ProactiveDaemon:

    def __init__(
        self,
        presence_fn: Optional[Callable[[], bool]] = None,
        speak_fn: Optional[Callable[[str], None]] = None,
    ):
        self._presence_fn = presence_fn or (lambda: True)
        self._speak_fn = speak_fn
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._morning_brief_done = False
        self._evening_summary_done = False
        self._last_date = ""

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="proactive-daemon",
        )
        self._thread.start()
        logger.info("ProactiveDaemon: started")

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        while self._running:
            try:
                self._tick()
            except Exception as ex:
                logger.error(f"ProactiveDaemon: tick error: {ex}")
            time.sleep(30)

    def _tick(self) -> None:
        today = time.strftime("%Y-%m-%d")
        if today != self._last_date:
            self._morning_brief_done = False
            self._evening_summary_done = False
            self._last_date = today

        hour = int(time.strftime("%H"))
        present = self._is_present()

        # Morning brief: 6-10 AM, once per day, when present
        if 6 <= hour <= 10 and not self._morning_brief_done and present:
            self._morning_brief()
            self._morning_brief_done = True

        # Evening summary: 6-9 PM, once per day, when present
        if 18 <= hour <= 21 and not self._evening_summary_done and present:
            self._evening_summary()
            self._evening_summary_done = True

    def _is_present(self) -> bool:
        try:
            return self._presence_fn()
        except Exception:
            return True

    def _morning_brief(self) -> None:
        parts = []

        # Time greeting
        parts.append("Good morning, sir.")

        # System health
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.3)
            mem = psutil.virtual_memory().percent
            parts.append(f"Systems nominal. CPU at {cpu}%, memory at {mem}%.")
        except Exception:
            parts.append("Systems online.")

        # Unread mail count
        try:
            from packages.registry import registry
            tool = registry.gmail_tool
            if tool and tool.is_available():
                unread = tool.list_unread(max_results=50)
                if unread:
                    parts.append(f"You have {len(unread)} unread email{'s' if len(unread) != 1 else ''}.")
        except Exception:
            pass

        # Security findings
        try:
            from packages.registry import registry
            findings = len(registry.security_center.findings)
            if findings > 0:
                parts.append(f"{findings} security finding{'s' if findings != 1 else ''} require attention.")
        except Exception:
            pass

        brief = " ".join(parts)
        logger.info(f"ProactiveDaemon: morning brief | {brief[:100]}")
        bus.emit("nova.initiative.morning_brief", source="proactive-daemon", payload={"brief": brief}, severity=1, requires_speech=True)

        if self._speak_fn:
            try:
                self._speak_fn(brief)
            except Exception as ex:
                logger.error(f"ProactiveDaemon: speak failed: {ex}")

    def _evening_summary(self) -> None:
        parts = ["Good evening, sir. Here's your day summary."]

        # Event count from bus
        try:
            now = time.time()
            voice_count = bus.event_count(event_type="nova.voice.>", since=now - 86400)
            security_count = bus.event_count(event_type="nova.security.>", since=now - 86400)
            mail_count = bus.event_count(event_type="nova.mail.>", since=now - 86400)
            parts.append(f"Today: {voice_count} voice interactions, {mail_count} mail events, {security_count} security events.")
        except Exception:
            pass

        summary = " ".join(parts)
        logger.info(f"ProactiveDaemon: evening summary | {summary[:100]}")
        bus.emit("nova.initiative.evening_summary", source="proactive-daemon", payload={"summary": summary}, severity=0, requires_speech=True)

        if self._speak_fn:
            try:
                self._speak_fn(summary)
            except Exception as ex:
                logger.error(f"ProactiveDaemon: speak failed: {ex}")
