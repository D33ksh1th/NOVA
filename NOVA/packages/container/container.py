"""
Application Container

Creates and owns shared infrastructure used across NOVA.
"""

from packages.common import logger

from services.brain.context import ContextEngine
from services.memory.context import MemoryContext
from services.llm.prompts import PromptBuilder

from services.context import (
    SystemContext,
    LocationContext,
    WeatherContext,
)


class ApplicationContainer:

    def __init__(self, memory):

        logger.info("Application Container Initializing...")

        # -----------------------------
        # Context Engines
        # -----------------------------

        self.context_engine = ContextEngine()

        self.system_context = SystemContext()

        self.location_context = LocationContext()

        self.weather_context = WeatherContext()

        self.memory_context = MemoryContext(memory)

        # -----------------------------
        # Prompt Builder
        # -----------------------------

        self.prompt_builder = PromptBuilder()

        logger.info("Application Container Ready")