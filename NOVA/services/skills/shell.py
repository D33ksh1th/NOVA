"""
Shell Skill

Executes shell/terminal commands safely via the TerminalTool.
Only runs when the user explicitly asks to run a command.
"""

from services.skills.base import Skill, SkillContext
from services.brain.intent import Intent
from packages.common import logger


class ShellSkill(Skill):

    def __init__(self, terminal_tool):
        self.terminal_tool = terminal_tool

    @property
    def name(self) -> str:
        return "shell"

    def can_handle(self, ctx: SkillContext) -> bool:
        return ctx.intent == Intent.COMMAND_RUN

    def execute(self, ctx: SkillContext) -> dict:
        logger.info("ShellSkill executing")
        result = self.terminal_tool.execute(ctx.message)
        if isinstance(result, dict):
            result["intent"] = ctx.intent.value
            return result
        return {
            "action": "shell",
            "intent": ctx.intent.value,
            "response": str(result),
        }
