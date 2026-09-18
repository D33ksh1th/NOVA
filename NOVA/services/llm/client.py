"""
LLM Client
"""

from services.llm.models import LLMRequest, LLMResponse
from services.llm.provider import LLMProvider
from services.llm.ollama_provider import OllamaProvider


class MockProvider(LLMProvider):

    def generate(
        self,
        model: str,
        prompt: str,
    ) -> str:

        return (
            f"[{model}] "
            "This is a mock response from NOVA."
        )


class LLMClient:

    def __init__(self):

        # Swap this to MockProvider() if you want mock responses
        self.provider = OllamaProvider()

    def generate(
        self,
        request: LLMRequest,
    ) -> LLMResponse:

        response = self.provider.generate(
            model=request.model,
            prompt=request.prompt,
        )

        return LLMResponse(
            text=response,
            model=request.model,
        )