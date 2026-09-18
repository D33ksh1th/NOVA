"""
Gmail Monitor — background polling loop.

Runs as an asyncio task (started from gateway lifespan).
On each tick it:
  1. Fetches unread message IDs from Gmail.
  2. Skips any already-seen IDs.
  3. For each new message, classifies urgency and fires GMAIL_NEW_MESSAGE
     on the NOVA event bus (which gets bridged to the frontend SSE stream).
  4. Marks high-priority messages as seen so they're not re-announced.

The monitor is enabled only when GMAIL_MONITOR_ENABLED=true in settings
and when a valid token exists at GMAIL_TOKEN_PATH.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Set

from packages.common import logger
from packages.config import settings
from packages.events import Event, bus


class GmailMonitor:
    """
    Async background polling loop for Gmail new-message notifications.
    """

    def __init__(self):
        self._seen_ids: Set[str] = set()
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._tool = None   # lazy-initialised to avoid heavy imports at startup
        self._initial_seed_done = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if not settings.GMAIL_MONITOR_ENABLED:
            logger.info("GmailMonitor: disabled via GMAIL_MONITOR_ENABLED=false")
            return
        if not Path(settings.GMAIL_TOKEN_PATH).expanduser().exists():
            logger.warning(
                "GmailMonitor: token not found — skipping start. "
                "Complete OAuth setup to enable live Gmail notifications.",
                token_path=settings.GMAIL_TOKEN_PATH,
            )
            return
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="gmail_monitor")
        logger.info(
            "GmailMonitor: started",
            interval_seconds=settings.GMAIL_POLL_INTERVAL,
        )

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
        logger.info("GmailMonitor: stopped")

    # ------------------------------------------------------------------
    # Poll loop
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        while self._running:
            try:
                await asyncio.to_thread(self._poll)
            except asyncio.CancelledError:
                break
            except Exception as ex:
                logger.error(f"GmailMonitor: poll error — {ex}")
            await asyncio.sleep(settings.GMAIL_POLL_INTERVAL)

    def _poll(self) -> None:
        tool = self._get_tool()
        if tool is None:
            return

        messages = tool.list_unread(max_results=settings.GMAIL_MAX_RESULTS)

        # First poll: seed seen IDs without firing notifications
        if not self._initial_seed_done:
            for m in messages:
                mid = m.get("id")
                if mid:
                    self._seen_ids.add(mid)
            self._initial_seed_done = True
            logger.info("GmailMonitor: seeded existing unread messages", count=len(self._seen_ids))
            return

        new_messages = [m for m in messages if m.get("id") and m["id"] not in self._seen_ids]

        for msg in new_messages:
            self._seen_ids.add(msg["id"])
            self._fire_event(msg)

        if new_messages:
            logger.info(
                "GmailMonitor: new messages detected",
                count=len(new_messages),
                critical=sum(1 for m in new_messages if m.get("urgency") == "critical"),
                high=sum(1 for m in new_messages if m.get("urgency") == "high"),
            )

    def _fire_event(self, msg: dict) -> None:
        urgency = msg.get("urgency", "normal")
        bus.publish(
            Event.GMAIL_NEW_MESSAGE,
            {
                "id": msg.get("id"),
                "from": msg.get("from", "unknown"),
                "subject": msg.get("subject", "(no subject)"),
                "snippet": msg.get("snippet", ""),
                "date": msg.get("date", ""),
                "urgency": urgency,
                "urgency_emoji": msg.get("urgency_emoji", "📬"),
                "thread_id": msg.get("thread_id"),
                "detected_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        logger.info(
            "GmailMonitor: fired GMAIL_NEW_MESSAGE",
            urgency=urgency,
            subject=str(msg.get("subject", ""))[:60],
            sender=str(msg.get("from", ""))[:40],
        )

    # ------------------------------------------------------------------
    # Tool lazy-load
    # ------------------------------------------------------------------

    def _get_tool(self):
        if self._tool is not None:
            return self._tool
        try:
            from services.tools.gmail_tool import GmailTool
            t = GmailTool()
            if t.is_available():
                self._tool = t
                logger.info("GmailMonitor: Gmail service authenticated successfully")
            else:
                logger.warning("GmailMonitor: Gmail service not available — check credentials")
        except Exception as ex:
            logger.error(f"GmailMonitor: could not load GmailTool — {ex}")
        return self._tool
