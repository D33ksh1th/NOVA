"""
Decision Engine
"""

from packages.common import logger


class DecisionEngine:

    def decide(self, intent):

        logger.info(f"Decision Engine -> {intent}")

        return intent