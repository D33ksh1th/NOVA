"""Speech planning layer between Brain text and TTS synthesis."""

from __future__ import annotations

from .models import EmotionDetectionResult, LanguageDetectionResult, SpeechPlan, SpeakerRecognitionResult


class SpeechPlanner:
    def __init__(self, default_rate: int = 180, default_pitch: int = 50):
        self.default_rate = default_rate
        self.default_pitch = default_pitch

    def plan(
        self,
        text: str,
        emotion: EmotionDetectionResult,
        language: LanguageDetectionResult,
        speaker: SpeakerRecognitionResult,
    ) -> SpeechPlan:
        cleaned = self._normalize_text(text)
        style = "natural"
        rate = self.default_rate
        pitch = self.default_pitch

        if emotion.emotion == "excited":
            style = "excited"
            rate += 10
            pitch += 6
        elif emotion.emotion == "calm":
            style = "calm"
            rate -= 8
            pitch -= 4
        elif emotion.emotion == "stressed":
            style = "steady"
            rate -= 4

        if language.language != "en":
            rate = max(150, rate - 5)

        if speaker.recognized:
            style = style if style != "natural" else "personal"

        pauses = ["sentence"] if "." in cleaned else []
        emphasis = [emotion.emotion] if emotion.emotion != "neutral" else []
        return SpeechPlan(
            text=cleaned,
            style=style,
            rate=rate,
            pitch=pitch,
            pauses=pauses,
            emphasis=emphasis,
        )

    def _normalize_text(self, text: str) -> str:
        cleaned = (text or "").strip()
        cleaned = cleaned.replace(" - ", ". ")
        return " ".join(cleaned.split())
