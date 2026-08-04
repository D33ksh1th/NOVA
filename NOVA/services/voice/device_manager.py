"""Audio backend and device capability helpers."""

from __future__ import annotations

import platform
import shutil


class VoiceDeviceManager:
    def status(self) -> dict:
        system = platform.system().lower()
        return {
            "platform": system,
            "tts_backends": {
                "say": bool(shutil.which("say")) if system == "darwin" else False,
                "espeak": bool(shutil.which("espeak")),
            },
            "audio_backends": {
                "afplay": bool(shutil.which("afplay")) if system == "darwin" else False,
                "ffplay": bool(shutil.which("ffplay")),
            },
        }
