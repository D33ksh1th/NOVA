"""
General System Collector
"""

import getpass
import os
import platform
import socket
import sys
from datetime import datetime

import psutil

from .base import Collector


class GeneralCollector(Collector):

    @property
    def name(self):
        return "general"

    def collect(self):

        boot_timestamp = psutil.boot_time()

        now = datetime.now()

        uptime_seconds = int(
            now.timestamp() - boot_timestamp
        )

        boot = datetime.fromtimestamp(
            boot_timestamp
        )

        return {

            "username": getpass.getuser(),

            "hostname": socket.gethostname(),

            "fqdn": socket.getfqdn(),

            "current_time": now.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),

            "timezone": str(
                datetime.now().astimezone().tzinfo
            ),

            "boot_time": boot.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),

            "uptime_seconds": uptime_seconds,

            "platform": platform.system(),

            "platform_release": platform.release(),

            "platform_version": platform.version(),

            "architecture": platform.machine(),

            "processor": platform.processor(),

            "python_version": platform.python_version(),

            "python_executable": sys.executable,

            "working_directory": os.getcwd(),

            "home_directory": os.path.expanduser("~"),

            "virtual_environment": os.environ.get(
                "VIRTUAL_ENV"
            ),

        }