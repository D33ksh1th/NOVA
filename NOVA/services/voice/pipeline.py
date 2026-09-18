"""Modular voice pipeline orchestrator."""

from __future__ import annotations

import re
import time
from typing import Any, Dict

from packages.common import logger
from packages.events import Event, bus

from .conversation_manager import VoiceConversationManager
from .device_manager import VoiceDeviceManager
from .earcon import ThinkingEarconTimer
from .emotion import EmotionDetector
from .language import LanguageDetector
from .models import VoiceInputFrame
from .speech_planner import SpeechPlanner
from .speaker import SpeakerRecognizer, SpeakerRegistry
from .state import VoiceSession, VoiceState
from .vad import VoiceActivityDetector


import time as _time

def _admin_greeting() -> str:
    """Contextual greeting based on persona and time of day."""
    hour = int(_time.strftime("%H"))
    persona = _get_persona()
    addr = "sir" if persona == "jarvis" else "boss"

    if hour < 6:
        return f"Burning the midnight oil, {addr}? What do you need?"
    if hour < 12:
        return f"Good morning, {addr}. All systems operational."
    if hour < 17:
        return f"Good afternoon, {addr}. At your service."
    if hour < 21:
        return f"Good evening, {addr}. How may I assist?"
    return f"Evening, {addr}. What can I do for you?"


def _get_persona() -> str:
    try:
        from services.voice.tts import KokoroSpeechSynthesizer
        return getattr(KokoroSpeechSynthesizer, '_active_persona', 'jarvis')
    except Exception:
        return "jarvis"


def _admin_prefix() -> str:
    persona = _get_persona()
    return {"jarvis": "Sir, ", "friday": "Boss, ", "devi": "Sir, "}.get(persona, "Sir, ")


