"""
Tool Registry
"""


class ToolRegistry:

    def __init__(self):
        self.tools = []

    def register(self, tool):
        self.tools.append(tool)

    def all(self):
        return self.tools

    def find_by_name(self, name: str):
        """
        Find a registered tool by its class name.
        """

        for tool in self.tools:
            if tool.__class__.__name__ == name:
                return tool

        return None