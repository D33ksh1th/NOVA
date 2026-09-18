"""
Conversation Memory

Tracks the in-session conversation history so NOVA has
short-term context without relying on the database for
every turn.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


@dataclass
class Turn:
    role: str           # "user" or "nova"
    content: str
    timestamp: str = field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )


class ConversationMemory:
    """
    Keeps the last N turns of the conversation in memory
    for fast context injection into prompts.
    """

    def __init__(self, max_turns: int = 10):
        self._turns: List[Turn] = []
        self._max_turns = max_turns

    def add_user(self, message: str) -> None:
        self._append(Turn(role="user", content=message))

    def add_nova(self, response: str) -> None:
        self._append(Turn(role="nova", content=response))

    def _append(self, turn: Turn) -> None:
        self._turns.append(turn)
        # Keep only the last N turns (pairs)
        if len(self._turns) > self._max_turns * 2:
            self._turns = self._turns[-(self._max_turns * 2):]

    def as_text(self, max_chars: int = 2000) -> str:
        """Return recent conversation as plain text for prompt injection."""
        lines = []
        for t in self._turns[-self._max_turns:]:
            prefix = "You" if t.role == "user" else "NOVA"
            lines.append(f"{prefix}: {t.content}")
        text = "\n".join(lines)
        # Truncate from the start if too long
        if len(text) > max_chars:
            text = "...\n" + text[-max_chars:]
        return text

    def as_list(self) -> List[dict]:
        return [
            {"role": t.role, "content": t.content, "timestamp": t.timestamp}
            for t in self._turns
        ]

    def is_empty(self) -> bool:
        return len(self._turns) == 0

    def clear(self) -> None:
        self._turns.clear()

    def last_user_message(self) -> Optional[str]:
        for turn in reversed(self._turns):
            if turn.role == "user":
                return turn.content
        return None

    def last_nova_response(self) -> Optional[str]:
        for turn in reversed(self._turns):
            if turn.role == "nova":
                return turn.content
        return None