ADMIN_FIRST_RESPONSE_GREETING = "Hey boss, good to hear you."


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
        self._thinking_earcon = ThinkingEarconTimer()

    def process(self, frame: VoiceInputFrame, session: VoiceSession) -> Dict[str, Any]:
        # Suppress mic input while Nova is speaking (prevents self-listening loop)
        _speaking = session.state == VoiceState.SPEAKING
        if not _speaking:
            try:
                _speaking = bool(self.synthesizer.is_speaking)
            except Exception:
                pass
        if _speaking:
            logger.info("VoicePipeline: suppressed input — Nova is currently speaking")
            return {
                "response": "",
                "action": "voice",
                "voice": session.to_dict(),
                "message": "Suppressed: Nova is speaking.",
            }

        existing_metadata = session.metadata if isinstance(session.metadata, dict) else {}
        admin_first_response_completed = bool(existing_metadata.get("admin_first_response_completed", False))
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
        self._thinking_earcon.start()
        enrolled_profiles = self.speaker_registry.all_profiles()
        recognition_enabled = bool((frame.metadata or {}).get("recognition_enabled", True))
        # Master gate toggle from settings
        from packages.config import settings
        if not settings.VOICE_RECOGNITION_GATE:
            recognition_enabled = False
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
            # Only gate on speaker identity when audio was provided.
            # Text-only input has no voiceprint to verify — let it through.
            has_audio = bool((frame.metadata or {}).get("audio_path", ""))
            if not has_audio:
                logger.info(
                    "VoicePipeline: text-only input, skipping speaker gate",
                    speaker_backend=speaker.backend,
                )
            elif "insufficient-audio" in str(speaker.backend or "").lower():
                response_text = (
                    "I could not capture a clear voice sample. "
                    "Please speak for a full second in a steady voice, closer to the microphone."
                )
                logger.warning(
                    "VoicePipeline: blocked request due to insufficient audio quality",
                    speaker_backend=speaker.backend,
                )
                self._thinking_earcon.cancel()
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
                has_audio
                and "resemblyzer" in str(speaker.backend or "").lower()
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
                self._thinking_earcon.cancel()
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
            if has_audio:
                logger.warning(
                    "VoicePipeline: unrecognized speaker — processing as guest",
                    recognition_backend=recognition.backend,
                    speaker_backend=speaker.backend,
                    speaker_confidence=float(speaker.confidence),
                )

        # When recognition gate is off and admin exists, assume admin identity
        is_admin = speaker.recognized and speaker.role == "admin"
        is_known = speaker.recognized
        if not recognition_enabled and not speaker.recognized:
            admin_profile = self.speaker_registry.get_admin()
            if admin_profile:
                is_admin = True
                is_known = True
                speaker = type(speaker)(
                    speaker=admin_profile.name,
                    role="admin",
                    confidence=1.0,
                    recognized=True,
                    backend="gate-bypassed",
                )

        if is_admin and self._is_simple_greeting(transcript):
            greeting_text = _admin_greeting() if not admin_first_response_completed else "I'm here, boss."
            result = {
                "response": greeting_text,
                "action": "voice_identity",
                "intent": "voice_identity_admin_greeting",
            }
        elif is_known and self._is_simple_greeting(transcript):
            result = {
                "response": f"Hi, {speaker.speaker}.",
                "action": "voice_identity",
                "intent": "voice_identity_greeting",
            }
        else:
            result = self.conversation_service.handle(transcript)

        response_text = self._extract_response(result)
        if is_admin and response_text:
            response_text = self._with_admin_intro(
                response_text,
                first_response=not admin_first_response_completed,
            )
            admin_first_response_completed = True
            if isinstance(result, dict):
                result = dict(result)
                result["response"] = response_text
        self._thinking_earcon.cancel()
        bus.publish(Event.AVATAR_THINKING_COMPLETED, {"response_preview": response_text[:120]})
        session.response = response_text

        # Dual-channel: short spoken version, full display version
        spoken_text, display_text = self._brevity_split(response_text)

        plan = self.speech_planner.plan(spoken_text, emotion, language, speaker)
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
        preferred_voice = str(preferences.get("accent_profile") or preferences.get("voice") or "").strip()
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
            chunks = plan.chunks if getattr(plan, "chunks", None) else [plan.text]
            _synth = self.synthesizer
            _plan = plan
            _pv = preferred_voice
            _pm = preferred_mode

            _session = session

            import threading

            def _speak():
                try:
                    synthesis = _synth.speak_sequence(
                        chunks,
                        play=True,
                        style=_plan.style,
                        rate=_plan.rate,
                        pitch=_plan.pitch,
                        voice=_pv or None,
                        voice_mode=_pm,
                        pause_ms=int(getattr(_plan, "pause_ms", 120)),
                        start_delay_ms=0,
                    )
                    if getattr(synthesis, "backend", "") in {"text", "error"}:
                        logger.info("VoicePipeline: TTS backend did not emit playable audio")
                    bus.publish(
                        Event.AVATAR_SPEAKING_COMPLETED,
                        {"backend": getattr(synthesis, "backend", "")},
                    )
                except Exception as ex:
                    logger.error(f"VoicePipeline: background speech error: {ex}")
                    bus.publish(Event.AVATAR_SPEAKING_COMPLETED, {"error": str(ex)})
                finally:
                    _session.touch(VoiceState.IDLE)
                    bus.publish(Event.AVATAR_IDLE, {"reason": "speech_completed"})

            threading.Thread(target=_speak, daemon=True, name="nova-pipeline-speak").start()

        self.conversation_manager.end_turn(session)
        if not (frame.speak and response_text):
            session.touch(VoiceState.IDLE)
            bus.publish(Event.AVATAR_IDLE, {"reason": "turn_completed"})
        session.metadata = {
            "admin_first_response_completed": admin_first_response_completed,
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

    @staticmethod
    def _brevity_split(text: str) -> tuple[str, str | None]:
        """Split into (spoken, display). Spoken ≤ 2 sentences. Display = full if longer."""
        import re as _re
        sentences = _re.split(r'(?<=[.!?])\s+', text.strip())
        if len(sentences) <= 2:
            return text.strip(), None
        spoken = " ".join(sentences[:2])
        return spoken, text.strip()

    def _normalize_result(self, result: Any) -> Dict[str, Any]:
        if isinstance(result, dict):
            return dict(result)
        if hasattr(result, "text"):
            return {"response": result.text, "action": "chat"}
        return {"response": str(result), "action": "chat"}

    def _with_admin_intro(self, response_text: str, first_response: bool) -> str:
        return (response_text or "").strip()