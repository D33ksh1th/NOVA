"""
Battery Collector
"""

import platform
import subprocess

import psutil

from .base import Collector


class BatteryCollector(Collector):

    @property
    def name(self):

        return "battery"

    def collect(self):

        data = {}

        try:

            battery = psutil.sensors_battery()

            if battery:

                data["percentage"] = battery.percent
                data["charging"] = battery.power_plugged
                data["seconds_left"] = battery.secsleft

        except Exception:

            pass

        system = platform.system()

        try:

            if system == "Darwin":

                output = subprocess.check_output(

                    [
                        "system_profiler",
                        "SPPowerDataType",
                    ],

                    text=True,

                )

                parsed = {}

                for line in output.splitlines():

                    if ":" not in line:
                        continue

                    key, value = line.split(":", 1)

                    parsed[
                        key.strip().lower().replace(" ", "_")
                    ] = value.strip()

                data.update({

                    "condition":
                        parsed.get("condition"),

                    "cycle_count":
                        parsed.get("cycle_count"),

                    "maximum_capacity":
                        parsed.get("maximum_capacity"),

                    "full_charge_capacity":
                        parsed.get(
                            "full_charge_capacity_(mah)"
                        ),

                })

        except Exception:

            pass

        return data