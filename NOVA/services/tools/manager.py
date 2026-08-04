"""
Tool Manager
"""

from packages.common import logger


class ToolManager:

    def __init__(
        self,
        registry,
    ):

        self.registry = registry

    def execute(
        self,
        message: str,
    ):

        for tool in self.registry.all():

            if tool.can_handle(message):

                logger.info(
                    f"Tool Selected -> {tool.name}"
                )

                return tool.execute(message)

        return None