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
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from packages.common import logger
from packages.config import settings


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
                error="Neural-only talkback is enabled; configure Kokoro or Piper.",
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
                    return SpeechSynthesisResult(text=prepared, backend="say", spoken=True, command=" ".join(cmd))
                return SpeechSynthesisResult(text=prepared, backend="say", spoken=False, command=" ".join(cmd))

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
                    return SpeechSynthesisResult(text=prepared, backend="espeak", spoken=True, command=" ".join(cmd))
                return SpeechSynthesisResult(text=prepared, backend="espeak", spoken=False, command=" ".join(cmd))

            logger.info("SpeechSynthesizer: no local TTS backend found; returning text only")
            return SpeechSynthesisResult(text=prepared, backend="text", spoken=False)
        except Exception as ex:
            logger.error(f"SpeechSynthesizer error -> {ex}")
            return SpeechSynthesisResult(text=prepared, backend="error", spoken=False, error=str(ex))

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
        text = (text or "").strip()
        if not text:
            return ""
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        text = text.replace("|", ", ")
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"([\.!\?])\s*", r"\1  ", text)
        text = re.sub(r"([,;:])\s*", r"\1 ", text)
        # Expand common abbreviations so neural voices pronounce them clearly.
        text = re.sub(r"\bCV\b", "C V", text, flags=re.IGNORECASE)
        text = re.sub(r"\bAPI\b", "A P I", text, flags=re.IGNORECASE)
        text = re.sub(r"\bUI\b", "U I", text, flags=re.IGNORECASE)
        text = re.sub(r"\bSQL\b", "S Q L", text, flags=re.IGNORECASE)
        text = re.sub(r"\bAI\b", "A I", text, flags=re.IGNORECASE)
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
# Kokoro TTS  (neural, CLI-based)
# ---------------------------------------------------------------------------

class KokoroSpeechSynthesizer(SpeechSynthesizer):
    """
    Kokoro neural TTS invoked as a subprocess CLI.

    KOKORO_TTS_COMMAND e.g. "kokoro-tts --voice af_sarah"
    The command receives text on stdin; output file path is appended last.
    Falls back to system TTS when the binary is not found.
    """

    BACKEND = "kokoro"

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
            logger.warning("KokoroSpeechSynthesizer: KOKORO_TTS_COMMAND not configured — falling back to system TTS")
            return super().speak(text, play=play, style=style, rate=rate, pitch=pitch, voice=voice, voice_mode=voice_mode)

        parts = shlex.split(self.tts_command)
        resolved_binary = self._resolve_command_binary(parts[0])
        if not resolved_binary:
            logger.warning(f"KokoroSpeechSynthesizer: binary '{parts[0]}' not found — falling back to system TTS")
            return super().speak(text, play=play, style=style, rate=rate, pitch=pitch, voice=voice, voice_mode=voice_mode)

        parts[0] = resolved_binary

        try:
            return self._run_kokoro(cleaned, command_parts=parts, play=play, style=style)
        except Exception as ex:
            logger.error(f"KokoroSpeechSynthesizer error: {ex} — falling back")
            return super().speak(text, play=play, style=style, rate=rate, pitch=pitch, voice=voice, voice_mode=voice_mode)

    def _run_kokoro(
        self,
        text: str,
        command_parts: list[str],
        play: bool,
        style: Optional[str],
    ) -> SpeechSynthesisResult:
        with tempfile.NamedTemporaryFile(
            suffix=f".{self.output_format}", delete=False, prefix="nova_kokoro_"
        ) as tmp:
            out_path = tmp.name

        cmd = command_parts + [out_path]
        completed = subprocess.run(cmd, input=text, capture_output=True, text=True, timeout=60)

        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "kokoro failed").strip())

        if play and Path(out_path).exists():
            self._play_audio(out_path)

        return SpeechSynthesisResult(text=text, backend=self.BACKEND, spoken=play, command=" ".join(cmd))

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
