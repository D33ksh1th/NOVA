"""
Text-to-speech adapters.

Three backends, selected by TTS_PROVIDER in settings:

  "say" / "espeak"  — system TTS (macOS say, Linux espeak). Always available.
  "kokoro"          — Kokoro neural TTS (CLI, KOKORO_TTS_COMMAND).
  "piper"           — Piper TTS (CLI, PIPER_TTS_COMMAND).

Kokoro and Piper fall back to system TTS when their binary is absent.
"""

from __future__ import annotations

import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from packages.common import logger
from packages.config import settings
from .speech_text import prepare_speech_text


@dataclass
class SpeechSynthesisResult:
    text: str
    backend: str = "none"
    spoken: bool = False
    command: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# Base / system TTS  (macOS say, Linux espeak)
# ---------------------------------------------------------------------------

class SpeechSynthesizer:
    def __init__(self, voice: Optional[str] = None, rate: int = 180, pitch: int = 50):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch

    def speak(
        self,
        text: str,
        play: bool = True,
        style: Optional[str] = None,
        rate: Optional[int] = None,
        pitch: Optional[int] = None,
        voice: Optional[str] = None,
        voice_mode: Optional[str] = None,
    ) -> SpeechSynthesisResult:
        prepared = self._prepare_text(text)
        prepared = self._apply_voice_mode(prepared, voice_mode)
        if not prepared:
            return SpeechSynthesisResult(text="", backend="none", spoken=False)

        if settings.TTS_NEURAL_ONLY:
            return SpeechSynthesisResult(
                text=prepared,
                backend="blocked",
                spoken=False,
                error="Neural-only mode: Kokoro unavailable, system TTS blocked.",
            )

        selected_voice = voice or self.voice
        selected_rate = rate if rate is not None else self.rate
        selected_pitch = pitch if pitch is not None else self.pitch

        if style == "excited":
            selected_rate += 8
            selected_pitch += 4
        elif style == "calm":
            selected_rate = max(140, selected_rate - 8)
            selected_pitch -= 3

        system = platform.system().lower()
        try:
            if system == "darwin" and shutil.which("say"):
                cmd = ["say"]
                resolved_voice = self._resolve_macos_voice(selected_voice)
                cmd.extend(["-v", resolved_voice])
                cmd.extend(["-r", str(selected_rate), prepared])
                if play:
                    subprocess.run(cmd, check=True)
                    return SpeechSynthesisResult(text=prepared, backend="say", spoken=True, command=shlex.join(cmd))
                return SpeechSynthesisResult(text=prepared, backend="say", spoken=False, command=shlex.join(cmd))

            if shutil.which("espeak"):
                cmd = ["espeak", "-s", str(selected_rate)]
                if selected_voice:
                    cmd.extend(["-v", selected_voice])
                else:
                    cmd.extend(["-v", "en+f3"])
                cmd.extend(["-p", str(max(0, min(99, selected_pitch)))])
                cmd.append(prepared)
                if play:
                    subprocess.run(cmd, check=True)
                    return SpeechSynthesisResult(text=prepared, backend="espeak", spoken=True, command=shlex.join(cmd))
                return SpeechSynthesisResult(text=prepared, backend="espeak", spoken=False, command=shlex.join(cmd))

            logger.info("SpeechSynthesizer: no local TTS backend found; returning text only")
            return SpeechSynthesisResult(text=prepared, backend="text", spoken=False)
        except Exception as ex:
            logger.error(f"SpeechSynthesizer error -> {ex}")
            return SpeechSynthesisResult(text=prepared, backend="error", spoken=False, error=str(ex))

    def speak_sequence(
        self,
        chunks: list[str],
        play: bool = True,
        style: Optional[str] = None,
        rate: Optional[int] = None,
        pitch: Optional[int] = None,
        voice: Optional[str] = None,
        voice_mode: Optional[str] = None,
        pause_ms: int = 180,
        start_delay_ms: int = 0,
    ) -> SpeechSynthesisResult:
        prepared_chunks = [self._prepare_text(chunk) for chunk in (chunks or [])]
        prepared_chunks = [chunk for chunk in prepared_chunks if chunk]
        if not prepared_chunks:
            return SpeechSynthesisResult(text="", backend="none", spoken=False)

        if start_delay_ms > 0:
            time.sleep(start_delay_ms / 1000.0)

        all_commands: list[str] = []
        final_backend = "none"
        final_error = ""
        any_spoken = False

        for index, chunk in enumerate(prepared_chunks):
            result = self.speak(
                chunk,
                play=play,
                style=style,
                rate=rate,
                pitch=pitch,
                voice=voice,
                voice_mode=voice_mode,
            )
            final_backend = result.backend or final_backend
            final_error = result.error or final_error
            any_spoken = any_spoken or result.spoken
            if result.command:
                all_commands.append(result.command)

            if play and index < len(prepared_chunks) - 1:
                time.sleep(max(0, pause_ms) / 1000.0)

        return SpeechSynthesisResult(
            text=" ".join(prepared_chunks),
            backend=final_backend,
            spoken=any_spoken,
            command=" && ".join(all_commands),
            error=final_error,
        )

    def _apply_voice_mode(self, text: str, voice_mode: Optional[str]) -> str:
        # Cat mode should change voice timbre, not language/content.
        return text

    def _resolve_macos_voice(self, preferred_voice: Optional[str]) -> str:
        available = self._list_macos_voices()
        if not available:
            return preferred_voice or "Samantha"
        if preferred_voice and preferred_voice in available:
            return preferred_voice
        for candidate in ("Veena", "Lekha", "Rishi"):
            if candidate in available:
                return candidate
        if "Samantha" in available:
            return "Samantha"
        return available[0]

    def _list_macos_voices(self) -> list[str]:
        if platform.system().lower() != "darwin" or not shutil.which("say"):
            return []
        try:
            result = subprocess.run(["say", "-v", "?"], check=True, capture_output=True, text=True)
            voices: list[str] = []
            for line in result.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                voice = line.split(maxsplit=1)[0]
                if voice:
                    voices.append(voice)
            return voices
        except Exception:
            return []

    def _prepare_text(self, text: str) -> str:
        text = prepare_speech_text(text)
        if len(text) > 900:
            text = text[:900].rstrip() + "."
        return text

    def stop(self) -> dict:
        """Best-effort cancellation for local TTS playback processes."""
        if not shutil.which("pkill"):
            return {"success": False, "stopped": [], "error": "pkill_not_available"}

        stopped: list[str] = []

        def _try_stop(args: list[str], label: str) -> None:
            result = subprocess.run(args, capture_output=True, text=True)
            if result.returncode == 0:
                stopped.append(label)

        # System playback and TTS processes.
        _try_stop(["pkill", "-x", "afplay"], "afplay")
        _try_stop(["pkill", "-x", "say"], "say")
        _try_stop(["pkill", "-x", "espeak"], "espeak")
        _try_stop(["pkill", "-x", "aplay"], "aplay")
        _try_stop(["pkill", "-x", "ffplay"], "ffplay")
        _try_stop(["pkill", "-x", "piper"], "piper")
        _try_stop(["pkill", "-f", "--", "-m piper"], "python_m_piper")
        _try_stop(["pkill", "-x", "kokoro-tts"], "kokoro-tts")

        return {
            "success": True,
            "stopped": stopped,
        }


