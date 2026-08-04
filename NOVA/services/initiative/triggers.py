"""
Initiative triggers.

These are lightweight detectors that turn conversation state into
potential proactive opportunities.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable, List


_TOPIC_PATTERNS = [
    (r"\bollama\b|\bmodel\b|\bllm\b|\bgemma\b|\bqwen\b", "Ollama / model setup"),
    (r"\bmemory\b|\bremember\b|\brecall\b", "memory system"),
    (r"\bbrainengine\b|\bbrain engine\b|\brain\b", "BrainEngine"),
    (r"\bcontext\b", "context engine"),
    (r"\bplanner\b|\bplanning\b|\btask\b", "task planning"),
    (r"\bweather\b", "weather feature"),
    (r"\blocation\b|\blocation tool\b|\bwhere am i\b", "location feature"),
    (r"\bdebug\b|\berror\b|\bissue\b|\bfail\b", "debugging"),
    (r"\bregistry\b", "service registry"),
    (r"\bskill\b", "skill system"),
    (r"\bvoice\b", "voice feature"),
    (r"\bvision\b", "vision feature"),
]


class InitiativeTriggers:
    """Context analyzers used by the initiative engine."""

    def extract_topic(self, message: str, response: dict | None = None) -> str:
        text = f"{message} {response.get('response', '') if isinstance(response, dict) else ''}".lower()

        for pattern, label in _TOPIC_PATTERNS:
            if re.search(pattern, text):
                return label

        # Fallback: use the first meaningful phrase from the message.
        words = [w for w in re.findall(r"[a-zA-Z][a-zA-Z0-9_\-]+", message) if len(w) > 2]
        if not words:
            return ""
        return " ".join(words[:5])

    def count_topic_repetition(self, history: Iterable[dict], topic: str) -> int:
        if not topic:
            return 0
        topic = topic.lower().strip()
        count = 0
        for turn in history:
            content = str(turn.get("content", turn.get("message", ""))).lower()
            if topic in content:
                count += 1
        return count

    def count_debug_intensity(self, history: Iterable[dict]) -> int:
        texts: List[str] = []
        for turn in history:
            texts.append(str(turn.get("content", turn.get("message", ""))).lower())
        joined = " \n ".join(texts)
        debug_words = ["debug", "error", "traceback", "fix", "issue", "broken", "not working", "exception"]
        return sum(1 for word in debug_words if word in joined)

    def is_pause_request(self, message: str) -> bool:
        text = message.lower()
        phrases = ["stop for today", "let's stop", "pause here", "continue tomorrow", "later", "tomorrow"]
        return any(phrase in text for phrase in phrases)

    def is_resume_request(self, message: str) -> bool:
        text = message.lower()
        phrases = ["continue", "resume", "pick up where we left off", "keep going", "where were we"]
        return any(phrase in text for phrase in phrases)

    def is_greeting(self, message: str) -> bool:
        text = message.lower().strip()
        return text in {"hi", "hello", "hey", "good morning", "good afternoon", "good evening"} or text.startswith(("good morning", "good afternoon", "good evening"))
