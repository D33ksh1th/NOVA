"""
Skill Registry

Stores all registered NOVA skills.
"""

from packages.common import logger


class SkillRegistry:

    def __init__(self):

        self.skills = []

        logger.info("Skill Registry Initialized")

    def register(self, skill):

        logger.info(f"Registered Skill -> {skill.name}")

        self.skills.append(skill)

    def all(self):

        return self.skills