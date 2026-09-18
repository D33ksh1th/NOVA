"""
Mac Skill

Routes app launch and clipboard commands to MacTool.
No LLM — direct tool dispatch.
"""

import re

from services.skills.base import Skill, SkillContext
from services.brain.intent import Intent
from packages.common import logger
from services.tools.apple_music import music_followup_message, parse_music_request


class MacSkill(Skill):

    def __init__(self, mac_tool):
        self.mac_tool = mac_tool

    @property
    def name(self) -> str:
        return "mac"

    def can_handle(self, ctx: SkillContext) -> bool:
        if (ctx.context or {}).get("music_choice_pending") and music_followup_message(ctx.message):
            return True
        if parse_music_request(ctx.message):
            return True
        if ctx.intent in (Intent.APP_LAUNCH, Intent.CLIPBOARD):
            return True
        text = ctx.message.lower()
        favorite_music_pattern = re.search(
            r"\b(play|start)\b[\s,]+(my[\s,]+)?(favorite|favourite|fav(?:ou)?rite|favroute|favrite)\b[\s,]+music\b",
            text,
        )
        playlist_pattern = re.search(r"\b(play|start)\b[\s,]+(my[\s,]+)?playlist\b", text)
        resume_music_pattern = re.search(
            r"\b(play|resume|start)\b[\s,]+(the[\s,]+)?(apple[\s,]+)?music\b",
            text,
        )
        pause_music_pattern = re.search(
            r"\b(pause|stop)\b[\s,]+(the[\s,]+)?(apple[\s,]+)?music\b",
            text,
        )
        if favorite_music_pattern or playlist_pattern or resume_music_pattern or pause_music_pattern:
            return True
        return any(k in text for k in [
            "open ", "launch ", "start the app",
            "clipboard", "what's in my clipboard", "copy that",
            "play my favorite music", "play my favourite music", "play my favroute music",
            "start my playlist", "play my playlist",
        ])

    def execute(self, ctx: SkillContext) -> dict:
        logger.info("MacSkill executing")
        message = ctx.message
        if (ctx.context or {}).get("music_choice_pending"):
            message = music_followup_message(message) or message
        result = self.mac_tool.execute(message)
        result["intent"] = ctx.intent.value
        return result
