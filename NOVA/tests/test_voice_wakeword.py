"""Tests for wake-word detection — text and OpenWakeWord paths."""
from __future__ import annotations

import sys
import types
import tempfile
from pathlib import Path
import struct

import pytest

from services.voice.wakeword import WakeWordDetector, OpenWakeWordDetector


# -------------------------------------------------------------------------
# Text detector
# -------------------------------------------------------------------------

def test_text_detector_detects_nova_prefix():
    d = WakeWordDetector("Nova")
    r = d.detect("Nova what time is it")
    assert r.detected is True
    assert "nova" not in r.text.lower()
    assert r.backend == "text"


def test_text_detector_no_wake_word():
    d = WakeWordDetector("Nova")
    r = d.detect("what time is it")
    assert r.detected is False
    assert r.score == 0.0


def test_text_detector_strip_removes_wake_word():
    d = WakeWordDetector("Nova")
    assert d.strip("nova, play music") == "play music"


@pytest.mark.parametrize("detector_type", [WakeWordDetector, OpenWakeWordDetector])
@pytest.mark.parametrize("prefix", ["Lumi", "Hey Lumi", "Hi Lumi", "Hello Lumi", "Okay Lumi", "HeyLumi"])
def test_lumi_alias_detects_and_strips_commands(detector_type, prefix):
    detector = detector_type("Nova")
    result = detector.detect(f"{prefix}, what time is it?")
    assert result.detected is True
    assert result.text == "what time is it?"
    assert detector.strip(f"{prefix}!") == ""


@pytest.mark.parametrize("text", ["luminous sky", "Hey luminosity", "tell me about Lumi", "volume up"])
def test_lumi_alias_rejects_unrelated_transcripts(text):
    detector = WakeWordDetector("Nova")
    assert detector.matches(text) is False
    assert detector.strip(text) == text.lower()


def test_lumi_alias_does_not_override_custom_wake_word():
    detector = WakeWordDetector("Computer")
    assert detector.matches("Lumi play music") is False
    assert detector.matches("Hey Computer play music") is True


# -------------------------------------------------------------------------
# OpenWakeWord — text-mode fallback
# -------------------------------------------------------------------------

def _reset_oww():
    OpenWakeWordDetector._available = None
    OpenWakeWordDetector._oww_model = None


def test_oww_text_mode_detects_wake_word():
    _reset_oww()
    d = OpenWakeWordDetector("Nova")
    r = d.detect("nova turn on lights")
    assert r.detected is True
    assert "openwakeword/text" in r.backend


def test_oww_text_mode_no_wake_word():
    _reset_oww()
    d = OpenWakeWordDetector("Nova")
    r = d.detect("play some music")
    assert r.detected is False


# -------------------------------------------------------------------------
# OpenWakeWord — audio file with mocked openwakeword
# -------------------------------------------------------------------------

def _make_wav(path: Path, n_samples: int = 2560):
    """Write a minimal 16-bit PCM WAV file."""
    data_bytes = b'\x10\x00' * n_samples
    with open(path, 'wb') as f:
        # RIFF header
        f.write(b'RIFF')
        f.write(struct.pack('<I', 36 + len(data_bytes)))
        f.write(b'WAVE')
        f.write(b'fmt ')
        f.write(struct.pack('<IHHIIHH', 16, 1, 1, 16000, 32000, 2, 16))
        f.write(b'data')
        f.write(struct.pack('<I', len(data_bytes)))
        f.write(data_bytes)


class _FakeModel:
    def predict(self, chunk):
        return {"hey_nova": 0.9}


class _FakeOWW:
    class model:
        class Model:
            def __init__(self, **kwargs): pass
            def predict(self, chunk): return {"hey_nova": 0.9}


def test_oww_audio_detects_with_mocked_openwakeword(tmp_path):
    import numpy as np

    audio = tmp_path / "speech.wav"
    _make_wav(audio)

    fake_oww_module = types.ModuleType("openwakeword")
    fake_model_module = types.ModuleType("openwakeword.model")
    fake_model_module.Model = _FakeOWW.model.Model
    sys.modules["openwakeword"] = fake_oww_module
    sys.modules["openwakeword.model"] = fake_model_module

    _reset_oww()
    OpenWakeWordDetector._available = True

    try:
        d = OpenWakeWordDetector("Nova", threshold=0.5, wakeword_name="hey_nova")
        d.__class__._oww_model = _FakeModel()
        r = d.detect(str(audio))
    finally:
        del sys.modules["openwakeword"]
        del sys.modules["openwakeword.model"]
        _reset_oww()

    assert r.detected is True
    assert r.backend == "openwakeword"
    assert r.score >= 0.5


def test_oww_audio_falls_back_when_package_missing(tmp_path):
    audio = tmp_path / "audio.wav"
    _make_wav(audio)

    _reset_oww()
    OpenWakeWordDetector._available = False

    try:
        d = OpenWakeWordDetector("Nova")
        r = d.detect(str(audio))
    finally:
        _reset_oww()

    assert r.detected is False
    assert "fallback" in r.backend


# -------------------------------------------------------------------------
# Factory creates OpenWakeWordDetector for openwakeword provider
# -------------------------------------------------------------------------

def test_factory_creates_oww_detector():
    from services.voice.factory import VoiceComponentFactory
    factory = VoiceComponentFactory()
    wakeword = factory.create_wakeword()
    assert isinstance(wakeword, OpenWakeWordDetector)
