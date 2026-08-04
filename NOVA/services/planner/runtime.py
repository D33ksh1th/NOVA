"""
Runtime Engine
"""

from packages.common import logger


class RuntimeEngine:

    def __init__(

        self,

        tool_registry,

    ):

        self.tool_registry = tool_registry

        logger.info("Runtime Engine Initialized")

    def execute(self, decision, message):

        if not decision.use_tool:
            return None

        tool = self.tool_registry.find_by_name(
            decision.tool
        )

        if tool is None:

            logger.warning(
                f"Tool not found -> {decision.tool}"
            )

            return None

        logger.info(
            f"Executing Tool -> {decision.tool}"
        )

        return tool.execute(message)