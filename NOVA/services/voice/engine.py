"""
Voice Engine

Orchestrates wake word detection, transcript normalization,
conversation handling, and speech synthesis.
"""

from __future__ import annotations

import copy
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional, Any, Dict

from packages.common import logger
from packages.config import settings
from packages.events import bus, Event

from .factory import VoiceComponentFactory
from .speaker import assess_audio_sample
from .state import VoiceSession, VoiceState
from .pipeline import VoicePipeline
from .models import VoiceInputFrame
from .stt import SpeechRecognizer
from .tts import SpeechSynthesizer
from .player import VoicePlayer
from .wakeword import WakeWordDetector


class VoiceEngine:
    def __init__(
        self,
        conversation_service,
        recognizer: Optional[SpeechRecognizer] = None,
        synthesizer: Optional[SpeechSynthesizer] = None,
        player: Optional[VoicePlayer] = None,
        wakeword: Optional[WakeWordDetector] = None,
        enabled: Optional[bool] = None,
        component_factory: Optional[VoiceComponentFactory] = None,
    ):
        self.conversation_service = conversation_service
        self.component_factory = component_factory or VoiceComponentFactory()
        self.recognizer = recognizer or self.component_factory.create_recognizer()
        self.synthesizer = synthesizer or self.component_factory.create_synthesizer()
        self.player = player or VoicePlayer()
        self.wakeword = wakeword or self.component_factory.create_wakeword()
        self.enabled = settings.ENABLE_VOICE if enabled is None else enabled
        self.session = VoiceSession()
        default_voice_key = "english_lessac" if settings.TTS_PROVIDER.lower() == "piper" else str(getattr(settings, "VOICE_NAME", "") or "").strip()
        self._accent_profiles = {
            "english_clear": {"style": "clear", "rate": 178, "pitch": 50},
            "english_jarvis": {"style": "calm", "rate": 166, "pitch": 44},
            "english_friday": {"style": "warm", "rate": 178, "pitch": 50},
        }
        self._voice_model_presets = {
            "english_lessac": {"style": "calm", "rate": 170, "pitch": 46},
            "english_ryan": {"style": "clear", "rate": 176, "pitch": 42},
            "english_amy": {"style": "warm", "rate": 172, "pitch": 54},
            "ultron": {"style": "clear", "rate": 184, "pitch": 36, "voice": "english_lessac"},
            "nova": {"style": "natural", "rate": 174, "pitch": 46, "voice": "english_lessac"},
            "atlas": {"style": "calm", "rate": 168, "pitch": 42, "voice": "english_ryan"},
            "echo": {"style": "warm", "rate": 170, "pitch": 54, "voice": "english_amy"},
        }
        self._voice_mode_defaults = {
            "human": {"style": "calm", "rate": 170, "pitch": 46},
            "cat": {"style": "excited", "rate": 188, "pitch": 60},
        }
        self._voice_preferences = {
            "accent_profile": "english_jarvis",
            "voice_mode": "human",
            "style": "calm",
            "rate": 176,
            "pitch": 44,
            "voice": default_voice_key,
        }
        _speaker_registry = self.pipeline.speaker_registry if hasattr(self, "pipeline") else None
        from .speaker import SpeakerRegistry
        _registry = _speaker_registry or SpeakerRegistry()
        _speaker_recognizer = self.component_factory.create_speaker_recognizer(_registry)
        _emotion_detector = self.component_factory.create_emotion_detector()
        self.pipeline = VoicePipeline(
            conversation_service=self.conversation_service,
            recognizer=self.recognizer,
            synthesizer=self.synthesizer,
            wakeword=self.wakeword,
            player=self.player,
            vad=self.component_factory.create_vad(),
            speaker_registry=_registry,
            emotion_detector=_emotion_detector,
        )
        # Override the pipeline's default heuristic speaker recognizer with the
        # provider-backed one so real Resemblyzer embeddings are used when available.
        self.pipeline.speaker_recognizer = _speaker_recognizer
        self.recognition_enabled: bool = True  # Toggleable via settings/API
        self._enrollment_sessions: Dict[str, Dict[str, Any]] = {}
        self._active_enrollment_session_id: Optional[str] = None
        self._enrollment_prompts = [
            "Type or say: My voice is clear and steady.",
            "Type or say: Nova, please recognize my profile.",
            "Type or say: Security and privacy matter to me.",
            "Type or say: I am ready to use voice commands.",
            "Type or say: The quick brown fox jumps over the lazy dog.",
            "Type or say: Today is a good day to build something great.",
        ]
        logger.info("Voice Engine Initialized")

    def _persist_enrollment_audio(self, audio_path: Optional[str], session_id: str) -> Optional[str]:
        if not audio_path:
            logger.info("VoiceEngine: no audio_path provided for enrollment sample", session_id=session_id)
            return None
        source = Path(audio_path)
        if not source.exists():
            logger.warning("VoiceEngine: enrollment source audio does not exist", session_id=session_id, source_path=audio_path)
            return None
        target_dir = Path(tempfile.gettempdir()) / "nova_voice_enrollment" / session_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"sample-{uuid.uuid4()}{source.suffix or '.wav'}"
        shutil.copy2(source, target_path)
        logger.info(
            "VoiceEngine: persisted enrollment audio sample",
            session_id=session_id,
            source_path=str(source),
            target_path=str(target_path),
            size_bytes=source.stat().st_size,
        )
        return str(target_path)

    def _cleanup_enrollment_audio(self, session: Optional[Dict[str, Any]]) -> None:
        if not session:
            return
        removed = 0
        for path in session.get("audio_samples", []) or []:
            try:
                if path and os.path.exists(path):
                    os.remove(path)
                    removed += 1
            except OSError:
                pass
        if session.get("id"):
            target_dir = Path(tempfile.gettempdir()) / "nova_voice_enrollment" / str(session["id"])
            try:
                if target_dir.exists():
                    shutil.rmtree(target_dir, ignore_errors=True)
            except OSError:
                pass
        logger.info(
            "VoiceEngine: cleaned enrollment audio samples",
            session_id=str(session.get("id") or ""),
            removed_files=removed,
        )

    def has_active_enrollment_session(self) -> bool:
        sid = self._active_enrollment_session_id
        return bool(sid and sid in self._enrollment_sessions and not self._enrollment_sessions[sid].get("completed"))

    def is_enrollment_trigger(self, text: str) -> bool:
        normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
        triggers = [
            "recognize voice",
            "recognize my voice",
            "enroll voice",
            "enroll my voice",
            "register voice",
            "register my voice",
            "train voice",
            "train my voice",
            "voice enrollment",
        ]
        return any(t in normalized for t in triggers)

    def _is_quick_enroll(self, text: str) -> bool:
        normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
        return "quick enroll" in normalized or "enroll me" in normalized

    def quick_enroll(self, text: str) -> Dict[str, Any]:
        """One-step enrollment: 'enroll me as Deekshith' → immediately enrolled as admin."""
        name = self._extract_name_candidate(text)
        if not name:
            parts = re.sub(r"\s+", " ", text.strip()).split()
            # Try to get name from "enroll me as NAME" or "quick enroll NAME"
            for keyword in ["as", "enroll"]:
                if keyword in [p.lower() for p in parts]:
                    idx = [p.lower() for p in parts].index(keyword)
                    remaining = parts[idx + 1:]
                    remaining = [w for w in remaining if w.lower() not in {"me", "my", "voice", "as", "quick"}]
                    if remaining:
                        name = " ".join(w.capitalize() for w in remaining)
                        break
        if not name:
            return {
                "action": "voice_enrollment",
                "response": "Say 'enroll me as [your name]' to quick-enroll. Example: enroll me as Deekshith.",
                "data": {"completed": False},
            }

        profile = self.pipeline.speaker_registry.enroll(
            name,
            [f"quick-enrolled-{name}"],
            role="admin",
        )
        self._active_enrollment_session_id = None
        logger.info(f"VoiceEngine: quick-enrolled '{name}' as admin")
        return {
            "action": "voice_enrollment",
            "response": f"Done. {name} is now enrolled as admin. You can communicate freely.",
            "data": {
                "completed": True,
                "profile": {"id": profile.id, "name": profile.name, "role": profile.role, "samples": profile.samples},
            },
        }

    def enroll_speaker(self, name: str, samples: list[str]):
        return self.pipeline.speaker_registry.enroll(name, samples)

    def list_speakers(self) -> list[Dict[str, Any]]:
        profiles = self.pipeline.speaker_registry.all_profiles()
        return [
            {
                "id": p.id,
                "name": p.name,
                "samples": p.samples,
                "role": p.role,
                "created_at": p.created_at,
                "updated_at": p.updated_at,
            }
            for p in profiles
        ]

    def set_admin_speaker(self, speaker_id: str) -> Optional[Dict[str, Any]]:
        profile = self.pipeline.speaker_registry.set_admin(speaker_id)
        if profile is None:
            return None
        return {
            "id": profile.id,
            "name": profile.name,
            "samples": profile.samples,
            "role": profile.role,
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
        }

    def delete_speaker(self, speaker_id: str) -> Optional[Dict[str, Any]]:
        profile = self.pipeline.speaker_registry.delete_by_id(speaker_id)
        if profile is None:
            return None
        return {
            "id": profile.id,
            "name": profile.name,
            "samples": profile.samples,
            "role": profile.role,
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
        }

    def delete_all_speakers(self) -> int:
        return self.pipeline.speaker_registry.clear_all()

    def _extract_name_candidate(self, text: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z\s]", " ", text or "")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not cleaned:
            return ""

        trigger_like = {
            "recognize my voice",
            "recognize voice",
            "enroll my voice",
            "enroll voice",
            "register my voice",
            "register voice",
            "train my voice",
            "train voice",
            "voice enrollment",
        }
        if cleaned.lower() in trigger_like:
            return ""

        phrase_match = re.search(
            r"(?:for|name is|this is|it is)\s+([a-zA-Z][a-zA-Z\s]{1,40})$",
            cleaned,
            flags=re.IGNORECASE,
        )
        if phrase_match:
            return phrase_match.group(1).strip().title()
        return ""

    def extract_enrollment_name_hint(self, text: str) -> Optional[str]:
        candidate = self._extract_name_candidate(text)
        return candidate or None

    def _is_yes(self, text: str) -> bool:
        n = re.sub(r"\s+", " ", (text or "").lower()).strip()
        return n in {"yes", "y", "yeah", "yep", "sure", "ok", "okay", "confirm"}

    def _is_no(self, text: str) -> bool:
        n = re.sub(r"\s+", " ", (text or "").lower()).strip()
        return n in {"no", "n", "nope", "not now", "later", "cancel"}

    def start_enrollment_session(self, name: Optional[str] = None) -> Dict[str, Any]:
        session_id = str(uuid.uuid4())
        speaker_name = (name or "").strip()
        stage = "await_name"
        response = "Whose voice should I recognize? Please type the name in chat, for example: my name is Deekshith."

        if speaker_name:
            stage = "await_sample"
            response = (
                f"Enrolling {speaker_name}. I will give you {len(self._enrollment_prompts)} sentences. "
                f"Type each one in the chat box exactly as shown, then press Enter. "
                f"Sample 1 of {len(self._enrollment_prompts)}: {self._enrollment_prompts[0]}"
            )

        self._enrollment_sessions[session_id] = {
            "id": session_id,
            "stage": stage,
            "speaker_name": speaker_name,
            "samples": [],
            "audio_samples": [],
            "prompt_index": 0,
            "make_admin": False,
            "name_mode": "typed_preferred",
            "completed": False,
            "profile": None,
        }
        self._active_enrollment_session_id = session_id
        logger.info(
            "VoiceEngine: started enrollment session",
            session_id=session_id,
            stage=stage,
            speaker_name=speaker_name,
        )
        return {
            "action": "voice_enrollment",
            "response": response,
            "data": {
                "session_id": session_id,
                "stage": stage,
                "required_samples": len(self._enrollment_prompts),
            },
        }

    def get_enrollment_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        session = self._enrollment_sessions.get(session_id)
        if not session:
            return None
        return {
            "id": session["id"],
            "stage": session["stage"],
            "speaker_name": session["speaker_name"],
            "samples_collected": len(session["samples"]),
            "required_samples": len(self._enrollment_prompts),
            "completed": bool(session["completed"]),
            "profile": session.get("profile"),
        }

    def _finalize_enrollment(self, session: Dict[str, Any]) -> Dict[str, Any]:
        role = "admin" if bool(session.get("make_admin")) else "user"
        audio_samples = [p for p in session.get("audio_samples", []) if p]
        logger.info(
            "VoiceEngine: finalizing enrollment",
            session_id=session.get("id"),
            speaker_name=session.get("speaker_name"),
            text_samples=len(session.get("samples", [])),
            audio_samples=len(audio_samples),
            role=role,
        )
        if audio_samples:
            result = self.pipeline.speaker_registry.enroll_audio(
                session["speaker_name"],
                audio_samples,
                role=role,
            )
            # enroll_audio now returns a dict with 'profile' or 'error'
            if isinstance(result, dict) and "error" in result:
                session["stage"] = "await_sample"
                if self._active_enrollment_session_id == session["id"]:
                    self._active_enrollment_session_id = None
                return {
                    "action": "voice_enrollment",
                    "response": result["error"],
                    "data": {
                        "session_id": session["id"],
                        "stage": "failed",
                        "completed": False,
                        "quality_report": result.get("quality_report", {}),
                    },
                }
            profile = result["profile"] if isinstance(result, dict) else result
        else:
            profile = self.pipeline.speaker_registry.enroll(
                session["speaker_name"],
                session["samples"],
                role=role,
            )
        session["completed"] = True
        session["stage"] = "completed"
        session["profile"] = {
            "id": profile.id,
            "name": profile.name,
            "role": profile.role,
            "samples": profile.samples,
        }
        if self._active_enrollment_session_id == session["id"]:
            self._active_enrollment_session_id = None
        self._cleanup_enrollment_audio(session)

        response = f"Voice enrollment complete for {profile.name}."
        if profile.role == "admin":
            response += " This profile is now the admin voice."
        return {
            "action": "voice_enrollment",
            "response": response,
            "data": {
                "session_id": session["id"],
                "stage": session["stage"],
                "completed": True,
                "profile": session["profile"],
            },
        }

    def continue_enrollment_session(
        self,
        answer: str,
        session_id: Optional[str] = None,
        audio_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        sid = session_id or self._active_enrollment_session_id
        if not sid or sid not in self._enrollment_sessions:
            return {
                "action": "voice_enrollment",
                "response": "No active enrollment session. Say 'recognize voice' to start.",
                "data": {"session_id": None, "stage": "none", "completed": False},
            }

        session = self._enrollment_sessions[sid]
        stage = session["stage"]
        text = (answer or "").strip()
        logger.info(
            "VoiceEngine: continue enrollment",
            session_id=sid,
            stage=stage,
            answer_len=len(text),
            has_audio_path=bool(audio_path),
        )

        if stage == "await_name":
            name = self._extract_name_candidate(text)
            if not name:
                cleaned = re.sub(r"[^a-zA-Z\s]", " ", text or "")
                cleaned = re.sub(r"\s+", " ", cleaned).strip()
                trigger_like = {
                    "recognize my voice",
                    "recognize voice",
                    "enroll my voice",
                    "enroll voice",
                    "register my voice",
                    "register voice",
                    "train my voice",
                    "train voice",
                    "voice enrollment",
                }
                words = [w for w in cleaned.split(" ") if w]
                if cleaned and cleaned.lower() not in trigger_like and 1 <= len(words) <= 4:
                    name = " ".join(w.capitalize() for w in words)

            if not name:
                return {
                    "action": "voice_enrollment",
                    "response": "Please type the person's name clearly in chat, like 'Deekshith' or 'John Smith'.",
                    "data": {
                        "session_id": sid,
                        "stage": stage,
                        "samples_collected": 0,
                        "required_samples": len(self._enrollment_prompts),
                    },
                }
            session["speaker_name"] = name
            session["stage"] = "await_sample"
            session["prompt_index"] = 0
            return {
                "action": "voice_enrollment",
                "response": f"Great. I will enroll {name}. {self._enrollment_prompts[0]}",
                "data": {
                    "session_id": sid,
                    "stage": "await_sample",
                    "samples_collected": 0,
                    "required_samples": len(self._enrollment_prompts),
                },
            }

        if stage == "finalizing":
            logger.info("VoiceEngine: enrollment already finalizing", session_id=sid)
            return {
                "action": "voice_enrollment",
                "response": "Finalizing voice enrollment. Please wait.",
                "data": {
                    "session_id": sid,
                    "stage": "finalizing",
                    "samples_collected": len(session.get("samples", [])),
                    "required_samples": len(self._enrollment_prompts),
                    "completed": False,
                },
            }

        if stage == "await_sample":
            normalized_sample = re.sub(r"\s+", " ", (text or "").strip())
            words = [w for w in normalized_sample.split(" ") if w]

            # Prevent accidental auto-progress when STT returns empty/noisy snippets.
            if len(words) < 2:
                current_prompt = self._enrollment_prompts[min(session["prompt_index"], len(self._enrollment_prompts) - 1)]
                return {
                    "action": "voice_enrollment",
                    "response": f"I did not catch that clearly. Please repeat. {current_prompt}",
                    "data": {
                        "session_id": sid,
                        "stage": "await_sample",
                        "samples_collected": len(session["samples"]),
                        "required_samples": len(self._enrollment_prompts),
                    },
                }

            if audio_path:
                quality = assess_audio_sample(audio_path)
                if not quality.get("usable", False):
                    current_prompt = self._enrollment_prompts[min(session["prompt_index"], len(self._enrollment_prompts) - 1)]
                    logger.info(
                        "VoiceEngine: rejected enrollment sample due to low audio quality",
                        session_id=sid,
                        reason=str(quality.get("reason") or "unknown"),
                        duration_s=round(float(quality.get("duration_s") or 0.0), 3),
                        rms=round(float(quality.get("rms") or 0.0), 6),
                    )
                    return {
                        "action": "voice_enrollment",
                        "response": (
                            "I could not capture a clear voice sample. "
                            f"Please repeat clearly. {current_prompt}"
                        ),
                        "data": {
                            "session_id": sid,
                            "stage": "await_sample",
                            "samples_collected": len(session["samples"]),
                            "required_samples": len(self._enrollment_prompts),
                        },
                    }

            session["samples"].append(normalized_sample)
            if audio_path:
                persisted_audio = self._persist_enrollment_audio(audio_path, sid)
                if persisted_audio:
                    session.setdefault("audio_samples", []).append(persisted_audio)
            logger.info(
                "VoiceEngine: captured enrollment sample",
                session_id=sid,
                stage=stage,
                text_samples=len(session["samples"]),
                audio_samples=len(session.get("audio_samples", [])),
            )
            session["prompt_index"] += 1
            collected = len(session["samples"])

            if session["prompt_index"] < len(self._enrollment_prompts):
                next_prompt = self._enrollment_prompts[session["prompt_index"]]
                total = len(self._enrollment_prompts)
                return {
                    "action": "voice_enrollment",
                    "response": f"Good. Sample {collected} of {total} recorded. Next — {next_prompt}",
                    "data": {
                        "session_id": sid,
                        "stage": "await_sample",
                        "samples_collected": collected,
                        "required_samples": total,
                    },
                }

            session["stage"] = "confirm_admin"
            admin_exists = self.pipeline.speaker_registry.get_admin() is not None
            admin_note = " This will replace the current admin voice." if admin_exists else ""
            return {
                "action": "voice_enrollment",
                "response": f"Should I set {session['speaker_name']} as the admin voice? Say yes or no.{admin_note}",
                "data": {
                    "session_id": sid,
                    "stage": "confirm_admin",
                    "samples_collected": collected,
                    "required_samples": len(self._enrollment_prompts),
                },
            }

        if stage == "confirm_admin":
            if self._is_yes(text):
                session["make_admin"] = True
            elif self._is_no(text):
                session["make_admin"] = False
            else:
                return {
                    "action": "voice_enrollment",
                    "response": "Please answer with yes or no.",
                    "data": {
                        "session_id": sid,
                        "stage": "confirm_admin",
                        "samples_collected": len(session["samples"]),
                        "required_samples": len(self._enrollment_prompts),
                    },
                }
            # Guard against duplicate finalization from concurrent chat/voice requests.
            session["stage"] = "finalizing"
            return self._finalize_enrollment(session)

        return {
            "action": "voice_enrollment",
            "response": "Enrollment session is already complete.",
            "data": {
                "session_id": sid,
                "stage": session["stage"],
                "completed": bool(session.get("completed")),
                "profile": session.get("profile"),
            },
        }

    def status(self) -> Dict[str, Any]:
        music_status = self._get_music_status()
        return {
            "enabled": self.enabled,
            "session": self.session.to_dict(),
            "wake_word": settings.WAKE_WORD,
            "music": music_status,
            "modules": {
                "vad": self.pipeline.vad.__class__.__name__,
                "stt": self.recognizer.__class__.__name__,
                "speaker": self.pipeline.speaker_recognizer.__class__.__name__,
                "emotion": self.pipeline.emotion_detector.__class__.__name__,
                "language": self.pipeline.language_detector.__class__.__name__,
                "conversation": self.pipeline.conversation_manager.__class__.__name__,
                "speech_planner": self.pipeline.speech_planner.__class__.__name__,
                "tts": self.synthesizer.__class__.__name__,
            },
            "providers": self.component_factory.provider_summary(),
            "enrolled_speakers": [p.name for p in self.pipeline.speaker_registry.all_profiles()],
            "controls": {
                "current": self.get_voice_preferences(),
                "accent_profiles": copy.deepcopy(self._accent_profiles),
                "voice_modes": ["human", "cat"],
            },
        }

    def _get_music_status(self) -> Dict[str, Any]:
        if os.name != "posix":
            return {"playing": False, "state": "unavailable", "source": "unsupported"}

        script = (
            'try\n'
            '  tell application "Music"\n'
            '    if player state is playing then return "playing"\n'
            '    if player state is paused then return "paused"\n'
            '    return "stopped"\n'
            '  end tell\n'
            'on error\n'
            '  return "stopped"\n'
            'end try'
        )
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5,
            )
            state = (result.stdout or "").strip().lower()
            if state not in {"playing", "paused", "stopped"}:
                state = "unknown"
            return {
                "playing": state == "playing",
                "state": state,
                "source": "music",
            }
        except Exception as ex:
            logger.warning(f"VoiceEngine: failed to query music playback status: {ex}")
            return {"playing": False, "state": "unknown", "source": "error"}

    def _clamp_int(self, value: Any, fallback: int, minimum: int, maximum: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return fallback
        return max(minimum, min(maximum, parsed))

    def get_voice_preferences(self) -> Dict[str, Any]:
        return copy.deepcopy(self._voice_preferences)

    def resolve_voice_preferences(self, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        preferences = copy.deepcopy(self._voice_preferences)
        updates = overrides or {}

        voice_mode = str(updates.get("voice_mode") or preferences.get("voice_mode") or "human").strip().lower()
        if voice_mode not in self._voice_mode_defaults:
            voice_mode = "human"
        preferences["voice_mode"] = voice_mode

        mode_defaults = self._voice_mode_defaults[voice_mode]
        preferences["style"] = str(mode_defaults.get("style", preferences["style"]))
        preferences["rate"] = self._clamp_int(mode_defaults.get("rate"), preferences["rate"], 120, 240)
        preferences["pitch"] = self._clamp_int(mode_defaults.get("pitch"), preferences["pitch"], 0, 99)

        profile = str(updates.get("accent_profile") or preferences.get("accent_profile") or "").strip().lower()
        if voice_mode == "human" and profile and profile in self._accent_profiles:
            preferences["accent_profile"] = profile
            profile_defaults = self._accent_profiles[profile]
            preferences["style"] = str(profile_defaults.get("style", preferences["style"]))
            preferences["rate"] = self._clamp_int(profile_defaults.get("rate"), preferences["rate"], 120, 240)
            preferences["pitch"] = self._clamp_int(profile_defaults.get("pitch"), preferences["pitch"], 0, 99)

        if updates.get("voice") is not None:
            preferences["voice"] = str(updates.get("voice") or "").strip()

        voice_key = str(preferences.get("voice") or "").strip().lower()
        if voice_key in self._voice_model_presets:
            voice_defaults = self._voice_model_presets[voice_key]
            preferences["style"] = str(voice_defaults.get("style", preferences["style"]))
            preferences["rate"] = self._clamp_int(voice_defaults.get("rate"), preferences["rate"], 120, 240)
            preferences["pitch"] = self._clamp_int(voice_defaults.get("pitch"), preferences["pitch"], 0, 99)

        if updates.get("style") is not None:
            style = str(updates.get("style") or "").strip().lower()
            if style in {"natural", "warm", "clear", "excited", "calm"}:
                preferences["style"] = style
        if updates.get("rate") is not None:
            preferences["rate"] = self._clamp_int(updates.get("rate"), preferences["rate"], 120, 240)
        if updates.get("pitch") is not None:
            preferences["pitch"] = self._clamp_int(updates.get("pitch"), preferences["pitch"], 0, 99)

        return preferences

    def set_voice_preferences(self, updates: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self._voice_preferences = self.resolve_voice_preferences(updates)
        return self.get_voice_preferences()

    def handle_text(
        self,
        source_text: str,
        speak: bool = True,
        force: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Main test hook for the voice pipeline.

        In phase 2 we keep the input interface text-first so you can
        simulate microphone transcription from an API or CLI before
        wiring real audio capture.
        """
        if not self.enabled and not force:
            return {
                "enabled": False,
                "state": self.session.state.value,
                "response": "Voice is disabled in settings.",
            }

        text = (source_text or "").strip()
        normalized = re.sub(r"\s+", " ", text.lower())

        # While enrollment is active, always treat incoming turns as enrollment
        # responses unless the user explicitly cancels. This prevents sample
        # phrases from accidentally restarting enrollment mid-flow.
        if self._active_enrollment_session_id:
            if normalized in {"cancel", "cancel enrollment", "stop enrollment"}:
                sid = self._active_enrollment_session_id
                self._active_enrollment_session_id = None
                if sid in self._enrollment_sessions:
                    self._cleanup_enrollment_audio(self._enrollment_sessions.get(sid))
                    self._enrollment_sessions[sid]["stage"] = "cancelled"
                logger.info("VoiceEngine: enrollment cancelled", session_id=sid)
                return {
                    "action": "voice_enrollment",
                    "response": "Voice enrollment cancelled.",
                    "data": {"session_id": sid, "stage": "cancelled", "completed": False},
                }
            logger.info(
                "VoiceEngine: routing text through active enrollment session",
                session_id=self._active_enrollment_session_id,
                has_audio_path=bool((metadata or {}).get("audio_path")),
            )
            return self.continue_enrollment_session(
                text,
                self._active_enrollment_session_id,
                audio_path=(metadata or {}).get("audio_path"),
            )

        if self._is_quick_enroll(text):
            return self.quick_enroll(text)

        if self.is_enrollment_trigger(text):
            hinted_name = self._extract_name_candidate(text)
            return self.start_enrollment_session(name=hinted_name or None)

        # Suppress input while Nova is speaking (prevents self-listening echo loop)
        _speaking = self.session.state == VoiceState.SPEAKING
        if not _speaking:
            try:
                _speaking = bool(self.synthesizer.is_speaking)
            except Exception:
                pass
        if _speaking:
            logger.info("VoiceEngine: suppressed input — currently speaking")
            return {
                "response": "",
                "action": "voice",
                "voice": self.session.to_dict(),
                "message": "Suppressed: Nova is speaking.",
                "enabled": self.enabled,
                "state": self.session.state.value,
            }

        bus.publish(Event.VOICE_RECEIVED, {"source": "text", "value": source_text})
        merged_preferences = self.resolve_voice_preferences((metadata or {}).get("voice_preferences", {}))
        frame_metadata = dict(metadata or {})
        frame_metadata["voice_preferences"] = merged_preferences
        frame_metadata["recognition_enabled"] = bool(self.recognition_enabled)
        frame = VoiceInputFrame(
            source=source_text,
            source_type="text",
            speak=speak,
            force_wake=force,
            metadata=frame_metadata,
        )
        payload = self.pipeline.process(frame, self.session)
        transcript = self.session.transcript
        if transcript:
            bus.publish(Event.THOUGHT_CREATED, {"transcript": transcript})
        response_text = self.session.response
        if response_text:
            bus.publish(Event.RESPONSE_READY, {"response": response_text})
        payload.setdefault("enabled", self.enabled)
        payload.setdefault("state", self.session.state.value)
        return payload

    def listen(self, source_text: str, speak: bool = True) -> Dict[str, Any]:
        return self.handle_text(source_text=source_text, speak=speak)

    def stop_speaking(self) -> Dict[str, Any]:
        """Barge-in: interrupt Nova mid-sentence and switch to listening."""
        self._speech_generation = getattr(self, "_speech_generation", 0) + 1
        was_speaking = False
        if hasattr(self.synthesizer, 'interrupt'):
            was_speaking = self.synthesizer.interrupt()
        else:
            stopped = self.synthesizer.stop() if hasattr(self.synthesizer, "stop") else {"success": False, "stopped": []}
            was_speaking = bool(stopped.get("stopped"))

        if was_speaking:
            bus.publish(Event.SPEECH_INTERRUPTED, {"reason": "barge_in"})
            self.session.touch(VoiceState.INTERRUPTED)
            bus.publish(Event.AVATAR_IDLE, {"reason": "barge_in"})
            self.session.touch(VoiceState.IDLE)
        else:
            bus.publish(Event.AVATAR_SPEAKING_COMPLETED, {"reason": "stopped_by_user"})
            self.session.touch(VoiceState.IDLE)
            bus.publish(Event.AVATAR_IDLE, {"reason": "voice_stop_requested"})

        return {"interrupted": was_speaking, "state": self.session.state.value}
