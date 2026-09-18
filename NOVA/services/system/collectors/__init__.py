from .base import Collector

from .general import GeneralCollector
from .hardware import HardwareCollector
from .cpu import CPUCollector
from .memory import MemoryCollector
from .storage import StorageCollector
from .network import NetworkCollector
from .battery import BatteryCollector
from .display import DisplayCollector
from .python import PythonCollector

__all__ = [
    "Collector",
    "GeneralCollector",
    "HardwareCollector",
    "CPUCollector",
    "MemoryCollector",
    "StorageCollector",
    "NetworkCollector",
    "BatteryCollector",
    "DisplayCollector",
    "PythonCollector",
]