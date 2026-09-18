"""
Base Collector
"""

from abc import ABC
from abc import abstractmethod


class Collector(ABC):

    @property
    @abstractmethod
    def name(self):
        pass

    @abstractmethod
    def collect(self):
        pass