"""
Skill Manager

Selects and dispatches to the correct skill.
"""

from typing import Optional
from packages.common import logger
from services.skills.base import SkillContext


class SkillManager:

    def __init__(self, registry):
        self.registry = registry
        logger.info("Skill Manager Initialized")

    def dispatch(self, ctx: SkillContext) -> Optional[dict]:
        """
        Find the first skill that can handle the context and execute it.
        Returns None if no skill matched (caller falls back to legacy path).
        """
        logger.info(f"SkillManager dispatching -> intent={ctx.intent.value}")

        for skill in self.registry.all():
            if skill.can_handle(ctx):
                logger.info(f"SkillManager -> selected: {skill.name}")
                return skill.execute(ctx)

        logger.info("SkillManager -> no skill matched, falling back")
        return None