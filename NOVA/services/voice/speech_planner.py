"""Speech planning layer between Brain text and TTS synthesis.

This acts as NOVA's conversation director: it rewrites raw Brain output into
human-sounding speech chunks with timing, emphasis, and a voice profile that
the TTS layer can render consistently.
"""

from __future__ import annotations

import re

from .models import EmotionDetectionResult, LanguageDetectionResult, SpeechPlan, SpeakerRecognitionResult, VoiceProfile
from .speech_text import prepare_speech_text


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
        pause_ms = 120
        start_delay_ms = 0
        warmth = 0.5
        speed = 1.0
        voice_emotion = emotion.emotion

        if emotion.emotion == "excited":
            style = "excited"
            rate += 10
            pitch += 6
            speed = 1.08
            warmth = 0.72
            pause_ms = 100
        elif emotion.emotion == "calm":
            style = "calm"
            rate -= 8
            pitch -= 4
            speed = 0.94
            warmth = 0.8
            pause_ms = 150
        elif emotion.emotion == "stressed":
            style = "steady"
            rate -= 4
            speed = 0.90
            warmth = 0.62
            pause_ms = 150
        elif emotion.emotion == "happy":
            style = "warm"
            speed = 1.04
            warmth = 0.82
            pause_ms = 100
        elif emotion.emotion == "concerned":
            style = "steady"
            speed = 0.92
            warmth = 0.64
            pause_ms = 140

        if language.language != "en":
            rate = max(150, rate - 5)

        if speaker.recognized:
            style = style if style != "natural" else "personal"
            warmth += 0.08

        chunks = self._chunk_text(cleaned)
        pauses = ["sentence"] if len(chunks) > 1 else (["sentence"] if "." in cleaned else [])
        emphasis = [emotion.emotion] if emotion.emotion != "neutral" else []
        voice_profile = VoiceProfile(
            speed=round(speed, 2),
            pitch=round((pitch - self.default_pitch) / 100.0, 2),
            warmth=round(min(1.0, max(0.0, warmth)), 2),
            pause_strength=round(min(1.0, max(0.0, pause_ms / 300.0)), 2),
            emotion=voice_emotion,
            voice=("personal" if speaker.recognized else "nova"),
        )
        return SpeechPlan(
            text=cleaned,
            style=style,
            rate=rate,
            pitch=pitch,
            pauses=pauses,
            emphasis=emphasis,
            chunks=chunks,
            start_delay_ms=start_delay_ms,
            pause_ms=pause_ms,
            voice_profile=voice_profile.__dict__,
        )

    def _normalize_text(self, text: str) -> str:
        return prepare_speech_text(text)

    def _chunk_text(self, text: str) -> list[str]:
        """Split text into chunks suitable for TTS.

        Keeps sentences together when they're short enough for natural
        synthesis (~200 chars). Only splits when a chunk would exceed
        the comfort limit, so Kokoro produces smooth, continuous audio
        instead of choppy per-sentence fragments.
        """
        normalized = (text or "").strip()
        if not normalized:
            return []

        # Split on sentence boundaries first
        parts = re.split(r"(?<=[.!?])\s+", normalized)
        sentences = [p.strip() for p in parts if p.strip()]

        if not sentences:
            return [normalized]

        # Merge short sentences into longer chunks for smoother synthesis
        CHUNK_LIMIT = 200
        chunks: list[str] = []
        current = ""

        for sentence in sentences:
            if not current:
                current = sentence
            elif len(current) + 1 + len(sentence) <= CHUNK_LIMIT:
                current = current + " " + sentence
            else:
                chunks.append(current)
                current = sentence

        if current:
            chunks.append(current)

        # If any chunk is still too long, split on clause boundaries
        final: list[str] = []
        for chunk in chunks:
            if len(chunk) <= CHUNK_LIMIT + 50:
                final.append(chunk)
            else:
                subparts = re.split(r"(?<=[,;:])\s+", chunk)
                current_sub = ""
                for sub in subparts:
                    sub = sub.strip()
                    if not sub:
                        continue
                    if not current_sub:
                        current_sub = sub
                    elif len(current_sub) + 2 + len(sub) <= CHUNK_LIMIT:
                        current_sub = current_sub + " " + sub
                    else:
                        final.append(current_sub)
                        current_sub = sub
                if current_sub:
                    final.append(current_sub)

        return final or [normalized]
