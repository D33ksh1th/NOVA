"""Async adapter for a trusted local Ollama server, without fallback or retries.

The operator must qualify the tokenizer/chat template against the installed
model. Raw mode bypasses Ollama's template. Count mismatches fail closed, but
cannot undo inference already performed by a misconfigured server. USD records
represent local provider charges (zero), not hardware or electricity costs.
Closing a request cancels client I/O, not a hard guarantee of server termination.
"""

from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path
from typing import Protocol

import httpx

from services.agent_runtime.contracts.model_usage import (
    BudgetExceededError, MeteredCompletion, ModelResponseError,
)


class PromptTokenizer(Protocol):
    def apply_chat_template(self, conversation: list[dict[str, str]], *, tokenize: bool,
                            add_generation_prompt: bool, enable_thinking: bool) -> str: ...

    def encode(self, text: str, *, add_special_tokens: bool) -> list[int]: ...


def load_local_tokenizer(path: str | Path) -> PromptTokenizer:
    """Load operator-installed tokenizer files; never download or execute remote code."""
    from transformers import AutoTokenizer

    directory = Path(path).resolve(strict=True)
    if not directory.is_dir():
        raise ValueError("TOKENIZER_DIRECTORY_REQUIRED")
    return AutoTokenizer.from_pretrained(str(directory), local_files_only=True, trust_remote_code=False)


def _json_object(text: str) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("non-finite JSON")

    result = json.loads(text, object_pairs_hook=unique, parse_constant=invalid_constant)
    if not isinstance(result, dict):
        raise ValueError("object required")
    return result


class OllamaRuntimeModel:
    def __init__(self, *, model: str, tokenizer: PromptTokenizer,
                 base_url: str = "http://127.0.0.1:11434", context_tokens: int = 8192,
                 output_tokens: int = 2048, timeout_seconds: float = 60,
                 transport: httpx.AsyncBaseTransport | None = None,
                 response_schema: dict | None = None) -> None:
        endpoint = httpx.URL(base_url)
        if (endpoint.scheme != "http" or endpoint.host not in {"127.0.0.1", "::1"}
                or endpoint.userinfo or endpoint.path not in {"", "/"}
                or endpoint.query or endpoint.fragment):
            raise ValueError("LOCAL_MODEL_ENDPOINT_REQUIRED")
        if not model or model.endswith(":cloud"):
            raise ValueError("LOCAL_MODEL_REQUIRED")
        if (type(context_tokens) is not int or context_tokens <= 0
                or type(output_tokens) is not int or output_tokens <= 0
                or not math.isfinite(timeout_seconds) or timeout_seconds <= 0):
            raise ValueError("INVALID_MODEL_LIMITS")
        self.model = model
        self.tokenizer = tokenizer
        self.context_tokens = context_tokens
        self.output_tokens = output_tokens
        self.timeout_seconds = timeout_seconds
        self.response_schema = response_schema
        self._closed = False
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds,
                                        follow_redirects=False, trust_env=False, transport=transport)

    async def complete_metered(self, *, system: str, content: str,
                               max_tokens: int, max_usd: float) -> MeteredCompletion:
        if self._closed:
            raise RuntimeError("MODEL_CLOSED")
        if (type(max_tokens) is not int or max_tokens <= 0
                or not math.isfinite(max_usd) or max_usd < 0):
            raise BudgetExceededError("MODEL_BUDGET_EXCEEDED")
        if len(system.encode("utf-8")) + len(content.encode("utf-8")) > 131072:
            raise BudgetExceededError("MODEL_PROMPT_SIZE_EXCEEDED")
        prompt = self.tokenizer.apply_chat_template(
            [{"role": "system", "content": system}, {"role": "user", "content": content}],
            tokenize=False, add_generation_prompt=True, enable_thinking=False,
        )
        prompt_tokens = len(self.tokenizer.encode(prompt, add_special_tokens=True))
        remaining = min(max_tokens, self.context_tokens) - prompt_tokens
        if prompt_tokens <= 0 or remaining <= 0:
            raise BudgetExceededError("MODEL_BUDGET_EXCEEDED")
        output_limit = min(remaining, self.output_tokens)
        payload = {"model": self.model, "prompt": prompt, "raw": True,
               "format": self.response_schema if self.response_schema is not None else "json", "stream": False,
               "think": False,
                   "options": {"num_predict": output_limit, "num_ctx": self.context_tokens, "temperature": 0}}
        try:
            async with asyncio.timeout(self.timeout_seconds):
                async with self._client.stream("POST", "/api/generate", json=payload) as response:
                    response.raise_for_status()
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > 1048576:
                            raise ModelResponseError("MODEL_RESPONSE_TOO_LARGE")
            raw = _json_object(body.decode("utf-8"))
        except (httpx.TimeoutException, TimeoutError):
            raise ModelResponseError("MODEL_TIMEOUT") from None
        except httpx.HTTPStatusError as error:
            raise ModelResponseError(f"MODEL_HTTP_{error.response.status_code}") from None
        except (httpx.HTTPError, ValueError, UnicodeError):
            raise ModelResponseError("MODEL_TRANSPORT_OR_RESPONSE_INVALID") from None
        if "error" in raw:
            raise ModelResponseError("MODEL_PROVIDER_ERROR")
        counts = (raw.get("prompt_eval_count"), raw.get("eval_count"))
        if any(type(count) is not int or count < 0 for count in counts):
            raise ModelResponseError("MODEL_USAGE_UNAVAILABLE")
        actual_prompt, actual_output = counts
        tokens = actual_prompt + actual_output
        if actual_prompt != prompt_tokens or actual_output > output_limit:
            raise ModelResponseError("MODEL_TOKEN_CONTRACT_VIOLATION", tokens=tokens)
        if raw.get("done") is not True or raw.get("done_reason") != "stop" or "error" in raw:
            raise ModelResponseError("MODEL_INCOMPLETE", tokens=tokens)
        try:
            result = _json_object(raw["response"])
        except (KeyError, ValueError, TypeError):
            raise ModelResponseError("MODEL_JSON_INVALID", tokens=tokens) from None
        return MeteredCompletion(content=result, tokens=tokens, usd=0)

    async def close(self) -> None:
        self._closed = True
        await self._client.aclose()

    async def __aenter__(self) -> OllamaRuntimeModel:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()