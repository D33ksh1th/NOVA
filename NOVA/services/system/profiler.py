"""
System Profiler
"""

from services.system.collectors.general import GeneralCollector
from services.system.collectors.hardware import HardwareCollector
from services.system.collectors.cpu import CPUCollector
from services.system.collectors.memory import MemoryCollector
from services.system.collectors.storage import StorageCollector
from services.system.collectors.network import NetworkCollector
from services.system.collectors.battery import BatteryCollector
from services.system.collectors.display import DisplayCollector
from services.system.collectors.python import PythonCollector



class SystemProfiler:

    def __init__(self):

        self.general = GeneralCollector()

        self.hardware = HardwareCollector()

        self.cpu = CPUCollector()

        self.memory = MemoryCollector()

        self.storage = StorageCollector()

        self.network = NetworkCollector()

        self.battery = BatteryCollector()

        self.display = DisplayCollector()

        self.python = PythonCollector()

        self.network = NetworkCollector()

    def collect(self):

        return {

            "general": self.general.collect(),

            "hardware": self.hardware.collect(),

            "cpu": self.cpu.collect(),

            "memory": self.memory.collect(),

            "storage": self.storage.collect(),

            "network": self.network.collect(),

            "battery": self.battery.collect(),

            "display": self.display.collect(),

            "python": self.python.collect(),

        }