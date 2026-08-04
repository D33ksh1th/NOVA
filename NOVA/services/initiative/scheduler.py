"""
Initiative scheduler.

Keeps the companion from speaking too often.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from packages.common import logger


@dataclass
class InitiativeSchedule:
    allowed: bool
    reason: str = ""
    next_allowed_at: Optional[str] = None


class InitiativeScheduler:
    def __init__(self, cooldown_minutes: int = 45, min_turn_gap: int = 4):
        self.cooldown_minutes = cooldown_minutes
        self.min_turn_gap = min_turn_gap

    def can_emit(self, state, priority: int) -> InitiativeSchedule:
        now = datetime.now()

        if priority >= 90:
            return InitiativeSchedule(allowed=True, reason="high_priority")

        if state.last_initiative_at:
            try:
                last = datetime.fromisoformat(state.last_initiative_at)
                elapsed = now - last
                if elapsed < timedelta(minutes=self.cooldown_minutes):
                    next_allowed = last + timedelta(minutes=self.cooldown_minutes)
                    return InitiativeSchedule(
                        allowed=False,
                        reason="cooldown_active",
                        next_allowed_at=next_allowed.isoformat(timespec="seconds"),
                    )
            except Exception:
                logger.warning("InitiativeScheduler: could not parse last_initiative_at")

        if state.turn_count < self.min_turn_gap:
            return InitiativeSchedule(
                allowed=False,
                reason="not_enough_context",
                next_allowed_at=None,
            )

        return InitiativeSchedule(allowed=True, reason="ok")
