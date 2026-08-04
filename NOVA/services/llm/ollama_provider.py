"""
Ollama Provider

Uses the local Ollama server.
"""

import re
import requests

from packages.common import logger

from services.llm.provider import LLMProvider

# Patterns to strip from model responses before returning
_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_TRAILING_PROMPT_RE = re.compile(
    r"\n*(Would you like me to|Do you want me to|Let me know if you|Feel free to ask).*$",
    re.DOTALL | re.IGNORECASE,
)


def _clean_response(text: str) -> str:
    """Remove model artifacts and trailing filler from a response."""
    # Strip <think>...</think> blocks (qwen3 thinking mode)
    text = _THINK_TAG_RE.sub("", text)
    # Strip trailing "Would you like me to..." filler
    text = _TRAILING_PROMPT_RE.sub("", text)
    return text.strip()


class OllamaProvider(LLMProvider):

    def __init__(self):

        self.url = "http://localhost:11434/api/generate"

    def generate(
        self,
        model: str,
        prompt: str,
    ) -> str:

        logger.info(
            f"Ollama -> {model}"
        )

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }

        try:

            response = requests.post(
                self.url,
                json=payload,
                timeout=300,
            )

            response.raise_for_status()

            data = response.json()

            raw = data.get("response", "No response from model.")

            return _clean_response(raw)

        except Exception as ex:

            logger.error(f"Ollama Error -> {ex}")

            return "Unable to communicate with Ollama."