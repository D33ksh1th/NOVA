"""
Cognitive Engine
"""

from services.cognition.planner import (
    CognitivePlanner,
)

from services.cognition.executor import (
    PlanExecutor,
)


class CognitiveEngine:

    def __init__(self):

        self.planner = CognitivePlanner()

        self.executor = PlanExecutor()

    def think(self, goal):

        plan = self.planner.create(goal)

        return self.executor.execute(plan)