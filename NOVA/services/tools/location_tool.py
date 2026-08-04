"""
Location Tool
"""

from services.tools.base import Tool


class LocationTool(Tool):

    def __init__(self, location_context):

        self.location_context = location_context

    @property
    def name(self):

        return "location"

    def can_handle(self, message: str):

        text = message.lower()

        keywords = [
            "location",
            "where am i",
            "where are we",
            "current location",
            "my location",
            "which city",
            "where do i live",
        ]

        return any(
            keyword in text
            for keyword in keywords
        )

    def execute(self, message: str):

        location = self.location_context.build()

        city = location.get("city") or "Unknown city"
        state = location.get("state") or ""
        country = location.get("country") or "Unknown country"

        parts = [p for p in [city, state, country] if p]
        location_str = ", ".join(parts)

        return {
            "action": "location",
            "success": True,
            "location": location,
            "response": f"Your current location is {location_str}.",
        }