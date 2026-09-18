from __future__ import annotations

import math
from pathlib import Path

from services.voice.models import SpeakerProfile
from services.voice.speaker import ResemblyzerSpeakerRecognizer, _vec_to_hex


class _StubRegistry:
    def __init__(self, profiles: list[SpeakerProfile]):
        self._profiles = profiles

    def all_profiles(self) -> list[SpeakerProfile]:
        return list(self._profiles)

    def get(self, name: str):
        target = (name or "").strip().lower()
        for profile in self._profiles:
            if profile.name.lower() == target:
                return profile
        return None


def _unit_vec_with_cosine(cosine: float, dims: int = 256) -> list[float]:
    vec = [0.0] * dims
    vec[0] = cosine
    vec[1] = math.sqrt(max(0.0, 1.0 - cosine * cosine))
    return vec


def _audio_profile(name: str, vec: list[float]) -> SpeakerProfile:
    return SpeakerProfile(
        id=f"id-{name}",
        name=name,
        embedding=_vec_to_hex(vec),
        samples=4,
        role="user",
    )


def test_resemblyzer_recognizes_strict_match(monkeypatch, tmp_path: Path):
    enrolled = [1.0] + [0.0] * 255
    profile = _audio_profile("Dikshit", enrolled)
    recognizer = ResemblyzerSpeakerRecognizer(registry=_StubRegistry([profile]), threshold=0.8)

    monkeypatch.setattr(
        "services.voice.speaker._compute_resemblyzer_embedding",
        lambda _paths: enrolled,
    )
    monkeypatch.setattr(
        "services.voice.speaker.assess_audio_sample",
        lambda _path: {"usable": True, "reason": "ok", "duration_s": 1.4, "rms": 0.02},
    )

    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"fake")

    result = recognizer.recognize("hello", {"audio_path": str(audio_path)})

    assert result.recognized is True
    assert result.speaker == "Dikshit"
    assert result.backend == "resemblyzer"


def test_resemblyzer_single_profile_uses_relaxed_threshold(monkeypatch, tmp_path: Path):
    enrolled = [1.0] + [0.0] * 255
    spoken = _unit_vec_with_cosine(0.66)
    profile = _audio_profile("Dikshit", enrolled)
    recognizer = ResemblyzerSpeakerRecognizer(registry=_StubRegistry([profile]), threshold=0.8)

    monkeypatch.setattr(
        "services.voice.speaker._compute_resemblyzer_embedding",
        lambda _paths: spoken,
    )
    monkeypatch.setattr(
        "services.voice.speaker.assess_audio_sample",
        lambda _path: {"usable": True, "reason": "ok", "duration_s": 1.4, "rms": 0.02},
    )

    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"fake")

    result = recognizer.recognize("hello", {"audio_path": str(audio_path)})

    assert result.recognized is True
    assert result.speaker == "Dikshit"
    assert result.backend == "resemblyzer/relaxed-single-profile"


def test_resemblyzer_multi_profile_does_not_use_relaxed_threshold(monkeypatch, tmp_path: Path):
    profile_a = _audio_profile("Dikshit", [1.0] + [0.0] * 255)
    profile_b = _audio_profile("Other", [0.0, 1.0] + [0.0] * 254)
    spoken = _unit_vec_with_cosine(0.66)
    recognizer = ResemblyzerSpeakerRecognizer(registry=_StubRegistry([profile_a, profile_b]), threshold=0.8)

    monkeypatch.setattr(
        "services.voice.speaker._compute_resemblyzer_embedding",
        lambda _paths: spoken,
    )
    monkeypatch.setattr(
        "services.voice.speaker.assess_audio_sample",
        lambda _path: {"usable": True, "reason": "ok", "duration_s": 1.4, "rms": 0.02},
    )

    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"fake")

    result = recognizer.recognize("hello", {"audio_path": str(audio_path)})

    assert result.recognized is False
    assert result.speaker == "unknown"


def test_resemblyzer_rejects_insufficient_audio(monkeypatch, tmp_path: Path):
    profile = _audio_profile("Dikshit", [1.0] + [0.0] * 255)
    recognizer = ResemblyzerSpeakerRecognizer(registry=_StubRegistry([profile]), threshold=0.8)

    monkeypatch.setattr(
        "services.voice.speaker.assess_audio_sample",
        lambda _path: {"usable": False, "reason": "too_quiet", "duration_s": 0.9, "rms": 0.001},
    )

    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"fake")

    result = recognizer.recognize("hello", {"audio_path": str(audio_path)})

    assert result.recognized is False
    assert result.backend == "resemblyzer/insufficient-audio"
