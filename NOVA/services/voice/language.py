"""Heuristic language detection for voice inputs."""

from __future__ import annotations

from .models import LanguageDetectionResult


class LanguageDetector:
    def detect(self, text: str) -> LanguageDetectionResult:
        normalized = (text or "").lower()
        if any(word in normalized for word in ["namaste", "kaise", "haan", "nahi"]):
            return LanguageDetectionResult(language="hi", confidence=0.8)
        if any(word in normalized for word in ["hola", "gracias", "adios"]):
            return LanguageDetectionResult(language="es", confidence=0.8)
        return LanguageDetectionResult(language="en", confidence=0.7)
