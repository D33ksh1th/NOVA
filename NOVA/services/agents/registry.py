"""
Agent Registry
"""

from packages.common import logger


class AgentRegistry:

    def __init__(self):

        logger.info("Agent Registry Initialized")

        self._agents = []

    def register(self, agent):

        logger.info(
            f"Registered Agent -> {agent.name}"
        )

        self._agents.append(agent)

    def all(self):

        return self._agents