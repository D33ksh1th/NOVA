"""
Coding Agent
"""

from services.agents.base import Agent


class CodingAgent(Agent):

    def __init__(self, tool_manager):

        self.tool_manager = tool_manager

    @property
    def name(self):

        return "coding"

    def can_handle(self, message, intent):

        text = message.lower()

        keywords = [

            "run",

            "execute",

            "terminal",

            "command",

            "shell",

            "python",

            "git",

            "mkdir",

            "create file",

            "create folder",

            "pwd",

            "ls",

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

        return self.tool_manager.execute(message)