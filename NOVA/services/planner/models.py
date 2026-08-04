"""
Planner Models
"""

from dataclasses import dataclass


@dataclass
class Decision:

    use_tool: bool = False

    tool: str | None = None

    answer_directly: bool = True

    confidence: float = 0.0

    reasoning: str = ""

    use_memory: bool = False

    use_knowledge: bool = False