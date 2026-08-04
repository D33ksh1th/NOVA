"""
Agent Manager
"""

from packages.common import logger


class AgentManager:

    def __init__(
        self,
        registry,
    ):

        logger.info("Agent Manager Initialized")

        self.registry = registry

    def execute(
        self,
        message,
        intent,
        context,
    ):

        for agent in self.registry.all():

            if agent.can_handle(
                message,
                intent,
            ):

                logger.info(
                    f"Agent Selected -> {agent.name}"
                )

                return agent.execute(
                    message,
                    context,
                )

        return None