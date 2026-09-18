"""
Model Tasks
"""

from enum import Enum


class ModelTask(str, Enum):

    CHAT = "chat"

    CODING = "coding"

    EMBEDDING = "embedding"

    REASONING = "reasoning"

    SECURITY = "security"

    VISION = "vision"