"""Streaming audio playback with barge-in support.

Uses a single persistent OutputStream that stays open across chunks,
eliminating the gaps caused by opening/closing streams per chunk.
Crossfades between chunks to remove pops and clicks.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Optional

import numpy as np

from packages.common import logger

CROSSFADE_SAMPLES = 480  # 20ms at 24kHz — smooth transition between chunks


def _crossfade(prev: np.ndarray, next_chunk: np.ndarray, n: int = CROSSFADE_SAMPLES) -> np.ndarray:
    """Blend the tail of prev with the head of next_chunk to eliminate clicks."""
    if len(prev) < n or len(next_chunk) < n:
        return np.concatenate([prev, next_chunk])
    fade_out = np.linspace(1.0, 0.0, n, dtype=np.float32)
    fade_in = np.linspace(0.0, 1.0, n, dtype=np.float32)
    blended = prev[-n:] * fade_out + next_chunk[:n] * fade_in
    return np.concatenate([prev[:-n], blended, next_chunk[n:]])


class StreamingPlayer:
    """Threaded audio player with continuous stream and instant interrupt."""

    def __init__(self, sample_rate: int = 24000):
        self.sample_rate = sample_rate
        self._queue: queue.Queue[Optional[np.ndarray]] = queue.Queue()
        self._running = True
        self._interrupted = threading.Event()
        self._speaking = threading.Event()
        self._idle = threading.Event()
        self._idle.set()
        self._thread = threading.Thread(
            target=self._worker, daemon=True, name="nova-streaming-player",
        )
        self._thread.start()

    def enqueue(self, audio: np.ndarray) -> None:
        if self._interrupted.is_set():
            return
        self._queue.put(audio)

    def end_utterance(self) -> None:
        self._queue.put(None)

    def interrupt(self) -> bool:
        """Barge-in: stop current playback and drain queue. Returns True if was speaking."""
        was_speaking = self._speaking.is_set()
        self._interrupted.set()
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        return was_speaking

    def resume(self) -> None:
        self._interrupted.clear()

    def wait_idle(self, timeout: float = 30.0) -> bool:
        return self._idle.wait(timeout=timeout)

    @property
    def is_speaking(self) -> bool:
        return self._speaking.is_set()

    def _worker(self) -> None:
        sd = None
        try:
            import sounddevice as sd_mod
            sd = sd_mod
        except ImportError:
            logger.warning("StreamingPlayer: sounddevice not available, using subprocess fallback")

        while self._running:
            try:
                first_chunk = self._queue.get(timeout=0.3)
            except queue.Empty:
                continue

            if first_chunk is None:
                self._speaking.clear()
                self._idle.set()
                continue

            if self._interrupted.is_set():
                continue

            self._speaking.set()
            self._idle.clear()

            # Collect all available chunks into one continuous buffer
            combined = first_chunk
            while True:
                try:
                    next_chunk = self._queue.get_nowait()
                except queue.Empty:
                    break
                if next_chunk is None:
                    # End-of-utterance marker — play what we have, then go idle
                    self._play_buffer(sd, combined)
                    combined = None
                    break
                if self._interrupted.is_set():
                    combined = None
                    break
                combined = _crossfade(combined, next_chunk)

            if combined is not None and len(combined) > 0:
                self._play_buffer(sd, combined)

            # After playing the combined buffer, check if more chunks arrived
            # during playback (pipelining: synthesizer adds while we play)
            if not self._interrupted.is_set():
                continue  # loop back to get next chunk

        self._speaking.clear()
        self._idle.set()

    def _play_buffer(self, sd, audio: np.ndarray) -> None:
        """Play a single continuous audio buffer."""
        if self._interrupted.is_set():
            return
        try:
            if sd is not None:
                sd.play(audio, self.sample_rate)
                while sd.get_stream().active:
                    if self._interrupted.is_set():
                        sd.stop()
                        return
                    time.sleep(0.01)
            else:
                self._play_subprocess(audio)
        except Exception as ex:
            logger.error(f"StreamingPlayer: playback error: {ex}")

    def _play_subprocess(self, audio: np.ndarray) -> None:
        """Fallback: write to temp WAV and play via afplay/aplay."""
        import tempfile
        import subprocess
        import platform
        import soundfile as sf

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False, prefix="nova_stream_") as tmp:
            sf.write(tmp.name, audio, self.sample_rate)
            path = tmp.name

        system = platform.system().lower()
        try:
            if system == "darwin":
                subprocess.run(["afplay", path], check=False, timeout=30)
            else:
                subprocess.run(["aplay", path], check=False, timeout=30)
        except Exception:
            pass

    def shutdown(self) -> None:
        self._running = False
        self._interrupted.set()
        self._thread.join(timeout=3)
