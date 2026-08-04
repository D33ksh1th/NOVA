from services.llm import LLMClient
from services.llm.models import LLMRequest


class ModelProvider:

    def __init__(self):

        self.client = LLMClient()

    def generate(
        self,
        model,
        prompt,
    ):

        return self.client.generate(
            LLMRequest(
                model=model,
                prompt=prompt,
            )
        )