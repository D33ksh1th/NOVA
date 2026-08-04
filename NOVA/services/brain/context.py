"""
Conversation Context Engine
"""

from dataclasses import dataclass, field
from typing import List

from packages.common import logger


@dataclass
class ConversationContext:
    session_id: str = "default"
    history: List[str] = field(default_factory=list)

    def add_message(self, message: str):
        self.history.append(message)

    def last_message(self):
        if not self.history:
            return None
        return self.history[-1]


class ContextEngine:

    def __init__(self):
        self.context = ConversationContext()

    def build(self, message: str):

        logger.info("Building Context")

        self.context.add_message(message)

        return {
            "session_id": self.context.session_id,
            "history_length": len(self.context.history),
            "last_message": self.context.last_message(),
        }