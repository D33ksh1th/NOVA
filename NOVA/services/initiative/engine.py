"""
Initiative Engine

Evaluates every completed conversation turn and decides whether
NOVA should stay quiet, remind, recap, or proactively suggest
something useful.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, Optional

from packages.common import logger

from .rules import InitiativeState, InitiativeRules, InitiativeDecision
from .scheduler import InitiativeScheduler
from .triggers import InitiativeTriggers


class InitiativeEngine:
    def __init__(self, memory, system_context=None):
        self.memory = memory
        self.system_context = system_context
        self.rules = InitiativeRules()
        self.triggers = InitiativeTriggers()
        self.scheduler = InitiativeScheduler()
        logger.info("Initiative Engine Initialized")

    def evaluate(
        self,
        message: str,
        brain_result: Dict[str, Any],
        conversation_history: Optional[Iterable[dict]] = None,
    ) -> Optional[dict]:
        """Return an initiative payload or None."""
        state = self._load_state()
        now = datetime.now()
        today = now.date().isoformat()
        history = list(conversation_history or [])

        state.turn_count += 1
        state.last_message = message
        state.last_intent = str(brain_result.get("intent", ""))

        topic = self.triggers.extract_topic(message, brain_result)
        if topic:
            if state.current_topic == topic:
                state.repetitive_topic_count += 1
            else:
                state.repetitive_topic_count = 1
            state.current_topic = topic
        else:
            state.repetitive_topic_count = max(state.repetitive_topic_count - 1, 0)

        state.debug_count = self.triggers.count_debug_intensity(history)

        # Pause requests are remembered, but not interrupted with suggestions.
        if self.triggers.is_pause_request(message):
            paused = topic or state.current_topic or self._derive_topic_from_result(brain_result)
            if paused:
                state.paused_topic = paused
            self._save_state(state)
            return None

        decision = self._decide(state, message, brain_result, today)
        self._save_state(state)

        if not decision or not decision.should_speak:
            return None

        state.last_initiative_at = now.isoformat(timespec="seconds")
        state.last_initiative_type = decision.kind
        state.suggestions_shown += 1
        self._save_state(state)

        return {
            "type": decision.kind,
            "message": decision.message,
            "reason": decision.reason,
            "priority": decision.priority,
            "metadata": decision.metadata,
        }

    def _decide(self, state: InitiativeState, message: str, brain_result: Dict[str, Any], today: str) -> Optional[InitiativeDecision]:
        # Highest value: resuming a paused session.
        if self.triggers.is_resume_request(message) and state.paused_topic:
            return self.rules.build_resume_decision(state.paused_topic)

        # Morning check-in for a paused session on a later day.
        system_now = self._system_hour()
        if self.rules.should_check_in_morning(state.paused_topic, system_now, state.last_date, today):
            state.last_date = today
            return self.rules.build_morning_checkin(state.paused_topic)

        # Repeated debugging patterns.
        if self.rules.is_debugging_session(state.debug_count):
            topic = state.current_topic or self._derive_topic_from_result(brain_result) or "this issue"
            schedule = self.scheduler.can_emit(state, priority=95)
            if schedule.allowed:
                return self.rules.build_recap_decision(topic)

        # Repeated topic/questions.
        if self.rules.should_offer_recap(state.repetitive_topic_count):
            topic = state.current_topic or self._derive_topic_from_result(brain_result) or "this topic"
            schedule = self.scheduler.can_emit(state, priority=70)
            if schedule.allowed:
                return self.rules.build_low_key_suggestion(topic)

        # Greetings always get a direct conversational response — never inject
        # a paused-topic recap unprompted, as it overwrites the natural reply.
        if self.triggers.is_greeting(message):
            return None

        return None

    def _derive_topic_from_result(self, brain_result: Dict[str, Any]) -> str:
        response = str(brain_result.get("response", ""))
        action = str(brain_result.get("action", ""))
        if action == "plan":
            steps = brain_result.get("steps") or []
            if steps:
                first = steps[0]
                if isinstance(first, dict):
                    return str(first.get("task", ""))
        return self.triggers.extract_topic(response, brain_result)

    def _system_hour(self) -> int:
        if self.system_context is not None:
            try:
                data = self.system_context.build()
                time_str = data.get("time") or ""
                if time_str:
                    return int(time_str.split(":", 1)[0])
            except Exception:
                pass
        return datetime.now().hour

    def _load_state(self) -> InitiativeState:
        raw = self.memory.recall("initiative:state")
        return InitiativeState.from_json(raw)

    def _save_state(self, state: InitiativeState) -> None:
        self.memory.remember("initiative:state", state.to_json())
