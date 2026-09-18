"""Factory for pluggable voice components.

The current repo keeps dependency-light defaults, but the factory makes provider
selection explicit so Phase 2 can swap real backends in without changing the
VoiceEngine contract.
"""

from __future__ import annotations

from packages.config import settings

from .emotion import EmotionDetector, Wav2Vec2EmotionDetector
from .speaker import SpeakerRecognizer, SpeakerRegistry, EcapaSpeakerRecognizer
from .stt import SpeechRecognizer
from .tts import SpeechSynthesizer, KokoroSpeechSynthesizer, PiperSpeechSynthesizer
from .vad import VoiceActivityDetector, SileroVoiceActivityDetector
from .wakeword import WakeWordDetector, OpenWakeWordDetector


class VoiceComponentFactory:
    def create_recognizer(self) -> SpeechRecognizer:
        provider = settings.STT_PROVIDER.lower()
        whisper_binary = settings.WHISPER_CPP_BINARY if provider == "whisper.cpp" else None
        whisper_model = settings.WHISPER_CPP_MODEL if provider == "whisper.cpp" else None
        whisper_args = settings.WHISPER_CPP_ARGS if provider == "whisper.cpp" else None
        return SpeechRecognizer(
            language=settings.VOICE_LANGUAGE,
            whisper_binary=whisper_binary,
        )

    def create_synthesizer(self) -> SpeechSynthesizer:
        provider = settings.TTS_PROVIDER.lower()
        if provider == "kokoro":
            return KokoroSpeechSynthesizer(
                tts_command=settings.KOKORO_TTS_COMMAND,
                voice=settings.VOICE_NAME,
                rate=settings.VOICE_RATE,
                pitch=settings.VOICE_PITCH,
                kokoro_voice=settings.KOKORO_VOICE,
                kokoro_speed=settings.KOKORO_SPEED,
            )
        if provider == "piper":
            return PiperSpeechSynthesizer(
                tts_command=settings.PIPER_TTS_COMMAND,
                voice=settings.VOICE_NAME,
                rate=settings.VOICE_RATE,
                pitch=settings.VOICE_PITCH,
            )
        return SpeechSynthesizer(
            voice=settings.VOICE_NAME,
            rate=settings.VOICE_RATE,
            pitch=settings.VOICE_PITCH,
        )

    def create_wakeword(self) -> WakeWordDetector:
        if settings.WAKEWORD_PROVIDER.lower() == "openwakeword":
            return OpenWakeWordDetector(
                wake_word=settings.WAKE_WORD,
                model_path=settings.OPENWAKEWORD_MODEL_PATH,
                threshold=settings.OPENWAKEWORD_THRESHOLD,
                wakeword_name=settings.OPENWAKEWORD_WAKEWORD_NAME,
            )
        return WakeWordDetector(settings.WAKE_WORD)

    def create_vad(self) -> VoiceActivityDetector:
        if settings.VAD_PROVIDER.lower() == "silero-vad":
            return SileroVoiceActivityDetector(
                model_path=settings.SILERO_VAD_MODEL_PATH,
                threshold=settings.SILERO_VAD_THRESHOLD,
                min_speech_duration_ms=settings.SILERO_VAD_MIN_SPEECH_MS,
            )
        return VoiceActivityDetector()

    def provider_summary(self) -> dict[str, str]:
        return {
            "stt": settings.STT_PROVIDER,
            "vad": settings.VAD_PROVIDER,
            "tts": settings.TTS_PROVIDER,
            "wakeword": settings.WAKEWORD_PROVIDER,
            "speaker": settings.SPEAKER_PROVIDER,
            "emotion": settings.EMOTION_PROVIDER,
        }

    def create_speaker_recognizer(self, registry: SpeakerRegistry) -> SpeakerRecognizer:
        provider = settings.SPEAKER_PROVIDER.lower()
        if "resemblyzer" in provider or "speechbrain" in provider or "ecapa" in provider:
            return EcapaSpeakerRecognizer(
                registry=registry,
                threshold=settings.SPEAKER_SIMILARITY_THRESHOLD,
            )
        return SpeakerRecognizer(registry=registry)

    def create_emotion_detector(self) -> EmotionDetector:
        provider = settings.EMOTION_PROVIDER.lower()
        if "wav2vec2" in provider:
            return Wav2Vec2EmotionDetector(model_name=settings.EMOTION_MODEL_NAME)
        return EmotionDetector()