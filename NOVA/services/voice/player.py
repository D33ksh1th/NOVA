"""
Audio player helpers.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from packages.common import logger


@dataclass
class PlaybackResult:
    played: bool
    backend: str = "none"
    error: str = ""


class VoicePlayer:
    def play(self, audio_path: Optional[str]) -> PlaybackResult:
        if not audio_path:
            return PlaybackResult(played=False, backend="none")

        path = Path(audio_path)
        if not path.exists():
            return PlaybackResult(played=False, backend="none", error=f"Missing audio file: {audio_path}")

        system = platform.system().lower()
        try:
            if system == "darwin" and shutil.which("afplay"):
                subprocess.run(["afplay", str(path)], check=True)
                return PlaybackResult(played=True, backend="afplay")

            if shutil.which("ffplay"):
                subprocess.run(["ffplay", "-nodisp", "-autoexit", str(path)], check=True)
                return PlaybackResult(played=True, backend="ffplay")

            logger.info("VoicePlayer: no audio backend found")
            return PlaybackResult(played=False, backend="text")
        except Exception as ex:
            logger.error(f"VoicePlayer error -> {ex}")
            return PlaybackResult(played=False, backend="error", error=str(ex))
