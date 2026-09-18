"""Module 5: nova-persona — LLM interface with JARVIS persona.

Handles the system prompt, JSON output parsing, pydantic validation,
and retry logic.
"""

import json
import logging
import subprocess
import time
from typing import Optional

from pydantic import BaseModel, field_validator

logger = logging.getLogger("nova.persona")

SYSTEM_PROMPT = """You are NOVA. Speak like a competent, unflappable chief of staff.
Rules: max 2 sentences unless asked to elaborate. Never open with
"Sure!", "Certainly", "I'd be happy to". Dry understatement over
enthusiasm. State facts, then the caveat, then stop. You may be
faintly amused but never cute.
Output STRICT JSON, no markdown fences:
{"say":[{"text":"one sentence","emotion":"neutral|warm|amused|urgent|serious|concerned|confident"}]}"""

VALID_EMOTIONS = {"neutral", "warm", "amused", "urgent", "serious", "concerned", "confident"}


class SayItem(BaseModel):
    text: str
    emotion: str = "neutral"

    @field_validator("emotion")
    @classmethod
    def validate_emotion(cls, v: str) -> str:
        if v not in VALID_EMOTIONS:
            return "neutral"
        return v


class NovaResponse(BaseModel):
    say: list[SayItem]


class NovaPersona:
    """LLM interface with persona enforcement and structured output."""

    def __init__(self, config: dict):
        self._cfg = config["brain"]
        self._url = self._cfg["url"]
        self._model = self._cfg["model"]
        self._timeout = self._cfg["timeout_s"]
        self._max_retries = self._cfg["max_retries"]

    def think(self, user_input: str, context: Optional[str] = None) -> list[dict]:
        """Send user input to LLM, return list of {text, emotion} dicts.

        Retries up to max_retries on parse failure.
        Falls back to plain text with emotion=neutral.
        """
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_input},
        ]

        if context:
            messages.insert(1, {"role": "system", "content": f"Context: {context}"})

        for attempt in range(1, self._max_retries + 2):
            t0 = time.time()
            raw = self._call_ollama(messages)
            elapsed_ms = (time.time() - t0) * 1000

            if not raw:
                logger.warning("nova-persona: empty response (attempt %d)", attempt)
                continue

            logger.debug("nova-persona: response in %.0fms: %s", elapsed_ms, raw[:100])

            # Try to parse structured JSON
            parsed = self._parse_response(raw)
            if parsed is not None:
                logger.info("nova-persona: %d sentences, %.0fms", len(parsed), elapsed_ms)
                return parsed

            logger.warning("nova-persona: parse failed (attempt %d), retrying", attempt)

        # Final fallback: treat raw as plain text
        logger.warning("nova-persona: all retries exhausted, using raw text")
        return [{"text": raw.strip()[:200], "emotion": "neutral"}]

    def _call_ollama(self, messages: list[dict]) -> str:
        """Call Ollama /api/chat via curl (avoids Node TLS issues)."""
        body = json.dumps({
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.4, "num_predict": 512},
        })

        try:
            result = subprocess.run(
                [
                    "curl", "-s", "-X", "POST",
                    f"{self._url}/api/chat",
                    "-H", "Content-Type: application/json",
                    "-d", body,
                    "--max-time", str(self._timeout),
                ],
                capture_output=True,
                text=True,
                timeout=self._timeout + 5,
            )

            if result.returncode != 0:
                logger.error("nova-persona: curl failed (rc=%d)", result.returncode)
                return ""

            data = json.loads(result.stdout)
            return data.get("message", {}).get("content", "")

        except subprocess.TimeoutExpired:
            logger.error("nova-persona: LLM timeout (%ds)", self._timeout)
            return ""
        except json.JSONDecodeError as e:
            logger.error("nova-persona: JSON decode error: %s", e)
            return ""

    def _parse_response(self, raw: str) -> Optional[list[dict]]:
        """Parse and validate LLM JSON response."""
        # Strip markdown fences if present
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            data = json.loads(text)
            response = NovaResponse(**data)
            return [{"text": item.text, "emotion": item.emotion} for item in response.say]
        except (json.JSONDecodeError, ValueError) as e:
            logger.debug("nova-persona: validation failed: %s", e)
            return None
