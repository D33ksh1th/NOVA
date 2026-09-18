"""
Voice state and session models.

State machine: IDLE → LISTENING → RECOGNIZING → THINKING → SPEAKING → IDLE
                                                                    → INTERRUPTED → LISTENING
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Set


class VoiceState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    RECOGNIZING = "recognizing"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    ERROR = "error"


# Valid state transitions
_TRANSITIONS: Dict[VoiceState, Set[VoiceState]] = {
    VoiceState.IDLE: {VoiceState.LISTENING, VoiceState.SPEAKING, VoiceState.ERROR},
    VoiceState.LISTENING: {VoiceState.RECOGNIZING, VoiceState.IDLE, VoiceState.ERROR},
    VoiceState.RECOGNIZING: {VoiceState.THINKING, VoiceState.IDLE, VoiceState.ERROR},
    VoiceState.THINKING: {VoiceState.SPEAKING, VoiceState.IDLE, VoiceState.ERROR},
    VoiceState.SPEAKING: {VoiceState.IDLE, VoiceState.INTERRUPTED, VoiceState.ERROR},
    VoiceState.INTERRUPTED: {VoiceState.LISTENING, VoiceState.IDLE, VoiceState.ERROR},
    VoiceState.ERROR: {VoiceState.IDLE, VoiceState.LISTENING},
}


@dataclass
class VoiceSession:
    state: VoiceState = VoiceState.IDLE
    wake_word_detected: bool = False
    transcript: str = ""
    response: str = ""
    error: str = ""
    started_at: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )
    metadata: Dict[str, Any] = field(default_factory=dict)

    def touch(self, state: VoiceState | None = None) -> None:
        if state is not None:
            allowed = _TRANSITIONS.get(self.state, set())
            if state not in allowed and state != self.state:
                # Allow the transition but log it — don't block
                pass
            self.state = state
        self.updated_at = datetime.now().isoformat(timespec="seconds")

    def transition(self, state: VoiceState) -> bool:
        """Transition to a new state. Returns False if invalid."""
        allowed = _TRANSITIONS.get(self.state, set())
        if state not in allowed and state != self.state:
            return False
        self.state = state
        self.updated_at = datetime.now().isoformat(timespec="seconds")
        return True

    def fail(self, error: str) -> None:
        self.state = VoiceState.ERROR
        self.error = error
        self.touch()

    @property
    def thinking_elapsed_ms(self) -> float:
        """Milliseconds since entering THINKING state."""
        if self.state != VoiceState.THINKING:
            return 0.0
        try:
            entered = datetime.fromisoformat(self.updated_at)
            return (datetime.now() - entered).total_seconds() * 1000
        except Exception:
            return 0.0

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        return payload
