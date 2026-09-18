"""
Cognitive Models
"""

from dataclasses import dataclass, field


@dataclass
class Thought:

    title: str

    completed: bool = False


@dataclass
class Plan:

    goal: str

    thoughts: list[Thought] = field(default_factory=list)