"""Tests for the VAD adapter layer (heuristic + Silero with mocked torch)."""

from __future__ import annotations

import sys
from pathlib import Path

from services.voice.vad import VoiceActivityDetector, SileroVoiceActivityDetector


# ---------------------------------------------------------------------------
# Heuristic VAD
# ---------------------------------------------------------------------------

def test_heuristic_vad_empty_string():
    vad = VoiceActivityDetector()
    result = vad.detect("   ")
    assert result.speech_detected is False
    assert result.energy == 0.0
    assert result.backend == "text-vad"


def test_heuristic_vad_short_text():
    vad = VoiceActivityDetector()
    result = vad.detect("hey nova")
    assert result.speech_detected is True
    assert result.energy > 0
    assert result.backend == "text-vad"


def test_heuristic_vad_long_text():
    vad = VoiceActivityDetector()
    result = vad.detect("can you please help me set a reminder for tomorrow morning at nine")
    assert result.speech_detected is True
    assert result.energy == 1.0  # capped at 1.0 for long text
    assert result.confidence == 0.95


# ---------------------------------------------------------------------------
# Silero VAD — text-mode fallback (no torch needed)
# ---------------------------------------------------------------------------

def test_silero_vad_text_mode_falls_through_to_heuristic():
    # Reset class-level cache to simulate fresh state.
    SileroVoiceActivityDetector._available = None
    SileroVoiceActivityDetector._model = None

    vad = SileroVoiceActivityDetector()
    result = vad.detect("hello nova what is the time")
    assert result.speech_detected is True
    assert "heuristic" in result.backend


def test_silero_vad_empty_text_returns_no_speech():
    SileroVoiceActivityDetector._available = None
    vad = SileroVoiceActivityDetector()
    result = vad.detect("   ")
    assert result.speech_detected is False


# ---------------------------------------------------------------------------
# Silero VAD — audio file path with mocked torch
# ---------------------------------------------------------------------------

class _FakeTorch:
    """Minimal torch stub so we can test without installing torch."""

    class hub:
        @staticmethod
        def load(*args, **kwargs):
            def get_timestamps(wav, model, **kw):
                return [{"start": 0, "end": 8000}]

            def read_audio(path, sampling_rate=16000):
                class _Tensor:
                    shape = (1, 16000)
                    def __getitem__(self, item): return self
                return _Tensor()

            utils = (get_timestamps, None, read_audio, None, None)
            model = object()
            return model, utils


def test_silero_vad_audio_file_calls_model(tmp_path):
    """Confirm Silero path is taken for audio files when torch is available."""
    import importlib
    import types

    audio = tmp_path / "speech.wav"
    audio.write_bytes(b"\x00" * 100)

    # Inject fake torch into sys.modules before the class tries to import it.
    fake_torch = _FakeTorch()
    fake_torchaudio = types.ModuleType("torchaudio")
    sys.modules["torch"] = fake_torch
    sys.modules["torchaudio"] = fake_torchaudio

    # Reset class cache so it re-checks availability with fake torch.
    SileroVoiceActivityDetector._available = None
    SileroVoiceActivityDetector._model = None
    SileroVoiceActivityDetector._utils = None

    try:
        vad = SileroVoiceActivityDetector(threshold=0.5)
        result = vad.detect(str(audio))
    finally:
        del sys.modules["torch"]
        del sys.modules["torchaudio"]
        SileroVoiceActivityDetector._available = None
        SileroVoiceActivityDetector._model = None
        SileroVoiceActivityDetector._utils = None

    assert result.speech_detected is True
    assert result.backend == "silero-vad"
    assert result.energy > 0


def test_silero_vad_audio_file_no_torch_falls_back(tmp_path):
    """When torch is absent, audio input should not be treated as speech."""
    audio = tmp_path / "silence.wav"
    audio.write_bytes(b"\x00" * 100)

    SileroVoiceActivityDetector._available = False
    SileroVoiceActivityDetector._model = None

    try:
        vad = SileroVoiceActivityDetector()
        result = vad.detect(str(audio))
    finally:
        SileroVoiceActivityDetector._available = None

    assert result.speech_detected is False
    assert "fallback" in result.backend
