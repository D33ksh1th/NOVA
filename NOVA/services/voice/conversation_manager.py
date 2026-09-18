"""Conversation turn manager for voice interactions."""

from __future__ import annotations

from .models import ConversationTurnState
from .state import VoiceSession, VoiceState


class VoiceConversationManager:
    def begin_turn(self, session: VoiceSession, speaker: str | None = None) -> ConversationTurnState:
        metadata = dict(session.metadata or {})
        previous_state = session.state
        turn_count = int(metadata.get("turn_count", 0)) + 1
        interrupted = previous_state == VoiceState.SPEAKING
        active_speaker = speaker or metadata.get("active_speaker")

        metadata.update(
            {
                "turn_count": turn_count,
                "active_speaker": active_speaker,
                "interrupted": interrupted,
            }
        )
        session.metadata = metadata
        return ConversationTurnState(
            interrupted=interrupted,
            should_listen=True,
            active_speaker=active_speaker,
            turn_count=turn_count,
        )

    def end_turn(self, session: VoiceSession) -> None:
        metadata = dict(session.metadata or {})
        metadata["interrupted"] = False
        session.metadata = metadata
