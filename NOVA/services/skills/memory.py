"""
Memory Skill
"""

from services.skills.base import Skill
from services.skills.base import SkillContext
from services.brain.intent import Intent


class MemorySkill(Skill):

    def __init__(self, memory):

        self.memory = memory

    @property
    def name(self):

        return "memory"

    def can_handle(self, ctx: SkillContext) -> bool:
        return ctx.intent == Intent.MEMORY_STORE

    def execute(self, ctx: SkillContext) -> dict:
        text = ctx.message.replace("remember", "").strip()

        if "=" not in text:
            return {
                "action": "memory_store",
                "success": False,
                "response": "To store something say: remember key=value",
            }

        key, value = text.split("=", 1)
        self.memory.remember(key.strip(), value.strip())

        return {
            "action": "memory_store",
            "intent": ctx.intent.value,
            "success": True,
            "key": key.strip(),
            "value": value.strip(),
            "response": f"Stored: {key.strip()} = {value.strip()}",
        }