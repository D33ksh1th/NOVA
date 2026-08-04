"""
Planner Skill
"""

from services.skills.base import Skill
from services.skills.base import SkillContext
from services.brain.intent import Intent


class PlannerSkill(Skill):

    def __init__(self, planner):

        self.planner = planner

    @property
    def name(self):

        return "planner"

    def can_handle(self, ctx: SkillContext) -> bool:
        return ctx.intent == Intent.CREATE_TASK

    def execute(self, ctx: SkillContext) -> dict:
        goal = (
            ctx.message
            .replace("create", "")
            .replace("task", "")
            .strip()
        )
        result = self.planner.create_goal(goal)
        result["intent"] = ctx.intent.value
        result["response"] = f"Task created: {goal}"
        return result