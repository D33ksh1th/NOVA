"""
Model Manager
"""

from packages.common import logger

from services.models.router import ModelRouter
from services.models.provider import ModelProvider
from services.models.classifier import TaskClassifier


class ModelManager:

    def __init__(self):

        logger.info("Model Manager Initialized")

        self.router = ModelRouter()

        self.provider = ModelProvider()

        self.classifier = TaskClassifier()

    def generate(
        self,
        message: str,
        prompt: str,
    ):
        task = self.classifier.classify(message)
        model = self.router.route(task)

        return self.provider.generate(
            model=model,
            prompt=prompt,
        )