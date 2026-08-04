"""
LLM Provider
"""

from abc import ABC, abstractmethod


class LLMProvider(ABC):

    @abstractmethod
    def generate(
        self,
        model: str,
        prompt: str,
    ) -> str:
        pass