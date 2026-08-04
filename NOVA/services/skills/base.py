"""
Base Skill

Every NOVA capability inherits from this class.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class SkillContext:
    """Everything a skill needs to produce a response."""
    message: str
    intent: Any          # services.brain.intent.Intent
    memory: Optional[dict] = field(default_factory=dict)
    context: Optional[dict] = field(default_factory=dict)
    personality: Optional[str] = None
    tool_result: Optional[Any] = None


class Skill(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique skill identifier."""
        ...

    @abstractmethod
    def can_handle(self, ctx: SkillContext) -> bool:
        """
        Return True if this skill should handle the current request.
        Receives full SkillContext so skills can inspect message text,
        intent, memory, etc.
        """
        ...

    @abstractmethod
    def execute(self, ctx: SkillContext) -> dict:
        """
        Execute the skill and return a response dict.
        Must always include a 'response' key.
        """
        ...