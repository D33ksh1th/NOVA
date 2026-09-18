"""
Location Skill

Returns the user's current location via the LocationTool.
No LLM involved — direct tool → response.
"""

from services.skills.base import Skill, SkillContext
from services.brain.intent import Intent
from packages.common import logger


class LocationSkill(Skill):

    def __init__(self, location_tool):
        self.location_tool = location_tool

    @property
    def name(self) -> str:
        return "location"

    def can_handle(self, ctx: SkillContext) -> bool:
        if ctx.intent == Intent.LOCATION_QUERY:
            return True

        text = ctx.message.lower()
        keywords = [
            "location", "where am i", "current location",
            "my location", "which city", "where are we",
        ]
        return any(k in text for k in keywords)

    def execute(self, ctx: SkillContext) -> dict:
        logger.info("LocationSkill executing")
        result = self.location_tool.execute(ctx.message)
        result["intent"] = ctx.intent.value
        return result
