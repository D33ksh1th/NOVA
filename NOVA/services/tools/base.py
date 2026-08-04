"""
Base Tool
"""

from abc import ABC, abstractmethod


class Tool(ABC):

    @property
    @abstractmethod
    def name(self):
        pass

    @abstractmethod
    def can_handle(
        self,
        message: str,
    ) -> bool:
        pass

    @abstractmethod
    def execute(
        self,
        message: str,
    ):
        pass