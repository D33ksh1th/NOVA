"""
Python Collector
"""

import os
import sys

from .base import Collector


class PythonCollector(Collector):

    @property
    def name(self):
        return "python"

    def collect(self):

        return {

            "version": sys.version,

            "executable": sys.executable,

            "virtual_environment": os.environ.get(
                "VIRTUAL_ENV"
            ),

            "cwd": os.getcwd(),

        }