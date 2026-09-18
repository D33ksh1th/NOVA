from datetime import datetime
from zoneinfo import ZoneInfo
import platform


class SystemContext:

    def build(self):

        now = datetime.now(
            ZoneInfo("Asia/Kolkata")
        )

        return {

            "date": now.strftime("%d %B %Y"),

            "time": now.strftime("%H:%M:%S"),

            "weekday": now.strftime("%A"),

            "timezone": "Asia/Kolkata",

            "os": platform.system(),

            "hostname": platform.node(),

        }