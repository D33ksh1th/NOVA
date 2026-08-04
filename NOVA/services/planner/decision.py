"""
Decision Engine
"""

from packages.common import logger

from .models import Decision


class DecisionEngine:

    def __init__(self):
        logger.info("Decision Engine Initialized")

    def decide(self, message: str) -> Decision:

        text = message.lower().strip()

        decision = Decision()
        decision.use_memory = True

        # -----------------------------
        # Location
        # -----------------------------
        location_keywords = [
            "location",
            "where am i",
            "current location",
            "my location",
            "which city am i in",
            "which city are we in",
            "what city is this",
            "where are we",
        ]

        if any(keyword in text for keyword in location_keywords):
            decision.use_tool = True
            decision.tool = "LocationTool"
            decision.answer_directly = False
            decision.confidence = 0.99
            decision.reasoning = "Current location requested."
            return decision

        # -----------------------------
        # Time
        # -----------------------------
        time_keywords = [
            "time",
            "current time",
            "what time",
            "clock",
        ]

        if any(keyword in text for keyword in time_keywords):
            decision.use_tool = True
            decision.tool = "TimeTool"
            decision.answer_directly = False
            decision.confidence = 0.99
            decision.reasoning = "Current time requested."
            return decision

        # -----------------------------
        # Date
        # -----------------------------
        date_keywords = [
            "today's date",
            "current date",
            "what day is it",
            "what date is it",
            "date today",
        ]

        if any(keyword in text for keyword in date_keywords):
            decision.use_tool = True
            decision.tool = "DateTool"
            decision.answer_directly = False
            decision.confidence = 0.99
            decision.reasoning = "Current date requested."
            return decision

        # -----------------------------
        # System Information
        # -----------------------------
        system_keywords = [
            "system",
            "computer",
            "device",
            "machine",
            "laptop",
            "desktop",
            "mac",
            "macbook",
            "windows",
            "hardware",
            "spec",
            "specification",
            "configuration",
            "ram",
            "memory",
            "cpu",
            "processor",
            "gpu",
            "graphics",
            "disk",
            "storage",
            "battery",
            "display",
            "screen",
            "network",
            "wifi",
            "ethernet",
            "python",
            "os",
            "operating system",
        ]

        if any(keyword in text for keyword in system_keywords):
            decision.use_tool = True
            decision.tool = "SystemInfoTool"
            decision.answer_directly = False
            decision.confidence = 0.95
            decision.reasoning = "System information requested."
            return decision

        # -----------------------------
        # Weather
        # -----------------------------
        weather_keywords = [
            "weather",
            "temperature",
            "forecast",
            "rain",
            "humidity",
            "wind",
        ]

        if any(keyword in text for keyword in weather_keywords):
            decision.use_tool = True
            decision.tool = "WeatherTool"
            decision.answer_directly = False
            decision.confidence = 0.95
            decision.reasoning = "Weather information requested."
            return decision

        # -----------------------------
        # Default Chat
        # -----------------------------
        decision.use_tool = False
        decision.answer_directly = True
        decision.confidence = 0.70
        decision.reasoning = "General conversation."

        return decision