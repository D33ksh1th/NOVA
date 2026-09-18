"""
Cognitive Planner
"""

from services.cognition.models import (
    Plan,
    Thought,
)


class CognitivePlanner:

    def create(self, goal: str):

        plan = Plan(goal=goal)

        plan.thoughts.append(
            Thought("Understand request")
        )

        plan.thoughts.append(
            Thought("Search knowledge")
        )

        plan.thoughts.append(
            Thought("Select skill")
        )

        plan.thoughts.append(
            Thought("Generate response")
        )

        return plan