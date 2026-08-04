"""
Storage Collector
"""

from pathlib import Path

import psutil

from .base import Collector


class StorageCollector(Collector):

    @property
    def name(self):

        return "storage"

    def _bytes_to_gb(self, value):

        return round(value / (1024 ** 3), 2)

    def collect(self):

        try:

            disks = []

            partitions = psutil.disk_partitions()

            for partition in partitions:

                try:

                    usage = psutil.disk_usage(
                        partition.mountpoint
                    )

                    disks.append({

                        "device": partition.device,

                        "mount_point": partition.mountpoint,

                        "filesystem": partition.fstype,

                        "total_gb": self._bytes_to_gb(
                            usage.total
                        ),

                        "used_gb": self._bytes_to_gb(
                            usage.used
                        ),

                        "free_gb": self._bytes_to_gb(
                            usage.free
                        ),

                        "usage_percent": usage.percent,

                    })

                except PermissionError:

                    continue

            cwd = Path.cwd()

            cwd_usage = psutil.disk_usage(cwd)

            return {

                "current_directory": str(cwd),

                "current_drive": {

                    "total_gb": self._bytes_to_gb(
                        cwd_usage.total
                    ),

                    "used_gb": self._bytes_to_gb(
                        cwd_usage.used
                    ),

                    "free_gb": self._bytes_to_gb(
                        cwd_usage.free
                    ),

                    "usage_percent": cwd_usage.percent,

                },

                "partitions": disks,

            }

        except Exception as ex:

            return {

                "error": str(ex)

            }