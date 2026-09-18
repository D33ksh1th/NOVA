"""
Weather Context
"""

import requests


class WeatherContext:

    def build(
        self,
        latitude,
        longitude,
    ):

        if latitude is None or longitude is None:

            return {}

        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={latitude}"
            f"&longitude={longitude}"
            "&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
        )

        try:

            response = requests.get(
                url,
                timeout=10,
            )

            data = response.json()["current"]

            return {

                "temperature": data["temperature_2m"],

                "humidity": data["relative_humidity_2m"],

                "weather_code": data["weather_code"],

                "wind_speed": data.get("wind_speed_10m"),

            }

        except Exception:

            return {}