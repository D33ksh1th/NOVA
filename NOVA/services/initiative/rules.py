"""
Initiative rules and state models.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class InitiativeState:
    turn_count: int = 0
    debug_count: int = 0
    repetitive_topic_count: int = 0
    current_topic: str = ""
    paused_topic: str = ""
    last_date: str = ""
    last_initiative_at: str = ""
    last_initiative_type: str = ""
    last_message: str = ""
    last_intent: str = ""
    suggestions_shown: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: Optional[str]) -> "InitiativeState":
        if not raw:
            return cls()
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                known = {f.name for f in cls.__dataclass_fields__.values()}
                kwargs = {k: v for k, v in data.items() if k in known}
                extra = {k: v for k, v in data.items() if k not in known}
                state = cls(**kwargs)
                if extra:
                    state.extra = extra
                return state
        except Exception:
            pass
        return cls()


@dataclass
class InitiativeDecision:
    should_speak: bool = False
    kind: str = "quiet"
    message: str = ""
    reason: str = ""
    priority: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "should_speak": self.should_speak,
            "kind": self.kind,
            "message": self.message,
            "reason": self.reason,
            "priority": self.priority,
            "metadata": self.metadata,
        }


class InitiativeRules:
    """Rule helpers used by the initiative engine."""

    def should_pause_learning(self, message: str) -> bool:
        text = message.lower()
        phrases = [
            "stop for today",
            "let's stop",
            "pause here",
            "later",
            "tomorrow",
            "continue tomorrow",
            "resume later",
        ]
        return any(phrase in text for phrase in phrases)

    def should_resume_session(self, message: str, paused_topic: str) -> bool:
        text = message.lower()
        resume_words = ["continue", "resume", "pick up", "where were we", "keep going"]
        return bool(paused_topic) and any(word in text for word in resume_words)

    def is_debugging_session(self, debug_count: int) -> bool:
        return debug_count >= 3

    def should_offer_recap(self, repetitive_topic_count: int) -> bool:
        return repetitive_topic_count >= 3

    def should_check_in_morning(self, paused_topic: str, current_hour: int, last_date: str, today: str) -> bool:
        if not paused_topic:
            return False
        if last_date and last_date == today:
            return False
        return 5 <= current_hour < 12

    def build_resume_decision(self, paused_topic: str) -> InitiativeDecision:
        topic = paused_topic.strip() or "the last task"
        return InitiativeDecision(
            should_speak=True,
            kind="resume",
            priority=100,
            reason="User is resuming a paused work session.",
            message=(
                f"We paused while working on {topic}. "
                f"Would you like me to continue from there?"
            ),
            metadata={"topic": topic},
        )

    def build_recap_decision(self, topic: str) -> InitiativeDecision:
        topic = topic.strip() or "the current issue"
        return InitiativeDecision(
            should_speak=True,
            kind="recap",
            priority=90,
            reason="Repeated debugging or troubleshooting pattern detected.",
            message=(
                f"We’ve circled {topic} a few times. "
                f"Want me to summarize what we know so far and suggest the next step?"
            ),
            metadata={"topic": topic},
        )

    def build_morning_checkin(self, paused_topic: str) -> InitiativeDecision:
        topic = paused_topic.strip() or "yesterday's task"
        return InitiativeDecision(
            should_speak=True,
            kind="checkin",
            priority=80,
            reason="Morning check-in after a paused session.",
            message=(
                f"Good morning. Yesterday we paused {topic}. "
                f"Would you like to continue?"
            ),
            metadata={"topic": topic},
        )

    def build_low_key_suggestion(self, topic: str) -> InitiativeDecision:
        topic = topic.strip() or "this topic"
        return InitiativeDecision(
            should_speak=True,
            kind="suggestion",
            priority=40,
            reason="Light proactive suggestion based on recent context.",
            message=(
                f"It looks like we're still on {topic}. "
                f"I can organize the next step if you want."
            ),
            metadata={"topic": topic},
        )
