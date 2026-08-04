"""
Date Tool
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from services.tools.base import Tool


class DateTool(Tool):

    @property
    def name(self):

        return "date"

    def can_handle(
        self,
        message: str,
    ) -> bool:

        text = message.lower()

        keywords = [

            "today",

            "current date",

            "what is today's date",

            "what is the date",

            "date today",

        ]

        return any(
            keyword in text
            for keyword in keywords
        )

    def execute(
        self,
        message: str,
    ):

        now = datetime.now(
            ZoneInfo("Asia/Kolkata")
        )

        return {

            "action": "date",

            "response":
                f"Today is {now.strftime('%A, %d %B %Y')}."

        }