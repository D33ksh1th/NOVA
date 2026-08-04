"""Voice activity detection for the modular voice pipeline.

Two backends are supported, selected by VAD_PROVIDER in settings:

  "heuristic"   — lightweight text-token analysis. Always available.
                  Used automatically when torch is absent or no audio
                  file is given.

  "silero-vad"  — real Silero VAD model via PyTorch.
                  Requires: torch, torchaudio (pip install torch torchaudio)
                  Falls back to heuristic with a logged warning when torch
                  is not installed or the model cannot be loaded.

Both classes share the same public interface so the pipeline is unaffected.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

from packages.common import logger

from .models import VoiceActivityResult


# ---------------------------------------------------------------------------
# Heuristic (text) VAD — always available
# ---------------------------------------------------------------------------

class VoiceActivityDetector:
    """
    Lightweight text-based VAD.

    When the audio pipeline is text-first (pre-Whisper.cpp wiring), a
    string transcript is the source. We estimate activity from token density.
    """

    BACKEND = "text-vad"

    def detect(self, source: str) -> VoiceActivityResult:
        text = (source or "").strip()
        if not text:
            return VoiceActivityResult(False, confidence=1.0, energy=0.0, backend=self.BACKEND)

        token_count = len(text.split())
        energy = min(1.0, max(0.15, token_count / 12))
        confidence = 0.95 if token_count > 0 else 1.0
        return VoiceActivityResult(True, confidence=confidence, energy=energy, backend=self.BACKEND)


# ---------------------------------------------------------------------------
# Silero VAD — real audio detection with lazy torch dependency
# ---------------------------------------------------------------------------

class SileroVoiceActivityDetector:
    """
    Silero VAD (https://github.com/snakers4/silero-vad).

    For audio files: runs the real Silero model (via torch.hub or a cached
    local model) and returns genuine speech timestamps.

    For text input (source is not an existing file path): falls through to
    the heuristic text detector so the text-first test pipeline still works.

    If torch is unavailable or the model fails to load, the class silently
    degrades to the heuristic backend and logs a one-time warning.
    """

    BACKEND = "silero-vad"
    SAMPLE_RATE = 16000
    _model = None
    _utils = None
    _available: Optional[bool] = None  # None = not yet checked

    def __init__(
        self,
        model_path: str = "",
        threshold: float = 0.5,
        min_speech_duration_ms: int = 250,
        min_silence_duration_ms: int = 100,
    ):
        self.model_path = (model_path or "").strip()
        self.threshold = threshold
        self.min_speech_duration_ms = min_speech_duration_ms
        self.min_silence_duration_ms = min_silence_duration_ms
        self._heuristic = VoiceActivityDetector()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, source: str) -> VoiceActivityResult:
        """
        Detect voice activity.

        If `source` is a path to an audio file and torch is available,
        runs real Silero VAD.  Otherwise falls back to text heuristic.
        """
        if source and Path(source).exists():
            return self._detect_audio(Path(source))

        # Text-first path: delegate to heuristic.
        result = self._heuristic.detect(source)
        return VoiceActivityResult(
            result.speech_detected,
            result.confidence,
            result.energy,
            backend="silero-vad/heuristic",
        )

    # ------------------------------------------------------------------
    # Audio detection via Silero
    # ------------------------------------------------------------------

    def _detect_audio(self, path: Path) -> VoiceActivityResult:
        if not self._ensure_available():
            logger.warning(
                "SileroVAD: torch not available — falling back to heuristic for audio input. "
                "Install torch + torchaudio to enable real VAD."
            )
            return VoiceActivityResult(False, confidence=0.5, energy=0.0, backend="silero-vad/fallback")

        try:
            return self._run_silero(path)
        except Exception as ex:
            logger.error(f"SileroVAD detection failed: {ex} — returning speech=False for safety")
            return VoiceActivityResult(False, confidence=0.5, energy=0.0, backend="silero-vad/error")

    def _run_silero(self, path: Path) -> VoiceActivityResult:
        import torch  # guarded by _ensure_available

        model = self._get_model()
        get_timestamps, _, read_audio, _, _ = self._utils

        wav = read_audio(str(path), sampling_rate=self.SAMPLE_RATE)
        speeches = get_timestamps(
            wav,
            model,
            sampling_rate=self.SAMPLE_RATE,
            threshold=self.threshold,
            min_speech_duration_ms=self.min_speech_duration_ms,
            min_silence_duration_ms=self.min_silence_duration_ms,
        )

        if not speeches:
            return VoiceActivityResult(False, confidence=0.95, energy=0.0, backend=self.BACKEND)

        # Estimate energy from speech ratio.
        total_samples = wav.shape[-1]
        speech_samples = sum(s["end"] - s["start"] for s in speeches)
        energy = min(1.0, speech_samples / max(1, total_samples))
        return VoiceActivityResult(True, confidence=0.92, energy=energy, backend=self.BACKEND)

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _ensure_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import torch  # noqa: F401
            import torchaudio  # noqa: F401
            self.__class__._available = True
        except ImportError:
            self.__class__._available = False
        return self.__class__._available

    def _get_model(self):
        if self.__class__._model is not None:
            return self.__class__._model

        import torch

        if self.model_path and Path(self.model_path).exists():
            logger.info(f"SileroVAD: loading model from local path {self.model_path}")
            model = torch.jit.load(self.model_path)
            model.eval()
        else:
            logger.info("SileroVAD: loading model from torch.hub (snakers4/silero-vad)")
            model, utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                trust_repo=True,
            )
            self.__class__._utils = utils
            self.__class__._model = model
            return model

        # When loading from local .jit file the utils are fetched separately.
        _, utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            trust_repo=True,
        )
        self.__class__._utils = utils
        self.__class__._model = model
        return model
