"""Vision skill for OCR, image analysis, and browser automation."""

from services.brain.intent import Intent
from services.skills.base import Skill, SkillContext


class VisionSkill(Skill):
    def __init__(self, vision_tool):
        self.vision_tool = vision_tool

    @property
    def name(self) -> str:
        return "vision"

    def can_handle(self, ctx: SkillContext) -> bool:
        return ctx.intent in {Intent.VISION_QUERY, Intent.AUTOMATION_QUERY}

    def execute(self, ctx: SkillContext) -> dict:
        result = self.vision_tool.execute(ctx.message)
        if isinstance(result, dict):
            result.setdefault("intent", ctx.intent.value)
            return result
        return {
            "action": "vision",
            "intent": ctx.intent.value,
            "response": str(result),
        }
