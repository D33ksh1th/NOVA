"""
Display Collector
"""

import platform
import subprocess

from .base import Collector


class DisplayCollector(Collector):

    @property
    def name(self):
        return "display"

    def collect(self):

        system = platform.system()

        try:

            if system == "Darwin":

                output = subprocess.check_output(
                    ["system_profiler", "SPDisplaysDataType"],
                    text=True,
                )

                return {
                    "raw": output
                }

            elif system == "Windows":

                output = subprocess.check_output(
                    [
                        "wmic",
                        "path",
                        "Win32_VideoController",
                        "get",
                        "Name",
                    ],
                    text=True,
                )

                return {
                    "raw": output
                }

            else:

                return {}

        except Exception as ex:

            return {
                "error": str(ex)
            }