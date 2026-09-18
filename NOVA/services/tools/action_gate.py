"""Three-tier action gate for tool execution.

Tier 0 (auto): read-only queries — no confirmation needed
Tier 1 (announce): reversible changes — Nova states what it's doing, 5s cancel window
Tier 2 (confirm): destructive/production — voice confirmation required, dry-run first
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Callable, Dict, Optional

from packages.common import logger
from packages.events import bus
from packages.database import state_store


class ActionTier(IntEnum):
    AUTO = 0        # read-only, no confirmation
    ANNOUNCE = 1    # reversible, announce + 5s cancel window
    CONFIRM = 2     # destructive, require explicit voice/text confirmation


@dataclass
class ActionRequest:
    tool: str
    action: str
    params: Dict[str, Any]
    tier: ActionTier
    description: str
    dry_run_result: Optional[str] = None
    confirmed: bool = False
    cancelled: bool = False
    executed: bool = False
    result: Optional[Dict[str, Any]] = None
    speaker_id: Optional[str] = None
    correlation_id: Optional[str] = None


# Tool tier classification
TOOL_TIERS: Dict[str, ActionTier] = {
    # Tier 0: read-only
    "TimeTool": ActionTier.AUTO,
    "DateTool": ActionTier.AUTO,
    "LocationTool": ActionTier.AUTO,
    "WeatherTool": ActionTier.AUTO,
    "SystemInfoTool": ActionTier.AUTO,
    "WebSearchTool": ActionTier.AUTO,
    "WebPageTool": ActionTier.AUTO,
    "RepositoryReadTool": ActionTier.AUTO,
    "VisionTool": ActionTier.AUTO,
    # Tier 1: reversible
    "ReminderTool": ActionTier.ANNOUNCE,
    "GmailTool": ActionTier.ANNOUNCE,
    "MacTool": ActionTier.ANNOUNCE,
    "FileSystemTool": ActionTier.ANNOUNCE,
    # Tier 2: destructive
    "TerminalTool": ActionTier.CONFIRM,
    "AnsibleTool": ActionTier.CONFIRM,
}

# Tier 2 commands that are always blocked
BLOCKED_COMMANDS = {"rm -rf", "mkfs", "dd if=", "format", "> /dev/", "shutdown", "reboot"}


class ActionGate:

    def __init__(self, speak_fn: Optional[Callable[[str], None]] = None):
        self._speak_fn = speak_fn
        self._pending: Dict[str, ActionRequest] = {}
        self._lock = threading.Lock()

    def request(self, req: ActionRequest) -> Dict[str, Any]:
        """Process an action request through the tier gate."""

        # Check for blocked commands
        if req.tier == ActionTier.CONFIRM:
            cmd = str(req.params.get("command", "")).lower()
            if any(blocked in cmd for blocked in BLOCKED_COMMANDS):
                self._audit(req, success=False, detail="blocked_dangerous_command")
                return {"approved": False, "reason": f"Blocked: contains dangerous command pattern"}

        if req.tier == ActionTier.AUTO:
            return self._execute(req)

        if req.tier == ActionTier.ANNOUNCE:
            return self._announce_and_execute(req)

        if req.tier == ActionTier.CONFIRM:
            return self._request_confirmation(req)

        return {"approved": False, "reason": "unknown_tier"}

    def confirm(self, action_id: str, speaker_id: Optional[str] = None) -> Dict[str, Any]:
        """Confirm a pending Tier 2 action."""
        with self._lock:
            req = self._pending.pop(action_id, None)
        if not req:
            return {"approved": False, "reason": "no_pending_action"}
        req.confirmed = True
        req.speaker_id = speaker_id
        return self._execute(req)

    def cancel(self, action_id: str) -> Dict[str, Any]:
        """Cancel a pending action."""
        with self._lock:
            req = self._pending.pop(action_id, None)
        if not req:
            return {"cancelled": False, "reason": "no_pending_action"}
        req.cancelled = True
        self._audit(req, success=False, detail="cancelled_by_user")
        return {"cancelled": True, "action": req.action}

    def pending_actions(self) -> list[Dict[str, Any]]:
        with self._lock:
            return [
                {"id": aid, "tool": r.tool, "action": r.action, "description": r.description, "tier": r.tier}
                for aid, r in self._pending.items()
            ]

    def _execute(self, req: ActionRequest) -> Dict[str, Any]:
        req.executed = True
        self._audit(req, success=True, detail="executed")
        bus.emit(
            "nova.action.executed",
            source=req.tool,
            payload={"action": req.action, "tier": int(req.tier), "params": req.params},
            severity=req.tier,
        )
        return {"approved": True, "tier": int(req.tier), "action": req.action}

    def _announce_and_execute(self, req: ActionRequest) -> Dict[str, Any]:
        msg = f"Executing: {req.description}"
        if self._speak_fn:
            try:
                self._speak_fn(msg)
            except Exception:
                pass
        logger.info(f"ActionGate: Tier 1 announce | {req.description}")
        return self._execute(req)

    def _request_confirmation(self, req: ActionRequest) -> Dict[str, Any]:
        import uuid
        action_id = str(uuid.uuid4())[:8]
        with self._lock:
            self._pending[action_id] = req

        msg = f"{req.description}. Confirm or cancel, sir."
        if self._speak_fn:
            try:
                self._speak_fn(msg)
            except Exception:
                pass

        logger.info(f"ActionGate: Tier 2 awaiting confirmation | id={action_id} | {req.description}")
        bus.emit(
            "nova.action.pending",
            source=req.tool,
            payload={"action_id": action_id, "action": req.action, "description": req.description},
            severity=2,
            requires_speech=True,
        )
        return {
            "approved": False,
            "pending": True,
            "action_id": action_id,
            "tier": 2,
            "description": req.description,
            "message": msg,
        }

    def _audit(self, req: ActionRequest, success: bool, detail: str) -> None:
        try:
            state_store.audit(
                event_type="nova.action.executed" if success else "nova.action.denied",
                source=req.tool,
                action=req.action,
                detail={
                    "tier": int(req.tier),
                    "params": req.params,
                    "description": req.description,
                    "detail": detail,
                },
                speaker_id=req.speaker_id,
                severity=int(req.tier),
                correlation_id=req.correlation_id,
                success=success,
            )
        except Exception as ex:
            logger.error(f"ActionGate: audit failed: {ex}")

    def get_tier(self, tool_name: str) -> ActionTier:
        return TOOL_TIERS.get(tool_name, ActionTier.ANNOUNCE)
