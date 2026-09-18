"""
Speech-to-text adapters.

This implementation is offline-first and dependency-light.
If a proper local backend is configured later, it can be wired in
without changing the public API.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from packages.common import logger


@dataclass
class SpeechRecognitionResult:
    text: str
    backend: str = "text"
    confidence: float = 1.0
    error: str = ""


class SpeechRecognizer:
    def __init__(self, language: str = "en", whisper_binary: Optional[str] = None):
        self.language = language
        self.whisper_binary = whisper_binary

    def recognize(self, source: Optional[str] = None) -> SpeechRecognitionResult:
        """
        Recognize speech from a transcript string or an audio file path.

        If `source` is already text, it is normalized and returned.
        If `source` points to an audio file and a whisper binary is configured,
        the recognizer will try to call it.
        """
        if source is None:
            return SpeechRecognitionResult(text="", backend="none", confidence=0.0)

        if isinstance(source, str) and Path(source).exists():
            return self._recognize_audio_file(Path(source))

        text = self._normalize_text(str(source))
        return SpeechRecognitionResult(text=text, backend="text", confidence=1.0)

    def _recognize_audio_file(self, path: Path) -> SpeechRecognitionResult:
        if not self.whisper_binary:
            logger.warning("SpeechRecognizer: audio file provided but no whisper binary configured")
            return SpeechRecognitionResult(text="", backend="audio", confidence=0.0, error="No STT backend configured")

        try:
            completed = subprocess.run(
                [self.whisper_binary, str(path), "--language", self.language],
                capture_output=True,
                text=True,
                check=True,
            )
            text = self._normalize_text(completed.stdout)
            return SpeechRecognitionResult(text=text, backend="whisper.cpp", confidence=0.9)
        except Exception as ex:
            logger.error(f"SpeechRecognizer error -> {ex}")
            return SpeechRecognitionResult(text="", backend="whisper.cpp", confidence=0.0, error=str(ex))

    def _normalize_text(self, text: str) -> str:
        return " ".join((text or "").split()).strip()