# ---------------------------------------------------------------------------
# Kokoro TTS  (neural, in-process via kokoro-onnx — model held warm)
# ---------------------------------------------------------------------------

class KokoroSpeechSynthesizer(SpeechSynthesizer):
    """
    Kokoro neural TTS using kokoro-onnx directly in-process.
    Model is loaded ONCE on first use and held warm in memory.
    No subprocess spawning — fast, smooth, real voice.

    Falls back to system TTS if kokoro-onnx is not installed.
    """

    BACKEND = "kokoro"

    # Model paths — relative to NOVA root
    _DEFAULT_MODEL = str(Path(__file__).resolve().parents[2] / "models" / "kokoro" / "kokoro-v1.0.onnx")
    _DEFAULT_VOICES = str(Path(__file__).resolve().parents[2] / "models" / "kokoro" / "voices-v1.0.bin")

    # Shared instance (loaded once, reused across all calls)
    _kokoro_instance = None
    _kokoro_loaded = False

    # Voice profiles mapped to accent_profile setting
    ACCENT_VOICES = {
        "jarvis": "bm_george",
        "friday": "bf_emma",
        "devi": "hf_alpha",
        "english_jarvis": "bm_george",
        "english_friday": "bf_emma",
        "english_lessac": "bm_george",
        "english_ryan": "bm_george",
        "english_amy": "bf_emma",
        "bm_george": "bm_george",
        "bf_emma": "bf_emma",
        "english_clear": "bf_emma",
        "indian": "hf_alpha",
    }

    STYLE_SPEED = {
        "natural": 1.0,
        "warm": 0.99,
        "clear": 1.0,
        "excited": 1.04,
        "calm": 0.98,
        "jarvis": 0.98,
        "friday": 1.0,
    }

    # Active persona — set via /voice/persona endpoint
    _active_persona: str = "jarvis"

    def __init__(
        self,
        tts_command: str = "",  # ignored — kept for config compat
        output_format: str = "wav",
        voice: Optional[str] = None,
        rate: int = 180,
        pitch: int = 50,
        kokoro_voice: str = "bm_george",
        kokoro_speed: float = 1.1,
        model_path: Optional[str] = None,
        voices_path: Optional[str] = None,
    ):
        super().__init__(voice=voice, rate=rate, pitch=pitch)
        self.output_format = output_format
        self.kokoro_voice = kokoro_voice
        self.kokoro_speed = kokoro_speed
        self._playback_generation = 0
        self._playback_lock = threading.RLock()
        self._output_lock = threading.Lock()
        self._playback_process = None
        self._model_path = model_path or self._DEFAULT_MODEL
        self._voices_path = voices_path or self._DEFAULT_VOICES

    @classmethod
    def _get_kokoro(cls, model_path: str, voices_path: str):
        """Get or create the shared Kokoro instance."""
        if cls._kokoro_instance is not None:
            return cls._kokoro_instance

        try:
            from kokoro_onnx import Kokoro
            # Check model files exist
            if not Path(model_path).exists():
                logger.warning("KokoroSpeechSynthesizer: model files not found")
                return None

            cls._kokoro_instance = Kokoro(model_path, voices_path)
            cls._kokoro_loaded = True
            logger.info("KokoroSpeechSynthesizer: model loaded (warm in memory)")
            return cls._kokoro_instance
        except ImportError:
            logger.warning("KokoroSpeechSynthesizer: kokoro-onnx not installed")
            return None
        except Exception as ex:
            logger.error(f"KokoroSpeechSynthesizer: failed to load model: {ex}")
            return None

    def _resolve_voice_and_speed(self, style: Optional[str] = None, voice: Optional[str] = None, rate: Optional[int] = None) -> tuple[str, float]:
        """Resolve supported voice profiles and keep pacing within a conversational range."""
        kokoro_voice = self.ACCENT_VOICES.get(voice, self.kokoro_voice)
        speed = self.kokoro_speed
        if style and style in self.STYLE_SPEED:
            speed *= self.STYLE_SPEED[style]
        if rate is not None:
            speed *= rate / 180.0
        return kokoro_voice, max(0.85, min(1.2, speed))

    def _synthesize(self, kokoro, text: str, voice: str, speed: float):
        generation = self._playback_generation
        language = "en-gb" if voice.startswith(("bm_", "bf_")) else "hi" if voice.startswith(("hm_", "hf_")) else "en-us"
        result = kokoro.create(text, voice=voice, speed=speed, lang=language)
        if generation != self._playback_generation:
            raise InterruptedError("Speech interrupted during synthesis")
        return result

    def _check_playback(self, generation: int):
        if generation != self._playback_generation:
            raise InterruptedError("Speech interrupted")

    def _run_playback(self, command: list[str], generation: int):
        with self._playback_lock:
            self._check_playback(generation)
            process = subprocess.Popen(command)
            self._playback_process = process
        try:
            result = process.wait()
            self._check_playback(generation)
            if result:
                raise RuntimeError(f"Speech playback exited with code {result}")
        finally:
            with self._playback_lock:
                if self._playback_process is process:
                    self._playback_process = None

    def _play_samples(self, samples, sample_rate: int, generation: int):
        with self._output_lock:
            self._play_samples_serial(samples, sample_rate, generation)

    def _play_samples_serial(self, samples, sample_rate: int, generation: int):
        self._check_playback(generation)
        started = False
        try:
            import sounddevice as sd
            with self._playback_lock:
                self._check_playback(generation)
                sd.play(samples, sample_rate, latency="high")
                started = True
            playback_status = sd.wait()
            if playback_status and playback_status.output_underflow:
                logger.warning("KokoroSpeechSynthesizer: audio output underrun detected")
        except InterruptedError:
            raise
        except Exception:
            self._check_playback(generation)
            if started:
                raise
            import soundfile as sf
            with tempfile.NamedTemporaryFile(suffix=".wav", prefix="nova_kokoro_") as audio_file:
                sf.write(audio_file.name, samples, sample_rate)
                self._play_audio(audio_file.name, generation)
        self._check_playback(generation)

    def _fallback_speak(self, text: str, play: bool, generation: int, **kwargs):
        result = super().speak(text, play=False, **kwargs)
        try:
            self._check_playback(generation)
            if play and result.command:
                self._run_playback(shlex.split(result.command), generation)
                result.spoken = True
        except InterruptedError:
            result.spoken = False
            result.error = "interrupted"
        return result

    @staticmethod
    def _prepare_audio(samples, sample_rate: int):
        from math import gcd
        import numpy as np
        from scipy.signal import resample_poly

        audio = np.asarray(samples, dtype=np.float32).copy()
        if audio.ndim != 1 or not audio.size or sample_rate <= 0 or not np.isfinite(audio).all():
            raise ValueError("Invalid neural speech audio")
        target_rate = 48000
        if sample_rate != target_rate:
            divisor = gcd(sample_rate, target_rate)
            audio = resample_poly(audio, target_rate // divisor, sample_rate // divisor)
        peak = float(np.max(np.abs(audio)))
        if peak > 0.98:
            audio *= 0.98 / peak
        fade_samples = min(int(target_rate * 0.005), len(audio) // 2)
        if fade_samples:
            ramp = np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)
            audio[:fade_samples] *= ramp
            audio[-fade_samples:] *= ramp[::-1]
        return audio, target_rate

    def speak(
        self,
        text: str,
        play: bool = True,
        style: Optional[str] = None,
        rate: Optional[int] = None,
        pitch: Optional[int] = None,
        voice: Optional[str] = None,
        voice_mode: Optional[str] = None,
    ) -> SpeechSynthesisResult:
        generation = self._playback_generation
        cleaned = self._prepare_text(text)
        cleaned = self._apply_voice_mode(cleaned, voice_mode)
        if not cleaned:
            return SpeechSynthesisResult(text="", backend="none", spoken=False)

        kokoro = self._get_kokoro(self._model_path, self._voices_path)
        if kokoro is None:
            logger.warning("KokoroSpeechSynthesizer: not available — falling back to system TTS")
            return self._fallback_speak(text, play, generation, style=style, rate=rate, pitch=pitch, voice=voice, voice_mode=voice_mode)

        # Resolve voice and speed from style/accent settings
        kokoro_voice, speed = self._resolve_voice_and_speed(style, voice, rate)

        try:
            import numpy as np
            import soundfile as sf

            self._check_playback(generation)
            samples, sr = self._synthesize(kokoro, cleaned, kokoro_voice, speed)

            samples, sr = self._prepare_audio(samples, sr)

            if play:
                self._play_samples(samples, sr, generation)

            return SpeechSynthesisResult(
                text=cleaned, backend=self.BACKEND, spoken=play,
                command=f"kokoro-onnx({self.kokoro_voice}, speed={speed:.2f})"
            )
        except InterruptedError:
            return SpeechSynthesisResult(text=cleaned, backend=self.BACKEND, spoken=False, error="interrupted")
        except Exception as ex:
            logger.error(f"KokoroSpeechSynthesizer speech error: {ex}")
            return SpeechSynthesisResult(text=cleaned, backend=self.BACKEND, spoken=False, error=str(ex))

    def speak_sequence(
        self,
        chunks: list[str],
        play: bool = True,
        style: Optional[str] = None,
        rate: Optional[int] = None,
        pitch: Optional[int] = None,
        voice: Optional[str] = None,
        voice_mode: Optional[str] = None,
        pause_ms: int = 180,
        start_delay_ms: int = 0,
        severity: int = 0,
    ) -> SpeechSynthesisResult:
        """Synthesize and play one continuous, interruptible response."""
        generation = self._playback_generation
        if start_delay_ms > 0:
            time.sleep(start_delay_ms / 1000.0)

        prepared_chunks = [self._prepare_text(chunk) for chunk in (chunks or [])]
        prepared_chunks = [chunk for chunk in prepared_chunks if chunk]
        if not prepared_chunks:
            return SpeechSynthesisResult(text="", backend="none", spoken=False)

        # Apply prosody based on severity
        prepared_chunks = self._apply_prosody(prepared_chunks, severity)

        kokoro = self._get_kokoro(self._model_path, self._voices_path)
        if kokoro is None:
            return self._fallback_speak(" ".join(prepared_chunks), play, generation, style=style, rate=rate, pitch=pitch, voice=voice, voice_mode=voice_mode)

        import numpy as np
        import soundfile as sf

        kokoro_voice, speed = self._resolve_voice_and_speed(style, voice, rate)
        speed = self._severity_speed(speed, severity)

        # Synthesize all chunks into one continuous buffer, then play once
        return self._speak_merged(prepared_chunks, kokoro, kokoro_voice, speed, pause_ms, play, generation)

    def _speak_merged(
        self,
        chunks: list[str],
        kokoro,
        voice: str,
        speed: float,
        pause_ms: int,
        play: bool,
        generation: Optional[int] = None,
    ) -> SpeechSynthesisResult:
        """Synthesize full text as ONE call for seamless audio."""
        import numpy as np
        import soundfile as sf

        # Join all chunks into one string — Kokoro handles sentence pauses naturally
        full_text = " ".join(chunks)
        if generation is None:
            generation = self._playback_generation

        try:
            self._check_playback(generation)
            samples, sr = self._synthesize(kokoro, full_text, voice, speed)
            samples, sr = self._prepare_audio(samples, sr)
            if play:
                self._play_samples(samples, sr, generation)
        except InterruptedError:
            return SpeechSynthesisResult(text=full_text, backend=self.BACKEND, spoken=False, error="interrupted")
        except Exception as ex:
            logger.error(f"KokoroSpeechSynthesizer: synthesis failed: {ex}")
            return SpeechSynthesisResult(text=full_text, backend="error", spoken=False, error=str(ex))

        if not play:
            return SpeechSynthesisResult(text=full_text, backend=self.BACKEND, spoken=False)

        return SpeechSynthesisResult(
            text=full_text,
            backend=self.BACKEND,
            spoken=True,
            command=f"kokoro-merged({voice}, speed={speed:.2f})",
        )

    def interrupt(self) -> bool:
        """Stop playback immediately."""
        with self._playback_lock:
            self._playback_generation += 1
            if self._playback_process is not None and self._playback_process.poll() is None:
                self._playback_process.terminate()
                try:
                    self._playback_process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    self._playback_process.kill()
                    self._playback_process.wait(timeout=0.5)
            try:
                import sounddevice as sd
                sd.stop()
            except Exception:
                pass
        return True

    @property
    def is_speaking(self) -> bool:
        try:
            import sounddevice as sd
            stream = sd.get_stream()
            return stream.active if stream else False
        except Exception:
            return False

    def _severity_speed(self, base_speed: float, severity: int) -> float:
        """Map event severity to delivery speed."""
        if severity >= 4:
            return base_speed * 1.15  # urgent: faster, clipped
        if severity >= 3:
            return base_speed * 1.08
        return base_speed

    def _apply_prosody(self, chunks: list[str], severity: int) -> list[str]:
        """Insert prosody markers based on severity and structure."""
        if not chunks:
            return chunks
        # Insert a brief pause before the conclusion (last chunk)
        if len(chunks) > 1 and severity >= 2:
            chunks[-1] = "... " + chunks[-1]
        return chunks

    def _play_audio(self, path: str, generation: Optional[int] = None) -> None:
        if generation is None:
            generation = self._playback_generation
        system = platform.system().lower()
        if system == "darwin":
            command = ["afplay", path]
        elif shutil.which("aplay"):
            command = ["aplay", path]
        elif shutil.which("ffplay"):
            command = ["ffplay", "-nodisp", "-autoexit", path]
        else:
            raise RuntimeError("No audio playback backend available")
        self._run_playback(command, generation)


# ---------------------------------------------------------------------------
# Piper TTS  (fast, offline, neural)
# ---------------------------------------------------------------------------

class PiperSpeechSynthesizer(SpeechSynthesizer):
    """
    Piper TTS invoked as a subprocess CLI.

    PIPER_TTS_COMMAND e.g. "piper --model en_US-lessac-medium"
    Piper reads text from stdin, writes WAV to --output_file.
    Falls back to system TTS when the binary is not found.
    """

    BACKEND = "piper"

    def __init__(
        self,
        tts_command: str = "",
        output_format: str = "wav",
        voice: Optional[str] = None,
        rate: int = 180,
        pitch: int = 50,
    ):
        super().__init__(voice=voice, rate=rate, pitch=pitch)
        self.tts_command = (tts_command or "").strip()
        self.output_format = output_format
        self._project_root = Path(__file__).resolve().parents[2]
        self._voice_model_map = {
            "english_lessac": (
                self._project_root / "assets/voices/piper/en_US_lessac_medium/en_US-lessac-medium.onnx",
                self._project_root / "assets/voices/piper/en_US_lessac_medium/en_US-lessac-medium.onnx.json",
            ),
            "english_amy": (
                self._project_root / "assets/voices/piper/en_US_amy_medium/en_US-amy-medium.onnx",
                self._project_root / "assets/voices/piper/en_US_amy_medium/en_US-amy-medium.onnx.json",
            ),
            "english_ryan": (
                self._project_root / "assets/voices/piper/en_US_ryan_medium/en_US-ryan-medium.onnx",
                self._project_root / "assets/voices/piper/en_US_ryan_medium/en_US-ryan-medium.onnx.json",
            ),
            "ultron": (
                self._project_root / "assets/voices/piper/en_US_ryan_medium/en_US-ryan-medium.onnx",
                self._project_root / "assets/voices/piper/en_US_ryan_medium/en_US-ryan-medium.onnx.json",
            ),
            "nova": (
                self._project_root / "assets/voices/piper/en_US_lessac_medium/en_US-lessac-medium.onnx",
                self._project_root / "assets/voices/piper/en_US_lessac_medium/en_US-lessac-medium.onnx.json",
            ),
            "atlas": (
                self._project_root / "assets/voices/piper/en_US_ryan_medium/en_US-ryan-medium.onnx",
                self._project_root / "assets/voices/piper/en_US_ryan_medium/en_US-ryan-medium.onnx.json",
            ),
            "echo": (
                self._project_root / "assets/voices/piper/en_US_amy_medium/en_US-amy-medium.onnx",
                self._project_root / "assets/voices/piper/en_US_amy_medium/en_US-amy-medium.onnx.json",
            ),
        }

    def speak(
        self,
        text: str,
        play: bool = True,
        style: Optional[str] = None,
        rate: Optional[int] = None,
        pitch: Optional[int] = None,
        voice: Optional[str] = None,
        voice_mode: Optional[str] = None,
    ) -> SpeechSynthesisResult:
        cleaned = self._prepare_text(text)
        cleaned = self._apply_voice_mode(cleaned, voice_mode)
        if not cleaned:
            return SpeechSynthesisResult(text="", backend="none", spoken=False)

        if not self.tts_command:
            logger.warning("PiperSpeechSynthesizer: PIPER_TTS_COMMAND not configured — falling back to system TTS")
            return super().speak(text, play=play, style=style, rate=rate, pitch=pitch, voice=voice, voice_mode=voice_mode)

        parts = shlex.split(self.tts_command)
        resolved_binary = self._resolve_command_binary(parts[0])
        if not resolved_binary:
            logger.warning(f"PiperSpeechSynthesizer: binary '{parts[0]}' not found — falling back to system TTS")
            return super().speak(text, play=play, style=style, rate=rate, pitch=pitch, voice=voice, voice_mode=voice_mode)

        parts[0] = resolved_binary

        try:
            return self._run_piper(
                cleaned,
                command_parts=parts,
                play=play,
                style=style,
                rate=rate,
                voice=voice,
                voice_mode=voice_mode,
            )
        except Exception as ex:
            logger.error(f"PiperSpeechSynthesizer error: {ex} — falling back")
            return super().speak(text, play=play, style=style, rate=rate, pitch=pitch, voice=voice, voice_mode=voice_mode)

    def speak_sequence(
        self,
        chunks: list[str],
        play: bool = True,
        style: Optional[str] = None,
        rate: Optional[int] = None,
        pitch: Optional[int] = None,
        voice: Optional[str] = None,
        voice_mode: Optional[str] = None,
        pause_ms: int = 180,
        start_delay_ms: int = 0,
    ) -> SpeechSynthesisResult:
        if start_delay_ms > 0:
            time.sleep(start_delay_ms / 1000.0)

        prepared_chunks = [self._prepare_text(chunk) for chunk in (chunks or [])]
        prepared_chunks = [chunk for chunk in prepared_chunks if chunk]
        if not prepared_chunks:
            return SpeechSynthesisResult(text="", backend="none", spoken=False)

        all_commands: list[str] = []
        final_backend = "none"
        final_error = ""
        any_spoken = False

        for index, chunk in enumerate(prepared_chunks):
            result = self.speak(
                chunk,
                play=play,
                style=style,
                rate=rate,
                pitch=pitch,
                voice=voice,
                voice_mode=voice_mode,
            )
            final_backend = result.backend or final_backend
            final_error = result.error or final_error
            any_spoken = any_spoken or result.spoken
            if result.command:
                all_commands.append(result.command)
            if play and index < len(prepared_chunks) - 1:
                time.sleep(max(0, pause_ms) / 1000.0)

        return SpeechSynthesisResult(
            text=" ".join(prepared_chunks),
            backend=final_backend,
            spoken=any_spoken,
            command=" && ".join(all_commands),
            error=final_error,
        )

    def _run_piper(
        self,
        text: str,
        command_parts: list[str],
        play: bool,
        style: Optional[str],
        rate: Optional[int],
        voice: Optional[str],
        voice_mode: Optional[str],
    ) -> SpeechSynthesisResult:
        with tempfile.NamedTemporaryFile(
            suffix=f".{self.output_format}", delete=False, prefix="nova_piper_"
        ) as tmp:
            out_path = tmp.name

        cmd = list(command_parts)
        self._apply_voice_override(cmd, voice)
        lower_flags = {item.lower() for item in cmd}

        selected_rate = rate if rate is not None else self.rate
        length_scale = max(0.78, min(1.28, 180.0 / max(120.0, float(selected_rate))))

        selected_style = (style or "").strip().lower()
        selected_mode = str(voice_mode or "human").strip().lower()
        if selected_style == "clear":
            length_scale = min(1.20, length_scale + 0.01)
            noise_scale = 0.48
            noise_w_scale = 0.70
            sentence_silence = 0.18
        elif selected_style == "warm":
            length_scale = min(1.24, length_scale + 0.06)
            noise_scale = 0.54
            noise_w_scale = 0.74
            sentence_silence = 0.14
        elif selected_style == "excited":
            length_scale = max(0.82, length_scale - 0.10)
            noise_scale = 0.70
            noise_w_scale = 0.95
            sentence_silence = 0.10
        elif selected_style == "calm":
            length_scale = min(1.26, length_scale + 0.08)
            noise_scale = 0.50
            noise_w_scale = 0.68
            sentence_silence = 0.18
        else:
            noise_scale = 0.62
            noise_w_scale = 0.86
            sentence_silence = 0.14

        if selected_mode == "cat":
            length_scale = max(0.90, length_scale - 0.06)
            noise_scale = min(0.78, noise_scale + 0.08)
            noise_w_scale = min(0.98, noise_w_scale + 0.08)
            sentence_silence = max(0.08, sentence_silence - 0.02)

        if "--length-scale" not in lower_flags and "--length_scale" not in lower_flags:
            cmd.extend(["--length_scale", f"{length_scale:.2f}"])
        if "--noise-scale" not in lower_flags and "--noise_scale" not in lower_flags:
            cmd.extend(["--noise_scale", f"{noise_scale:.2f}"])
        if "--noise-w-scale" not in lower_flags and "--noise_w_scale" not in lower_flags:
            cmd.extend(["--noise_w_scale", f"{noise_w_scale:.2f}"])
        if "--sentence-silence" not in lower_flags and "--sentence_silence" not in lower_flags:
            cmd.extend(["--sentence_silence", f"{sentence_silence:.2f}"])

        cmd.extend(["--output_file", out_path])
        completed = subprocess.run(cmd, input=text, capture_output=True, text=True, timeout=60)

        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "piper failed").strip())

        rendered_path = out_path
        cat_fx_applied = False
        if selected_mode == "cat" and Path(out_path).exists():
            rendered_path, cat_fx_applied = self._apply_cat_timbre(out_path)

        if play and Path(rendered_path).exists():
            self._play_audio(rendered_path)

        command_text = " ".join(cmd)
        if selected_mode == "cat":
            command_text += " | catfx=ffmpeg" if cat_fx_applied else " | catfx=unavailable(ffmpeg-missing)"

        return SpeechSynthesisResult(text=text, backend=self.BACKEND, spoken=play, command=command_text)

    def _apply_voice_override(self, cmd: list[str], voice: Optional[str]) -> None:
        model_and_config = self._resolve_voice_model(voice)
        if not model_and_config:
            return
        model_path, config_path = model_and_config
        self._set_or_append_flag(cmd, {"--model"}, str(model_path), "--model")
        self._set_or_append_flag(cmd, {"--config"}, str(config_path), "--config")

    def _resolve_voice_model(self, voice: Optional[str]) -> Optional[tuple[Path, Path]]:
        raw = (voice or "").strip()
        if not raw:
            return None

        key = raw.lower()

        if key in self._voice_model_map:
            model_path, config_path = self._voice_model_map[key]
            if model_path.exists() and config_path.exists():
                return model_path, config_path
            return None

        model_candidate = Path(raw)
        if not model_candidate.is_absolute():
            model_candidate = self._project_root / model_candidate
        config_candidate = Path(str(model_candidate) + ".json")
        if model_candidate.exists() and config_candidate.exists():
            return model_candidate, config_candidate
        return None

    def _set_or_append_flag(self, cmd: list[str], names: set[str], value: str, default_flag: str) -> None:
        names_lower = {name.lower() for name in names}
        for idx in range(len(cmd) - 1):
            if cmd[idx].lower() in names_lower:
                cmd[idx + 1] = value
                return
        cmd.extend([default_flag, value])

    def _apply_cat_timbre(self, src_path: str) -> tuple[str, bool]:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            logger.warning("PiperSpeechSynthesizer: ffmpeg not found; cat timbre effect unavailable")
            return src_path, False

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False, prefix="nova_catfx_") as tmp:
            target_path = tmp.name

        # Pitch-shift + brighten + significantly slow down for animal-like timbre.
        # atempo=0.65 makes cat voice 65% of normal speed (1.54x slower overall).
        filter_graph = "asetrate=48000*1.32,aresample=48000,atempo=0.65,treble=g=3"
        command = [
            ffmpeg,
            "-y",
            "-i",
            src_path,
            "-filter:a",
            filter_graph,
            target_path,
        ]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=45)
            if completed.returncode != 0:
                logger.warning("PiperSpeechSynthesizer: ffmpeg cat effect failed; using raw output")
                return src_path, False
            return target_path, True
        except Exception as ex:
            logger.warning(f"PiperSpeechSynthesizer: ffmpeg cat effect error -> {ex}")
            return src_path, False

    def _play_audio(self, path: str) -> None:
        system = platform.system().lower()
        if system == "darwin":
            subprocess.run(["afplay", path], check=False)
        elif shutil.which("aplay"):
            subprocess.run(["aplay", path], check=False)
        elif shutil.which("ffplay"):
            subprocess.run(["ffplay", "-nodisp", "-autoexit", path], check=False)

    def _resolve_command_binary(self, binary: str) -> str:
        found = shutil.which(binary)
        if found:
            return found

        # If PATH is missing venv/bin, resolve CLI tools from the active Python env.
        candidate = Path(sys.executable).resolve().parent / binary
        if candidate.exists() and candidate.is_file():
            return str(candidate)
        return ""
