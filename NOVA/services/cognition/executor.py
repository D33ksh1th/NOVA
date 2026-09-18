"""
Plan Executor
"""


class PlanExecutor:

    def execute(self, plan):

        for thought in plan.thoughts:

            thought.completed = True

        return plan