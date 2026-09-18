"""Thinking earcon — a subtle tone played when inference exceeds 800ms.

Prevents dead silence while the LLM is processing, which makes
assistants feel unresponsive.
"""

from __future__ import annotations

import threading
import time

from packages.common import logger


THINKING_DELAY_MS = 800


def _generate_earcon() -> bytes | None:
    """Generate a short, subtle chime as a numpy array, returned as WAV bytes."""
    try:
        import numpy as np
        import io
        import soundfile as sf

        sr = 24000
        duration = 0.3
        t = np.linspace(0, duration, int(sr * duration), dtype=np.float32)
        # Gentle two-tone chime that fades quickly
        tone = 0.08 * np.sin(2 * np.pi * 880 * t) * np.exp(-t * 8)
        tone += 0.05 * np.sin(2 * np.pi * 1320 * t) * np.exp(-t * 10)

        buf = io.BytesIO()
        sf.write(buf, tone, sr, format="WAV")
        return buf.getvalue()
    except Exception:
        return None


_EARCON_AUDIO = None


def _get_earcon_audio():
    global _EARCON_AUDIO
    if _EARCON_AUDIO is None:
        try:
            import numpy as np
            sr = 24000
            duration = 0.3
            t = np.linspace(0, duration, int(sr * duration), dtype=np.float32)
            tone = 0.08 * np.sin(2 * np.pi * 880 * t) * np.exp(-t * 8)
            tone += 0.05 * np.sin(2 * np.pi * 1320 * t) * np.exp(-t * 10)
            _EARCON_AUDIO = (tone, sr)
        except Exception:
            return None
    return _EARCON_AUDIO


def play_thinking_earcon() -> None:
    """Play a brief thinking tone on an independent output stream."""
    result = _get_earcon_audio()
    if result is None:
        return
    audio, sr = result
    try:
        import sounddevice as sd
        with sd.OutputStream(samplerate=sr, channels=1, dtype="float32", latency="high") as output:
            output.write(audio)
    except Exception:
        pass


class ThinkingEarconTimer:
    """Plays a thinking earcon if the callback isn't cancelled within THINKING_DELAY_MS."""

    def __init__(self, delay_ms: int = THINKING_DELAY_MS):
        self._delay = delay_ms / 1000.0
        self._timer: threading.Timer | None = None
        self._lock = threading.RLock()
        self._generation = 0

    def start(self) -> None:
        self.cancel()
        with self._lock:
            generation = self._generation
            self._timer = threading.Timer(self._delay, self._play, args=(generation,))
            self._timer.daemon = True
            self._timer.start()

    def _play(self, generation: int) -> None:
        with self._lock:
            if generation == self._generation:
                play_thinking_earcon()

    def cancel(self) -> None:
        with self._lock:
            self._generation += 1
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
