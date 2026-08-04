"""
Legacy voice facade.

This keeps a simple compatibility surface while the new
voice package evolves around VoiceEngine.
"""

from __future__ import annotations

from typing import Optional, Any, Dict

from packages.common import logger


class Voice:
    def __init__(self, engine=None):
        self.engine = engine

    def listen(self, text: str, speak: bool = True) -> Dict[str, Any]:
        if self.engine is None:
            logger.warning("Voice facade called without an engine")
            return {"response": "", "state": "idle", "enabled": False}
        return self.engine.listen(text, speak=speak)

    def speak(self, text: str):
        if self.engine is None:
            logger.warning("Voice facade called without an engine")
            return {"response": text, "spoken": False}
        return self.engine.synthesizer.speak(text, play=True)