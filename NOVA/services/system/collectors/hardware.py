"""
Hardware Collector

Cross-platform hardware information.
Supports:
- macOS
- Windows
- Linux
"""

import platform
import subprocess

from .base import Collector


class HardwareCollector(Collector):

    @property
    def name(self):

        return "hardware"

    def collect(self):

        system = platform.system()

        try:

            if system == "Darwin":
                return self._collect_macos()

            if system == "Windows":
                return self._collect_windows()

            if system == "Linux":
                return self._collect_linux()

        except Exception as ex:

            return {
                "error": str(ex)
            }

        return {}

    # ------------------------------------------------

    def _collect_macos(self):

        output = subprocess.check_output(
            [
                "system_profiler",
                "SPHardwareDataType",
            ],
            text=True,
        )

        data = {}

        for line in output.splitlines():

            if ":" not in line:
                continue

            key, value = line.split(":", 1)

            key = key.strip().lower().replace(" ", "_")

            data[key] = value.strip()

        return {

            "manufacturer": "Apple",

            "model": data.get("model_name"),

            "model_identifier": data.get("model_identifier"),

            "chip": data.get("chip"),

            "memory": data.get("memory"),

            "serial_number": data.get("serial_number_(system)"),

            "hardware_uuid": data.get("hardware_uuid"),

            "boot_rom": data.get("system_firmware_version"),

        }

    # ------------------------------------------------

    def _collect_windows(self):

        output = subprocess.check_output(

            [
                "wmic",
                "computersystem",
                "get",
                "manufacturer,model,totalphysicalmemory",
            ],

            text=True,

        )

        return {

            "raw": output.strip()

        }

    # ------------------------------------------------

    def _collect_linux(self):

        output = subprocess.check_output(
            [
                "hostnamectl"
            ],
            text=True,
        )

        return {

            "raw": output.strip()

        }