"""
File Skill

Handles file system operations (read, list, check existence)
via the FileSystemTool.
"""

from services.skills.base import Skill, SkillContext
from services.brain.intent import Intent
from packages.common import logger


class FileSkill(Skill):

    def __init__(self, filesystem_tool):
        self.filesystem_tool = filesystem_tool

    @property
    def name(self) -> str:
        return "file"

    def can_handle(self, ctx: SkillContext) -> bool:
        return ctx.intent == Intent.FILE_OPERATION

    def execute(self, ctx: SkillContext) -> dict:
        logger.info("FileSkill executing")
        result = self.filesystem_tool.execute(ctx.message)
        if isinstance(result, dict):
            result["intent"] = ctx.intent.value
            return result
        return {
            "action": "file",
            "intent": ctx.intent.value,
            "response": str(result),
        }
