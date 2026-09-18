"""
Web Search Skill

Routes web search queries to WebSearchTool.
No LLM — the tool result IS the response.
"""

from services.skills.base import Skill, SkillContext
from services.brain.intent import Intent
from packages.common import logger


class WebSearchSkill(Skill):

    def __init__(self, web_search_tool):
        self.web_search_tool = web_search_tool

    @property
    def name(self) -> str:
        return "web_search"

    def can_handle(self, ctx: SkillContext) -> bool:
        if ctx.intent == Intent.WEB_SEARCH:
            return True
        text = ctx.message.lower()
        return any(k in text for k in [
            "search for", "search about", "look up", "google",
            "find online", "search the web",
        ])

    def execute(self, ctx: SkillContext) -> dict:
        logger.info("WebSearchSkill executing")
        result = self.web_search_tool.execute(ctx.message)
        result["intent"] = ctx.intent.value
        return result
