"""
Time Skill

Returns the current time and date using the TimeTool.
No LLM involved — direct tool → response.
"""

from services.skills.base import Skill, SkillContext
from services.brain.intent import Intent
from packages.common import logger


class TimeSkill(Skill):

    def __init__(self, time_tool):
        self.time_tool = time_tool

    @property
    def name(self) -> str:
        return "time"

    def can_handle(self, ctx: SkillContext) -> bool:
        if ctx.intent == Intent.TIME_QUERY:
            return True
        text = ctx.message.lower()
        return any(k in text for k in ["what time", "current time", "what's the time"])

    def execute(self, ctx: SkillContext) -> dict:
        logger.info("TimeSkill executing")
        result = self.time_tool.execute(ctx.message)
        result["intent"] = ctx.intent.value
        return result
