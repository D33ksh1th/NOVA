"""NOVA Skills — Command detection and execution.

Intercepts user transcripts that match known commands
before they hit the LLM. Provides structured progress feedback.
"""

import logging
import re
from typing import Callable, Optional

logger = logging.getLogger("nova.skills")

# Intent patterns — matched against STT transcript
SKILL_PATTERNS: dict[str, list[str]] = {}


class NovaSkills:
    """Skill router — detects commands and dispatches to handlers."""

    def __init__(self):
        self._handlers: dict[str, Callable] = {}
        self._compiled_patterns: dict[str, list[re.Pattern]] = {}

        # Compile patterns
        for skill_id, patterns in SKILL_PATTERNS.items():
            self._compiled_patterns[skill_id] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]

    def register(self, skill_id: str, handler: Callable):
        """Register a handler for a skill."""
        self._handlers[skill_id] = handler

    def match(self, transcript: str) -> Optional[str]:
        """Check if transcript matches any skill. Returns skill_id or None."""
        text = transcript.strip().lower()
        for skill_id, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                if pattern.search(text):
                    logger.info("nova-skills: matched %r -> %s", transcript[:40], skill_id)
                    return skill_id
        return None

    async def execute(self, skill_id: str, transcript: str) -> bool:
        """Execute a matched skill. Returns True if handled."""
        handler = self._handlers.get(skill_id)
        if handler is None:
            logger.warning("nova-skills: no handler for %s", skill_id)
            return False

        try:
            await handler(transcript)
            return True
        except Exception as e:
            logger.error("nova-skills: %s failed: %s", skill_id, e)
            return False
