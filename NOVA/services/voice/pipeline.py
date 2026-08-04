"""Modular voice pipeline orchestrator."""

from __future__ import annotations

import re
from typing import Any, Dict

from packages.common import logger
from packages.events import Event, bus

from .conversation_manager import VoiceConversationManager
from .device_manager import VoiceDeviceManager
from .emotion import EmotionDetector
from .language import LanguageDetector
from .models import VoiceInputFrame
from .speech_planner import SpeechPlanner
from .speaker import SpeakerRecognizer, SpeakerRegistry
from .state import VoiceSession, VoiceState
from .vad import VoiceActivityDetector


class VoicePipeline:
    def __init__(
        self,
        conversation_service,
        recognizer,
        synthesizer,
        wakeword,
        player,
        speaker_registry: SpeakerRegistry | None = None,
        vad: VoiceActivityDetector | None = None,
        language_detector: LanguageDetector | None = None,
        emotion_detector: EmotionDetector | None = None,
        conversation_manager: VoiceConversationManager | None = None,
        speech_planner: SpeechPlanner | None = None,
        device_manager: VoiceDeviceManager | None = None,
    ):
        self.conversation_service = conversation_service
        self.recognizer = recognizer
        self.synthesizer = synthesizer
        self.wakeword = wakeword
        self.player = player
        self.speaker_registry = speaker_registry or SpeakerRegistry()
        self.speaker_recognizer = SpeakerRecognizer(self.speaker_registry)
        self.vad = vad or VoiceActivityDetector()
        self.language_detector = language_detector or LanguageDetector()
        self.emotion_detector = emotion_detector or EmotionDetector()
        self.conversation_manager = conversation_manager or VoiceConversationManager()
        self.speech_planner = speech_planner or SpeechPlanner(
            default_rate=getattr(synthesizer, "rate", 180),
            default_pitch=getattr(synthesizer, "pitch", 50),
        )
        self.device_manager = device_manager or VoiceDeviceManager()

    def process(self, frame: VoiceInputFrame, session: VoiceSession) -> Dict[str, Any]:
        previous_state = session.state
        session.touch(VoiceState.LISTENING)
        bus.publish(Event.AVATAR_LISTENING_STARTED, {"source_type": frame.source_type})

        vad_result = self.vad.detect(frame.source)
        if not vad_result.speech_detected:
            bus.publish(Event.AVATAR_LISTENING_COMPLETED, {"reason": "no_speech"})
            session.touch(VoiceState.IDLE)
            bus.publish(Event.AVATAR_IDLE, {"reason": "no_speech"})
            session.metadata = {
                "vad": vad_result.__dict__,
                "devices": self.device_manager.status(),
            }
            return {
                "response": "",
                "action": "voice",
                "voice": session.to_dict(),
                "message": "No speech activity detected.",
            }

        recognition = self.recognizer.recognize(frame.source)
        transcript = recognition.text
        wake = self.wakeword.detect(transcript)

        if wake.detected:
            transcript = wake.text
            session.wake_word_detected = True
        elif frame.force_wake:
            session.wake_word_detected = True
        else:
            session.wake_word_detected = False

        if not session.wake_word_detected:
            transcript = transcript.strip()
            session.transcript = transcript
            bus.publish(Event.AVATAR_LISTENING_COMPLETED, {"reason": "wake_word_not_detected"})
            session.touch(VoiceState.IDLE)
            bus.publish(Event.AVATAR_IDLE, {"reason": "wake_word_not_detected"})
            session.metadata = {
                "vad": vad_result.__dict__,
                "recognition": {
                    "backend": recognition.backend,
                    "confidence": recognition.confidence,
                    "error": recognition.error,
                },
                "wake_word": {
                    "detected": wake.detected,
                    "keyword": getattr(self.wakeword, "wake_word", "nova"),
                },
                "devices": self.device_manager.status(),
            }
            return {
                "response": "",
                "action": "voice",
                "voice": session.to_dict(),
                "message": "Wake word not detected.",
            }

        transcript = transcript.strip()
        session.transcript = transcript
        if not transcript:
            bus.publish(Event.AVATAR_LISTENING_COMPLETED, {"reason": "empty_transcript"})
            session.touch(VoiceState.IDLE)
            bus.publish(Event.AVATAR_IDLE, {"reason": "empty_transcript"})
            return {
                "response": "",
                "action": "voice",
                "voice": session.to_dict(),
                "message": "No transcript detected.",
            }

        session.touch(VoiceState.RECOGNIZING)

        speaker = self.speaker_recognizer.recognize(transcript, frame.metadata)
        emotion = self.emotion_detector.detect(transcript)
        language = self.language_detector.detect(transcript)
        session.state = previous_state
        conversation = self.conversation_manager.begin_turn(session, speaker.speaker if speaker.recognized else None)
        bus.publish(Event.AVATAR_LISTENING_COMPLETED, {"transcript": transcript})
        session.touch(VoiceState.THINKING)
        bus.publish(Event.AVATAR_THINKING_STARTED, {"transcript": transcript})
        enrolled_profiles = self.speaker_registry.all_profiles()
        recognition_enabled = bool((frame.metadata or {}).get("recognition_enabled", True))
        logger.info(
            "VoicePipeline: speaker evaluation",
            recognition_enabled=recognition_enabled,
            enrolled_profiles=len(enrolled_profiles),
            audio_profiles=self.speaker_registry.has_audio_profiles(),
            speaker=speaker.speaker,
            speaker_recognized=speaker.recognized,
            speaker_confidence=float(speaker.confidence),
            speaker_backend=speaker.backend,
        )

        if recognition_enabled and enrolled_profiles and not speaker.recognized:
            if str(speaker.backend or "").lower() == "resemblyzer/insufficient-audio":
                response_text = (
                    "I could not capture a clear voice sample. "
                    "Please speak for a full second in a steady voice, closer to the microphone."
                )
                logger.warning(
                    "VoicePipeline: blocked request due to insufficient audio quality",
                    speaker_backend=speaker.backend,
                )
                bus.publish(Event.AVATAR_THINKING_COMPLETED, {"response_preview": response_text[:120]})
                session.response = response_text
                self.conversation_manager.end_turn(session)
                session.touch(VoiceState.IDLE)
                bus.publish(Event.AVATAR_IDLE, {"reason": "insufficient_audio_quality"})
                session.metadata = {
                    "vad": vad_result.__dict__,
                    "recognition": {
                        "backend": recognition.backend,
                        "confidence": recognition.confidence,
                        "error": recognition.error,
                    },
                    "wake_word": {
                        "detected": wake.detected,
                        "keyword": getattr(self.wakeword, "wake_word", "nova"),
                    },
                    "speaker": speaker.__dict__,
                    "emotion": emotion.__dict__,
                    "language": language.__dict__,
                    "conversation": conversation.__dict__,
                    "devices": self.device_manager.status(),
                }
                return {
                    "response": response_text,
                    "action": "voice_identity",
                    "intent": "voice_identity_insufficient_audio",
                    "voice": session.to_dict(),
                    "recognition_backend": recognition.backend,
                    "recognition_confidence": recognition.confidence,
                    "speaker": speaker.speaker,
                    "speaker_role": speaker.role,
                    "emotion": emotion.emotion,
                    "language": language.language,
                }

            if (
                "resemblyzer" in str(speaker.backend or "").lower()
                and not self.speaker_registry.has_audio_profiles()
            ):
                logger.warning(
                    "VoicePipeline: blocked request due to legacy non-audio voice profiles",
                    recognition_backend=recognition.backend,
                    speaker_backend=speaker.backend,
                    enrolled_profiles=len(enrolled_profiles),
                )
                response_text = (
                    "Your enrolled voice profiles were created before audio-based voice recognition was enabled. "
                    "Please re-enroll your voice to create a usable voiceprint."
                )
                bus.publish(Event.AVATAR_THINKING_COMPLETED, {"response_preview": response_text[:120]})
                session.response = response_text
                self.conversation_manager.end_turn(session)
                session.touch(VoiceState.IDLE)
                bus.publish(Event.AVATAR_IDLE, {"reason": "legacy_speaker_profiles"})
                session.metadata = {
                    "vad": vad_result.__dict__,
                    "recognition": {
                        "backend": recognition.backend,
                        "confidence": recognition.confidence,
                        "error": recognition.error,
                    },
                    "wake_word": {
                        "detected": wake.detected,
                        "keyword": getattr(self.wakeword, "wake_word", "nova"),
                    },
                    "speaker": speaker.__dict__,
                    "emotion": emotion.__dict__,
                    "language": language.__dict__,
                    "conversation": conversation.__dict__,
                    "devices": self.device_manager.status(),
                }
                return {
                    "response": response_text,
                    "action": "voice_identity",
                    "intent": "voice_identity_reenroll_required",
                    "voice": session.to_dict(),
                    "recognition_backend": recognition.backend,
                    "recognition_confidence": recognition.confidence,
                    "speaker": speaker.speaker,
                    "speaker_role": speaker.role,
                    "emotion": emotion.emotion,
                    "language": language.language,
                }
            logger.warning(
                "VoicePipeline: blocked request due to unrecognized speaker",
                recognition_backend=recognition.backend,
                speaker_backend=speaker.backend,
                speaker_confidence=float(speaker.confidence),
            )
            response_text = "Unrecognized voice. I can respond only to enrolled speakers while voice recognition is enabled."
            bus.publish(Event.AVATAR_THINKING_COMPLETED, {"response_preview": response_text[:120]})
            session.response = response_text
            self.conversation_manager.end_turn(session)
            session.touch(VoiceState.IDLE)
            bus.publish(Event.AVATAR_IDLE, {"reason": "unknown_speaker"})
            session.metadata = {
                "vad": vad_result.__dict__,
                "recognition": {
                    "backend": recognition.backend,
                    "confidence": recognition.confidence,
                    "error": recognition.error,
                },
                "wake_word": {
                    "detected": wake.detected,
                    "keyword": getattr(self.wakeword, "wake_word", "nova"),
                },
                "speaker": speaker.__dict__,
                "emotion": emotion.__dict__,
                "language": language.__dict__,
                "conversation": conversation.__dict__,
                "devices": self.device_manager.status(),
            }
            return {
                "response": response_text,
                "action": "voice_identity",
                "intent": "voice_identity_unrecognized",
                "voice": session.to_dict(),
                "recognition_backend": recognition.backend,
                "recognition_confidence": recognition.confidence,
                "speaker": speaker.speaker,
                "speaker_role": speaker.role,
                "emotion": emotion.emotion,
                "language": language.language,
            }

        if speaker.recognized and self._is_simple_greeting(transcript):
            result = {
                "response": f"Hi, {speaker.speaker}.",
                "action": "voice_identity",
                "intent": "voice_identity_greeting",
            }
        else:
            result = self.conversation_service.handle(transcript)

        response_text = self._extract_response(result)
        bus.publish(Event.AVATAR_THINKING_COMPLETED, {"response_preview": response_text[:120]})
        session.response = response_text

        plan = self.speech_planner.plan(response_text, emotion, language, speaker)
        preferences = frame.metadata.get("voice_preferences", {}) if isinstance(frame.metadata, dict) else {}
        preferred_style = str(preferences.get("style") or "").strip().lower()
        if preferred_style in {"natural", "warm", "clear", "excited", "calm"}:
            plan.style = preferred_style
        if preferences.get("rate") is not None:
            try:
                plan.rate = int(preferences.get("rate"))
            except (TypeError, ValueError):
                pass
        if preferences.get("pitch") is not None:
            try:
                plan.pitch = int(preferences.get("pitch"))
            except (TypeError, ValueError):
                pass
        preferred_voice = str(preferences.get("voice") or "").strip()
        preferred_mode = str(preferences.get("voice_mode") or "human").strip().lower()

        synthesis = None
        if frame.speak and response_text:
            session.touch(VoiceState.SPEAKING)
            bus.publish(
                Event.AVATAR_SPEAKING_STARTED,
                {
                    "text": plan.text,
                    "style": plan.style,
                    "rate": plan.rate,
                    "pitch": plan.pitch,
                    "voice_mode": preferred_mode,
                },
            )
            synthesis = self.synthesizer.speak(
                plan.text,
                play=True,
                style=plan.style,
                rate=plan.rate,
                pitch=plan.pitch,
                voice=preferred_voice or None,
                voice_mode=preferred_mode,
            )
            if getattr(synthesis, "backend", "") in {"text", "error"}:
                logger.info("VoicePipeline: TTS backend did not emit playable audio")
            bus.publish(
                Event.AVATAR_SPEAKING_COMPLETED,
                {
                    "backend": getattr(synthesis, "backend", ""),
                    "error": getattr(synthesis, "error", ""),
                },
            )

        self.conversation_manager.end_turn(session)
        session.touch(VoiceState.IDLE)
        bus.publish(Event.AVATAR_IDLE, {"reason": "turn_completed"})
        session.metadata = {
            "vad": vad_result.__dict__,
            "recognition": {
                "backend": recognition.backend,
                "confidence": recognition.confidence,
                "error": recognition.error,
            },
            "wake_word": {
                "detected": wake.detected,
                "keyword": getattr(self.wakeword, "wake_word", "nova"),
            },
            "speaker": speaker.__dict__,
            "emotion": emotion.__dict__,
            "language": language.__dict__,
            "conversation": conversation.__dict__,
            "speech_plan": plan.__dict__,
            "devices": self.device_manager.status(),
            "synthesis": getattr(synthesis, "__dict__", {}) if synthesis else {},
        }

        payload = self._normalize_result(result)
        payload.update(
            {
                "voice": session.to_dict(),
                "recognition_backend": recognition.backend,
                "recognition_confidence": recognition.confidence,
                "speaker": speaker.speaker,
                "speaker_role": speaker.role,
                "emotion": emotion.emotion,
                "language": language.language,
            }
        )
        return payload

    def _is_simple_greeting(self, transcript: str) -> bool:
        t = (transcript or "").strip().lower()
        return bool(re.fullmatch(r"(hi|hello|hey|good\s+morning|good\s+afternoon|good\s+evening)[\s!.?]*", t))

    def _extract_response(self, result: Any) -> str:
        if isinstance(result, dict):
            return str(result.get("response") or result.get("text") or "")
        if hasattr(result, "text"):
            return str(result.text)
        return str(result)

    def _normalize_result(self, result: Any) -> Dict[str, Any]:
        if isinstance(result, dict):
            return dict(result)
        if hasattr(result, "text"):
            return {"response": result.text, "action": "chat"}
        return {"response": str(result), "action": "chat"}