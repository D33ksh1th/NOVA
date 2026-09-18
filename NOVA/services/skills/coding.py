"""
Coding Skill

Routes coding and programming questions through the code-optimised
LLM model (qwen3:8b) via the model manager.

The TaskPlanner is used for complex coding requests (e.g. "build an app")
while single questions go directly to the LLM.
"""

from services.skills.base import Skill, SkillContext
from services.brain.intent import Intent
from packages.common import logger


_SYSTEM_PROMPT = """You are NOVA's coding engine.

You are an expert software engineer with deep knowledge across all languages,
frameworks, and paradigms.

Rules:
- Write complete, runnable code — never pseudocode unless asked.
- Include comments only where non-obvious.
- Follow best practices and modern idioms for the language.
- If multiple approaches exist, use the best one and briefly explain why.
- Always specify the language in code blocks.
- Do not add unnecessary boilerplate or repeated imports.
"""


class CodingSkill(Skill):

    def __init__(self, model_manager):
        self.model_manager = model_manager

    @property
    def name(self) -> str:
        return "coding"

    def can_handle(self, ctx: SkillContext) -> bool:
        return ctx.intent == Intent.CODE_HELP

    def _preferred_language_from_memory(self, memory):
        if not memory:
            return None

        # Preferred shape: dict-like
        if hasattr(memory, "get"):
            return memory.get("favorite_language")

        # Fallback shape: list/tuple of memory records
        if isinstance(memory, (list, tuple)):
            for item in memory:
                # Dict record: {"key": "favorite_language", "value": "python"}
                if isinstance(item, dict):
                    if item.get("key") == "favorite_language":
                        return item.get("value")
                    if "favorite_language" in item:
                        return item.get("favorite_language")

                # Object record: item.key/item.value
                key = getattr(item, "key", None)
                if key == "favorite_language":
                    return getattr(item, "value", None)

        return None

    def execute(self, ctx: SkillContext) -> dict:
        logger.info("CodingSkill executing")

        memory_block = ""
        lang = self._preferred_language_from_memory(ctx.memory)
        if lang:
            memory_block = f"\nUser's preferred language: {lang}.\n"

        prompt = (
            f"{_SYSTEM_PROMPT}"
            f"{memory_block}"
            f"\nUser request:\n{ctx.message}"
            f"\n\nRespond directly with code and a brief explanation."
        )

        result = self.model_manager.generate(
            message=ctx.message,
            prompt=prompt,
        )

        text = result.text if hasattr(result, "text") else str(result)

        return {
            "action": "coding",
            "intent": ctx.intent.value,
            "response": text,
        }
