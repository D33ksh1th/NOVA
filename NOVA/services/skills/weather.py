"""
Weather Skill

Fetches live weather data via the WeatherTool.
No LLM involved — direct tool → response.
"""

from services.skills.base import Skill, SkillContext
from services.brain.intent import Intent
from packages.common import logger


class WeatherSkill(Skill):

    def __init__(self, weather_tool):
        self.weather_tool = weather_tool

    @property
    def name(self) -> str:
        return "weather"

    def can_handle(self, ctx: SkillContext) -> bool:
        if ctx.intent == Intent.WEATHER_QUERY:
            return True
        text = ctx.message.lower()
        keywords = ["weather", "temperature", "forecast", "humidity", "rain", "wind"]
        return any(k in text for k in keywords)

    def execute(self, ctx: SkillContext) -> dict:
        logger.info("WeatherSkill executing")
        result = self.weather_tool.execute(ctx.message)
        result["intent"] = ctx.intent.value
        return result
