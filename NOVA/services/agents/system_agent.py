"""
System Agent
"""

from services.agents.base import Agent


class SystemAgent(Agent):

    def __init__(self, tool_manager):

        self.tool_manager = tool_manager

    @property
    def name(self):

        return "system"

    def can_handle(
        self,
        message,
        intent,
    ):

        text = message.lower()

        keywords = [

            "system",

            "system information",

            "system info",

            "computer",

            "device",

            "machine",

            "specs",

            "specifications",

            "hardware",

            "configuration",

            "mac",

            "macbook",

            "laptop",

            "pc",

            "windows",

            "hostname",

            "processor",

        ]

        return any(
            word in text
            for word in keywords
        )

    def execute(
        self,
        message,
        context,
    ):

        return self.tool_manager.execute(
            message
        )