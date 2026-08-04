"""
Base Agent
"""

from abc import ABC
from abc import abstractmethod


class Agent(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def can_handle(
        self,
        message: str,
        intent,
    ) -> bool:
        pass

    @abstractmethod
    def execute(
        self,
        message: str,
        context: dict,
    ):
        pass