"""
Terminal Tool
"""

import subprocess

from services.tools.base import Tool


class TerminalTool(Tool):

    @property
    def name(self):

        return "terminal"

    def can_handle(self, message: str) -> bool:

        text = message.lower()

        keywords = [
            "run",
            "execute",
            "terminal",
            "command",
            "shell",
        ]

        return any(word in text for word in keywords)

    def execute(self, message: str):

        command = (
            message.lower()
            .replace("run", "")
            .replace("execute", "")
            .replace("command", "")
            .replace("terminal", "")
            .strip()
        )

        if not command:

            return {
                "action": "terminal",
                "success": False,
                "response": "No command provided."
            }

        try:

            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
            )

            return {

                "action": "terminal",

                "command": command,

                "exit_code": result.returncode,

                "stdout": result.stdout,

                "stderr": result.stderr,

            }

        except Exception as ex:

            return {

                "action": "terminal",

                "success": False,

                "response": str(ex),

            }