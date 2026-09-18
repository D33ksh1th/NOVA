"""
Weather Tool
"""

from services.tools.base import Tool

from packages.common import logger

# WMO weather code → human-readable condition
# https://open-meteo.com/en/docs#weathervariables
_WMO_CONDITIONS = {
    0: "Clear sky",
    1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Foggy", 48: "Icy fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    80: "Slight showers", 81: "Moderate showers", 82: "Violent showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Heavy thunderstorm with hail",
}


class WeatherTool(Tool):

    def __init__(
        self,
        location_context,
        weather_context,
    ):

        self.location_context = location_context
        self.weather_context = weather_context

    @property
    def name(self):
        return "weather"

    def can_handle(self, message: str):
        text = message.lower()
        keywords = [
            "weather", "temperature", "forecast",
            "humidity", "outside", "rain", "climate", "wind",
        ]
        return any(keyword in text for keyword in keywords)

    def execute(self, message: str):

        try:
            location = self.location_context.build()

            if not location:
                return {
                    "action": "weather",
                    "success": False,
                    "response": "Unable to determine your location.",
                }

            logger.info(f"Location -> {location}")

            weather = self.weather_context.build(
                location.get("latitude"),
                location.get("longitude"),
            )

            logger.info(f"Weather -> {weather}")

            if not weather:
                return {
                    "action": "weather",
                    "success": False,
                    "response": "Unable to retrieve weather data at the moment.",
                }

            temperature = weather.get("temperature", "N/A")
            humidity = weather.get("humidity", "N/A")
            wind = weather.get("wind_speed", "N/A")
            code = weather.get("weather_code")
            condition = _WMO_CONDITIONS.get(code, "Unknown") if code is not None else "Unknown"
            city = location.get("city") or location.get("region") or "your location"

            response = (
                f"Current weather in {city}:\n"
                f"  Condition   : {condition}\n"
                f"  Temperature : {temperature}°C\n"
                f"  Humidity    : {humidity}%\n"
                f"  Wind speed  : {wind} km/h"
            )

            return {
                "action": "weather",
                "success": True,
                "location": location,
                "weather": weather,
                "response": response,
            }

        except Exception as ex:
            logger.exception(ex)
            return {
                "action": "weather",
                "success": False,
                "response": f"Weather lookup failed: {ex}",
            }