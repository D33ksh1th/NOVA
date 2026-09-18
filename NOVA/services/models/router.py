"""
Model Router

Selects the best AI model for a task.
"""

from packages.common import logger
from packages.config import settings

from services.models.task import ModelTask


class ModelRouter:

    def route(self, task: ModelTask) -> str:

        logger.info(f"Selecting model for {task.value}")

        if task == ModelTask.CHAT:
            return settings.CHAT_MODEL

        if task == ModelTask.CODING:
            return settings.CODE_MODEL

        if task == ModelTask.EMBEDDING:
            return settings.EMBEDDING_MODEL

        if task == ModelTask.SECURITY:
            return settings.CODE_MODEL

        if task == ModelTask.REASONING:
            return settings.REASONING_MODEL

        return settings.CHAT_MODEL