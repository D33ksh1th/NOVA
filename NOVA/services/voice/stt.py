"""
Speech-to-text adapters.

This module keeps a text-first fallback while adding a real whisper.cpp audio
path that is configurable through settings.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import tempfile
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
    def __init__(
        self,
        language: str = "en",
        whisper_binary: Optional[str] = None,
        whisper_model: Optional[str] = None,
        whisper_args: Optional[str] = None,
        timeout_sec: int = 120,
    ):
        self.language = language
        self.whisper_binary = (whisper_binary or "").strip()
        self.whisper_model = (whisper_model or "").strip()
        self.whisper_args = shlex.split(whisper_args or "")
        self.timeout_sec = timeout_sec

    def recognize(self, source: Optional[str] = None) -> SpeechRecognitionResult:
        """
        Recognize speech from a transcript string or an audio file path.

        If `source` points to an existing path, run whisper.cpp when configured.
        Otherwise treat the source as already-transcribed text.
        """
        if source is None:
            return SpeechRecognitionResult(text="", backend="none", confidence=0.0)

        if isinstance(source, str) and Path(source).exists():
            return self._recognize_audio_file(Path(source))

        text = self._normalize_text(str(source))
        return SpeechRecognitionResult(text=text, backend="text", confidence=1.0)

    def _recognize_audio_file(self, path: Path) -> SpeechRecognitionResult:
        if not self.whisper_binary:
            logger.warning("SpeechRecognizer: audio file provided but whisper binary is not configured")
            return SpeechRecognitionResult(
                text="",
                backend="audio",
                confidence=0.0,
                error="Whisper.cpp binary is not configured",
            )

        if not self.whisper_model:
            logger.warning("SpeechRecognizer: audio file provided but whisper model is not configured")
            return SpeechRecognitionResult(
                text="",
                backend="audio",
                confidence=0.0,
                error="Whisper.cpp model is not configured",
            )

        try:
            with tempfile.TemporaryDirectory(prefix="nova_whisper_") as tmp_dir:
                output_prefix = str(Path(tmp_dir) / "transcript")

                primary_cmd = self._build_primary_whisper_command(path, output_prefix)
                completed = subprocess.run(
                    primary_cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_sec,
                )

                if completed.returncode != 0:
                    # Backward-compatible fallback for wrapper scripts that accept
                    # "<audio> --language <lang>" style arguments.
                    fallback_cmd = self._build_legacy_whisper_command(path)
                    completed = subprocess.run(
                        fallback_cmd,
                        capture_output=True,
                        text=True,
                        timeout=self.timeout_sec,
                    )

                if completed.returncode != 0:
                    error = self._normalize_text(completed.stderr or completed.stdout or "STT command failed")
                    logger.error(f"SpeechRecognizer whisper.cpp failed -> {error}")
                    return SpeechRecognitionResult(text="", backend="whisper.cpp", confidence=0.0, error=error)

                file_text = self._read_output_text_file(output_prefix)
                stdout_text = self._extract_transcript(completed.stdout)
                transcript = self._normalize_text(file_text or stdout_text)

                if not transcript:
                    return SpeechRecognitionResult(
                        text="",
                        backend="whisper.cpp",
                        confidence=0.0,
                        error="Whisper.cpp produced no transcript",
                    )

                return SpeechRecognitionResult(text=transcript, backend="whisper.cpp", confidence=0.9)

        except Exception as ex:
            logger.error(f"SpeechRecognizer error -> {ex}")
            return SpeechRecognitionResult(text="", backend="whisper.cpp", confidence=0.0, error=str(ex))

    def _build_primary_whisper_command(self, path: Path, output_prefix: str) -> list[str]:
        return [
            self.whisper_binary,
            "-m",
            self.whisper_model,
            "-f",
            str(path),
            "-l",
            self.language,
            "-otxt",
            "-of",
            output_prefix,
            *self.whisper_args,
        ]

    def _build_legacy_whisper_command(self, path: Path) -> list[str]:
        return [
            self.whisper_binary,
            str(path),
            "--language",
            self.language,
            *self.whisper_args,
        ]

    def _read_output_text_file(self, output_prefix: str) -> str:
        text_path = Path(f"{output_prefix}.txt")
        if not text_path.exists():
            return ""
        try:
            return text_path.read_text(encoding="utf-8")
        except Exception:
            return ""

    def _extract_transcript(self, stdout: str) -> str:
        cleaned = stdout or ""
        cleaned = re.sub(r"\[[^\]]*-->[^\]]*\]", " ", cleaned)
        cleaned = re.sub(r"\[[0-9:.]+\]", " ", cleaned)
        return cleaned

    def _normalize_text(self, text: str) -> str:
        return " ".join((text or "").split()).strip()
