"""
CPU Collector
"""

import platform

import psutil

from .base import Collector


class CPUCollector(Collector):

    @property
    def name(self):

        return "cpu"

    def collect(self):

        try:

            frequency = psutil.cpu_freq()

            load = None

            if hasattr(psutil, "getloadavg"):

                try:
                    load = psutil.getloadavg()
                except Exception:
                    load = None

            return {

                "processor": platform.processor(),

                "architecture": platform.machine(),

                "physical_cores": psutil.cpu_count(
                    logical=False
                ),

                "logical_cores": psutil.cpu_count(
                    logical=True
                ),

                "current_frequency_mhz":
                    round(frequency.current, 2)
                    if frequency else None,

                "min_frequency_mhz":
                    round(frequency.min, 2)
                    if frequency else None,

                "max_frequency_mhz":
                    round(frequency.max, 2)
                    if frequency else None,

                "cpu_usage_percent":
                    psutil.cpu_percent(interval=1),

                "load_average": load,

            }

        except Exception as ex:

            return {

                "error": str(ex)

            }