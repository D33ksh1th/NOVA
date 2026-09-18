"""
Knowledge Models
"""

from dataclasses import dataclass
from enum import Enum


class KnowledgeSource(Enum):

    MEMORY = "memory"

    CONVERSATION = "conversation"

    PLANNER = "planner"

    DOCUMENT = "document"

    CODE = "code"

    SECURITY = "security"


@dataclass
class Knowledge:

    source: KnowledgeSource

    title: str

    content: str

    score: float = 1.0