"""
System Skill

Handles system-related queries (including IP address)
via the SystemInfoTool.
"""

from services.skills.base import Skill, SkillContext
from services.brain.intent import Intent
from packages.common import logger


class SystemSkill(Skill):

    def __init__(self, system_tool):
        self.system_tool = system_tool

    @property
    def name(self) -> str:
        return "system"

    def can_handle(self, ctx: SkillContext) -> bool:
        if ctx.intent == Intent.SYSTEM_QUERY:
            return True

        text = (ctx.message or "").lower()
        fallback_keywords = [
            "system information",
            "system info",
            "system details",
            "device information",
            "computer information",
            "operating system",
            "os details",
            "battery",
            "cpu",
            "ram",
            "ip address",
        ]

        return any(keyword in text for keyword in fallback_keywords)

    def execute(self, ctx: SkillContext) -> dict:
        logger.info("SystemSkill executing")
        result = self.system_tool.execute(ctx.message)
        if isinstance(result, dict):
            result["intent"] = ctx.intent.value
            return result
        return {
            "action": "system",
            "intent": ctx.intent.value,
            "response": str(result),
        }
