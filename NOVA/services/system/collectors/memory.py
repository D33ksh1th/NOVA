"""
Memory Collector
"""

import psutil

from .base import Collector


class MemoryCollector(Collector):

    @property
    def name(self):

        return "memory"

    def _bytes_to_gb(self, value):

        return round(value / (1024 ** 3), 2)

    def collect(self):

        try:

            memory = psutil.virtual_memory()

            swap = psutil.swap_memory()

            return {

                "total_gb": self._bytes_to_gb(memory.total),

                "available_gb": self._bytes_to_gb(
                    memory.available
                ),

                "used_gb": self._bytes_to_gb(
                    memory.used
                ),

                "free_gb": self._bytes_to_gb(
                    memory.free
                ),

                "memory_usage_percent": memory.percent,

                "cached_gb": self._bytes_to_gb(
                    getattr(memory, "cached", 0)
                ),

                "buffers_gb": self._bytes_to_gb(
                    getattr(memory, "buffers", 0)
                ),

                "swap_total_gb": self._bytes_to_gb(
                    swap.total
                ),

                "swap_used_gb": self._bytes_to_gb(
                    swap.used
                ),

                "swap_free_gb": self._bytes_to_gb(
                    swap.free
                ),

                "swap_percent": swap.percent,

            }

        except Exception as ex:

            return {

                "error": str(ex)

            }