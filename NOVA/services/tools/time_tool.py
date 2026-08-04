"""
Time Tool
"""

from datetime import datetime
from zoneinfo import ZoneInfo
import re

from services.tools.base import Tool


class TimeTool(Tool):

    @property
    def name(self):

        return "time"

    def can_handle(
        self,
        message: str,
    ) -> bool:

        text = message.lower()

        keywords = [

            "time",

            "current time",

            "what time",

            "time now",

            "clock",

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

        text = (message or "").lower().strip()

        # Build a natural 12-hour format without a leading zero in the hour.
        hour_12 = now.hour % 12 or 12
        minute = now.minute
        am_pm = now.strftime("%p")
        pretty_time = f"{hour_12}:{minute:02d} {am_pm}"

        asks_day = bool(re.search(r"\b(what\s+day\s+is\s+(it|today)|which\s+day|day\s+is\s+it|today\s+is\s+which\s+day)\b", text))
        asks_date = bool(re.search(r"\b(date|today'?s\s+date|what\s+is\s+the\s+date)\b", text))
        asks_time = bool(re.search(r"\b(time|clock|what\s+time|current\s+time|time\s+now)\b", text))

        if asks_day and not asks_time:
            return {
                "action": "time",
                "response": f"Today is {now.strftime('%A')}.",
            }

        if asks_date and not asks_time:
            return {
                "action": "time",
                "response": f"Today is {now.strftime('%d %B %Y')}.",
            }

        if asks_time and not (asks_day or asks_date):
            return {
                "action": "time",
                "response": f"It is {pretty_time}.",
            }

        # Combined request (time + date/day), keep concise.
        return {
            "action": "time",
            "response": f"It is {pretty_time}, {now.strftime('%A, %d %B %Y')}.",
        }