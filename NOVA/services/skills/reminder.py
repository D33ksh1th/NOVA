"""
Reminder Skill

Handles reminder creation and listing.
No LLM — direct tool dispatch.
"""

from services.skills.base import Skill, SkillContext
from services.brain.intent import Intent
from packages.common import logger


class ReminderSkill(Skill):

    def __init__(self, reminder_tool):
        self.reminder_tool = reminder_tool

    @property
    def name(self) -> str:
        return "reminder"

    def can_handle(self, ctx: SkillContext) -> bool:
        if ctx.intent == Intent.REMINDER:
            return True
        text = ctx.message.lower()
        return any(k in text for k in [
            "remind me", "set a reminder", "set an alarm", "alert me",
        ])

    def execute(self, ctx: SkillContext) -> dict:
        logger.info("ReminderSkill executing")
        result = self.reminder_tool.execute(ctx.message)
        result["intent"] = ctx.intent.value
        return result
