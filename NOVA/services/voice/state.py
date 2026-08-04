"""
Voice state and session models.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict


class VoiceState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    RECOGNIZING = "recognizing"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ERROR = "error"


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
            self.state = state
        self.updated_at = datetime.now().isoformat(timespec="seconds")

    def fail(self, error: str) -> None:
        self.state = VoiceState.ERROR
        self.error = error
        self.touch()

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        return payload
