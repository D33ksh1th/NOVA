"""
Ollama Provider

Uses the local Ollama server.
"""

import re
import requests
from urllib.parse import urlparse

from packages.common import logger
from packages.config import settings

from services.llm.provider import LLMProvider

# Patterns to strip from model responses before returning
_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_TRAILING_PROMPT_RE = re.compile(
    r"\n*(Would you like me to|Do you want me to|Let me know if you|Feel free to ask).*$",
    re.DOTALL | re.IGNORECASE,
)
_CHANNEL_ARTIFACT_RE = re.compile(
    r"<\|channel\>\s*[a-zA-Z_]+\s*<channel\|>|<\|channel\>|<channel\|>",
    re.IGNORECASE,
)


def _clean_response(text: str) -> str:
    """Remove model artifacts and trailing filler from a response."""
    # Strip <think>...</think> blocks (qwen3 thinking mode)
    text = _THINK_TAG_RE.sub("", text)
    # Strip leaked control-channel markers that some models occasionally emit.
    text = _CHANNEL_ARTIFACT_RE.sub("", text)
    # Strip trailing "Would you like me to..." filler
    text = _TRAILING_PROMPT_RE.sub("", text)
    return text.strip()


class OllamaProvider(LLMProvider):

    def __init__(self):
        base = (settings.OLLAMA_HOST or "http://localhost:11434").rstrip("/")
        parsed = urlparse(base)

        if parsed.path.endswith("/api/generate"):
            self.ollama_url = base
            self.base_url = f"{parsed.scheme}://{parsed.netloc}"
        else:
            self.base_url = base
            self.ollama_url = f"{base}/api/generate"

        self.completions_url = f"{self.base_url}/v1/completions"
        self.chat_completions_url = f"{self.base_url}/v1/chat/completions"

    def _try_ollama_generate(self, model: str, prompt: str) -> str:
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": settings.MAX_TOKENS,
                "temperature": settings.TEMPERATURE,
            },
        }

        response = requests.post(
            self.ollama_url,
            json=payload,
            timeout=300,
        )
        response.raise_for_status()
        data = response.json()
        return _clean_response(data.get("response", "No response from model."))

    def _try_openai_completions(self, model: str, prompt: str) -> str:
        payload = {
            "model": model,
            "prompt": prompt,
            "max_tokens": settings.MAX_TOKENS,
            "temperature": settings.TEMPERATURE,
        }
        response = requests.post(
            self.completions_url,
            json=payload,
            timeout=300,
        )
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            return "No response from model."
        raw = choices[0].get("text", "")
        return _clean_response(raw)

    def _try_openai_chat(self, model: str, prompt: str) -> str:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": settings.MAX_TOKENS,
            "temperature": settings.TEMPERATURE,
        }
        response = requests.post(
            self.chat_completions_url,
            json=payload,
            timeout=300,
        )
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            return "No response from model."
        msg = choices[0].get("message", {})
        raw = msg.get("content", "")
        return _clean_response(raw)

    def generate(
        self,
        model: str,
        prompt: str,
    ) -> str:

        logger.info(
            f"Ollama -> {model}"
        )

        try:
            return self._try_ollama_generate(model=model, prompt=prompt)

        except Exception as ollama_ex:
            logger.warning(f"Ollama-style generate failed, trying OpenAI-compatible endpoint: {ollama_ex}")

            try:
                return self._try_openai_completions(model=model, prompt=prompt)

            except Exception as completion_ex:
                logger.warning(f"OpenAI completions failed, trying chat completions: {completion_ex}")

                try:
                    return self._try_openai_chat(model=model, prompt=prompt)
                except Exception as chat_ex:
                    logger.error(f"LLM Error -> {chat_ex}")
                    return "Unable to communicate with the model server."
