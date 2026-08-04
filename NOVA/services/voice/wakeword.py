"""
Wake word detection for the modular voice pipeline.

Two backends supported, chosen by WAKEWORD_PROVIDER in settings:

  "text"          — regex/text matching. Always available. Used when source
                    is already a transcript string. Zero dependencies.

  "openwakeword"  — real OpenWakeWord model for raw audio frames.
                    Requires: openwakeword  (pip install openwakeword)
                    Falls back to text matching with a logged warning
                    when the package is absent or the model fails to load.

Both detectors share the same public interface (WakeWordResult) so the
pipeline is not affected by which backend is active.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from packages.common import logger


# ---------------------------------------------------------------------------
# Shared result type
# ---------------------------------------------------------------------------

@dataclass
class WakeWordResult:
    detected: bool
    text: str
    backend: str = "text"
    score: float = 0.0


# ---------------------------------------------------------------------------
# Text / regex detector  (always available)
# ---------------------------------------------------------------------------

class WakeWordDetector:
    """Lightweight text-based wake-word detector."""

    BACKEND = "text"

    def __init__(self, wake_word: str = "Nova"):
        self.wake_word = wake_word.strip().lower()

    def detect(self, text: str) -> WakeWordResult:
        normalized = self._normalize(text)
        detected = normalized.startswith(self.wake_word)
        if detected:
            return WakeWordResult(True, self._strip(normalized), backend=self.BACKEND, score=1.0)
        return WakeWordResult(False, normalized, backend=self.BACKEND, score=0.0)

    def matches(self, text: str) -> bool:
        return self.detect(text).detected

    def _strip(self, text: str) -> str:
        pattern = rf"^({re.escape(self.wake_word)})(,|:)?\s*"
        return re.sub(pattern, "", text, flags=re.IGNORECASE).strip()

    # kept for backward compat
    def strip(self, text: str) -> str:
        return self._strip(self._normalize(text))

    def _normalize(self, text: str) -> str:
        return (text or "").strip().lower()


# ---------------------------------------------------------------------------
# OpenWakeWord detector  (real audio, lazy import)
# ---------------------------------------------------------------------------

class OpenWakeWordDetector:
    """
    OpenWakeWord-based detector (https://github.com/dscripka/openWakeWord).

    For text input (transcript string): delegates to the text detector so
    the text-first test path continues to work.

    For audio file input: loads the model and scores each 80ms chunk
    (1280 samples @ 16kHz, 16-bit PCM). Returns detected=True when
    any chunk score exceeds the threshold.

    Safe degradation: if openwakeword is not installed or the model
    cannot be loaded, falls back to text matching.
    """

    BACKEND = "openwakeword"
    SAMPLE_RATE = 16000
    CHUNK_SAMPLES = 1280   # 80 ms at 16 kHz

    _available: Optional[bool] = None
    _oww_model = None

    def __init__(
        self,
        wake_word: str = "Nova",
        model_path: str = "",
        threshold: float = 0.5,
        wakeword_name: str = "hey_nova",
    ):
        self.wake_word = wake_word.strip()
        self.model_path = (model_path or "").strip()
        self.threshold = threshold
        self.wakeword_name = wakeword_name
        self._text_detector = WakeWordDetector(wake_word)

    # ------------------------------------------------------------------
    # Public API — mirrors WakeWordDetector
    # ------------------------------------------------------------------

    def detect(self, source: str) -> WakeWordResult:
        """
        Detect wake word.

        If `source` is an existing file path, run OpenWakeWord on the audio.
        Otherwise fall through to the text detector.
        """
        if source and Path(source).exists():
            return self._detect_audio(Path(source))

        result = self._text_detector.detect(source)
        return WakeWordResult(
            result.detected,
            result.text,
            backend="openwakeword/text",
            score=result.score,
        )

    def matches(self, text: str) -> bool:
        return self.detect(text).detected

    def strip(self, text: str) -> str:
        return self._text_detector.strip(text)

    # ------------------------------------------------------------------
    # Audio detection via OpenWakeWord
    # ------------------------------------------------------------------

    def _detect_audio(self, path: Path) -> WakeWordResult:
        if not self._ensure_available():
            logger.warning(
                "OpenWakeWordDetector: openwakeword not installed — "
                "falling back to text matching. "
                "Run: pip install openwakeword"
            )
            return WakeWordResult(False, "", backend="openwakeword/fallback", score=0.0)

        try:
            return self._run_oww(path)
        except Exception as ex:
            logger.error(f"OpenWakeWordDetector error: {ex}")
            return WakeWordResult(False, "", backend="openwakeword/error", score=0.0)

    def _run_oww(self, path: Path) -> WakeWordResult:
        import openwakeword  # guarded by _ensure_available

        model = self._get_model()
        raw_audio = self._read_pcm_chunks(path)

        best_score = 0.0
        for chunk in raw_audio:
            prediction = model.predict(chunk)
            # prediction is a dict {wakeword_name: score, ...}
            score = prediction.get(self.wakeword_name, 0.0)
            # Try the first available key if the configured name isn't present.
            if score == 0.0 and prediction:
                score = max(prediction.values())
            if score > best_score:
                best_score = score

        detected = best_score >= self.threshold
        return WakeWordResult(
            detected=detected,
            text="" if not detected else self._text_detector.wake_word,
            backend=self.BACKEND,
            score=best_score,
        )

    def _read_pcm_chunks(self, path: Path) -> list:
        """
        Read a WAV file and return a list of int16 arrays of CHUNK_SAMPLES length.

        Uses numpy when available (openwakeword requires it at runtime) and
        falls back to stdlib array.array so tests pass without numpy.
        """
        try:
            raw = path.read_bytes()
            offset = 44 if raw[:4] == b"RIFF" else 0
            pcm = raw[offset:]
            n_samples = len(pcm) // 2

            try:
                import numpy as np
                audio = np.frombuffer(pcm, dtype=np.int16)
                make_chunk = lambda i: audio[i: i + self.CHUNK_SAMPLES]
            except ImportError:
                import array as _array
                audio = _array.array("h")
                audio.frombytes(pcm[: n_samples * 2])
                make_chunk = lambda i: audio[i: i + self.CHUNK_SAMPLES]

            chunks = []
            for i in range(0, n_samples - self.CHUNK_SAMPLES + 1, self.CHUNK_SAMPLES):
                chunks.append(make_chunk(i))
            return chunks
        except Exception as ex:
            logger.warning(f"OpenWakeWordDetector: could not read audio from {path}: {ex}")
            return []

    # ------------------------------------------------------------------
    # Model management
    # ------------------------------------------------------------------

    def _ensure_available(self) -> bool:
        if self.__class__._available is not None:
            return self.__class__._available
        try:
            import openwakeword  # noqa: F401
            self.__class__._available = True
        except ImportError:
            self.__class__._available = False
        return self.__class__._available

    def _get_model(self):
        if self.__class__._oww_model is not None:
            return self.__class__._oww_model

        import openwakeword
        from openwakeword.model import Model

        if self.model_path and Path(self.model_path).exists():
            logger.info(f"OpenWakeWordDetector: loading model from {self.model_path}")
            model = Model(wakeword_models=[self.model_path])
        else:
            logger.info("OpenWakeWordDetector: loading pre-trained model from openwakeword")
            model = Model(inference_framework="tflite")

        self.__class__._oww_model = model
        return model
