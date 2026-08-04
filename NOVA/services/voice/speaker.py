"""Speaker enrollment and recognition.

Two backends, chosen by SPEAKER_PROVIDER in settings:

  "heuristic"              — text hash embeddings + metadata hints.
                             Always available, zero ML dependencies.

  "speechbrain+resemblyzer" — Resemblyzer (pip install resemblyzer) for
                              real d-vector speaker embeddings from audio.
                              Falls back to heuristic when the package is
                              absent or no audio file is provided.

Public interface is the same for both:
  SpeakerRegistry.enroll(name, samples)  → SpeakerProfile
  SpeakerRecognizer.recognize(text, metadata) → SpeakerRecognitionResult
"""

from __future__ import annotations

import json
import hashlib
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from packages.common import logger

from .models import SpeakerProfile, SpeakerRecognitionResult


MIN_AUDIO_SECONDS = 0.8
MIN_AUDIO_RMS = 0.005


# ---------------------------------------------------------------------------
# Shared registry
# ---------------------------------------------------------------------------

class SpeakerRegistry:
    def __init__(self):
        self._profiles: dict[str, SpeakerProfile] = {}
        self._data_file = Path(__file__).resolve().parents[2] / "data" / "voice_speakers.json"
        self._load()

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _load(self) -> None:
        try:
            if not self._data_file.exists():
                logger.info("SpeakerRegistry: no persisted profile file found", file=str(self._data_file))
                return
            raw = json.loads(self._data_file.read_text(encoding="utf-8"))
            profiles = raw.get("profiles", []) if isinstance(raw, dict) else []
            for row in profiles:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("name") or "").strip()
                embedding = str(row.get("embedding") or "").strip()
                if not name or not embedding:
                    continue
                profile = SpeakerProfile(
                    id=str(row.get("id") or str(uuid.uuid4())),
                    name=name,
                    embedding=embedding,
                    samples=int(row.get("samples") or 0),
                    role="admin" if str(row.get("role") or "user").lower() == "admin" else "user",
                    created_at=str(row.get("created_at") or ""),
                    updated_at=str(row.get("updated_at") or ""),
                )
                self._profiles[name.lower()] = profile
            logger.info(
                "SpeakerRegistry: loaded profiles",
                total=len(self._profiles),
                audio_profiles=sum(1 for p in self._profiles.values() if _is_audio_embedding(p.embedding)),
            )
        except Exception as ex:
            logger.warning(f"SpeakerRegistry load failed: {ex}")

    def _save(self) -> None:
        try:
            self._data_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "profiles": [
                    {
                        "id": p.id,
                        "name": p.name,
                        "embedding": p.embedding,
                        "samples": p.samples,
                        "role": p.role,
                        "created_at": p.created_at,
                        "updated_at": p.updated_at,
                    }
                    for p in self._profiles.values()
                ]
            }
            self._data_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as ex:
            logger.warning(f"SpeakerRegistry save failed: {ex}")

    def enroll(self, name: str, samples: list[str], role: str = "user") -> SpeakerProfile:
        normalized_name = name.strip()
        seed = "|".join(_normalize_text(s) for s in samples if s)
        if not seed:
            seed = normalized_name.lower()
        embedding = hashlib.sha256(seed.encode()).hexdigest()
        existing = self.get(normalized_name)
        now = self._utc_now()
        profile = SpeakerProfile(
            id=existing.id if existing else str(uuid.uuid4()),
            name=normalized_name,
            embedding=embedding,
            samples=len(samples),
            role="admin" if role == "admin" else "user",
            created_at=existing.created_at if existing and existing.created_at else now,
            updated_at=now,
        )
        if profile.role == "admin":
            self._clear_admin_role()
        self._profiles[normalized_name.lower()] = profile
        self._save()
        return profile

    def enroll_audio(self, name: str, audio_paths: list[str], role: str = "user") -> SpeakerProfile:
        """Enroll a speaker from audio files using Resemblyzer when available."""
        logger.info(
            "SpeakerRegistry: enroll_audio requested",
            name=name.strip(),
            audio_paths=len(audio_paths),
            existing_profile=bool(self.get(name.strip())),
        )
        embedding_vec = _compute_resemblyzer_embedding(audio_paths)
        normalized_name = name.strip()
        existing = self.get(normalized_name)
        now = self._utc_now()
        if embedding_vec is not None:
            # Serialize float list to a hex-encoded string for storage in SpeakerProfile.
            embedding_str = _vec_to_hex(embedding_vec)
            backend = "resemblyzer"
        else:
            seed = normalized_name.lower()
            embedding_str = hashlib.sha256(seed.encode()).hexdigest()
            backend = "heuristic"
        profile = SpeakerProfile(
            id=existing.id if existing else str(uuid.uuid4()),
            name=normalized_name,
            embedding=embedding_str,
            samples=len(audio_paths),
            role="admin" if role == "admin" else "user",
            created_at=existing.created_at if existing and existing.created_at else now,
            updated_at=now,
        )
        if profile.role == "admin":
            self._clear_admin_role()
        self._profiles[normalized_name.lower()] = profile
        self._save()
        logger.info(f"SpeakerRegistry: enrolled '{normalized_name}' via {backend}")
        return profile

    def _clear_admin_role(self) -> None:
        for key, profile in list(self._profiles.items()):
            if profile.role == "admin":
                self._profiles[key] = SpeakerProfile(
                    id=profile.id,
                    name=profile.name,
                    embedding=profile.embedding,
                    samples=profile.samples,
                    role="user",
                    created_at=profile.created_at,
                    updated_at=self._utc_now(),
                )

    def set_admin(self, speaker_id: str) -> Optional[SpeakerProfile]:
        target = self.find_by_id(speaker_id)
        if target is None:
            return None
        self._clear_admin_role()
        updated = SpeakerProfile(
            id=target.id,
            name=target.name,
            embedding=target.embedding,
            samples=target.samples,
            role="admin",
            created_at=target.created_at,
            updated_at=self._utc_now(),
        )
        self._profiles[target.name.lower()] = updated
        self._save()
        return updated

    def delete_by_id(self, speaker_id: str) -> Optional[SpeakerProfile]:
        target = self.find_by_id(speaker_id)
        if target is None:
            return None
        self._profiles.pop(target.name.lower(), None)
        self._save()
        logger.info("SpeakerRegistry: deleted speaker profile", speaker_id=speaker_id, name=target.name)
        return target

    def clear_all(self) -> int:
        count = len(self._profiles)
        self._profiles.clear()
        self._save()
        logger.info("SpeakerRegistry: cleared all speaker profiles", removed=count)
        return count

    def find_by_id(self, speaker_id: str) -> Optional[SpeakerProfile]:
        for profile in self._profiles.values():
            if profile.id == speaker_id:
                return profile
        return None

    def get_admin(self) -> Optional[SpeakerProfile]:
        for profile in self._profiles.values():
            if profile.role == "admin":
                return profile
        return None

    def get(self, name: str) -> Optional[SpeakerProfile]:
        return self._profiles.get((name or "").strip().lower())

    def all_profiles(self) -> list[SpeakerProfile]:
        return list(self._profiles.values())

    def has_audio_profiles(self) -> bool:
        return any(_is_audio_embedding(profile.embedding) for profile in self._profiles.values())


# ---------------------------------------------------------------------------
# Heuristic recognizer (text + metadata)
# ---------------------------------------------------------------------------

class SpeakerRecognizer:
    """Text-based recognizer — only trusts explicit identity signals."""

    BACKEND = "heuristic"

    def __init__(self, registry: Optional[SpeakerRegistry] = None):
        self.registry = registry or SpeakerRegistry()

    def recognize(self, text: str, metadata: Optional[dict] = None) -> SpeakerRecognitionResult:
        metadata = metadata or {}
        speaker_hint = (metadata.get("speaker") or "").strip()
        speaker_source = str(metadata.get("speaker_source") or "").strip().lower()
        logger.info(
            "SpeakerRecognizer(heuristic): recognition request",
            has_speaker_hint=bool(speaker_hint),
            speaker_source=speaker_source,
            text_len=len((text or "").strip()),
        )
        if speaker_hint and speaker_source == "verified":
            profile = self.registry.get(speaker_hint)
            if profile:
                logger.info("SpeakerRecognizer(heuristic): accepted verified hint", speaker=profile.name)
                return SpeakerRecognitionResult(
                    speaker=profile.name,
                    role=profile.role,
                    confidence=0.99,
                    recognized=True,
                    backend=self.BACKEND,
                )

        tagged = self._extract_tagged_speaker(text)
        if tagged:
            profile = self.registry.get(tagged)
            if profile:
                logger.info("SpeakerRecognizer(heuristic): accepted tagged speaker", speaker=profile.name)
                return SpeakerRecognitionResult(
                    speaker=profile.name,
                    role=profile.role,
                    confidence=0.96,
                    recognized=True,
                    backend=self.BACKEND,
                )

        logger.info("SpeakerRecognizer(heuristic): no speaker matched")
        return SpeakerRecognitionResult(backend=self.BACKEND)

    def _extract_tagged_speaker(self, text: str) -> str:
        match = re.search(r"\[speaker:(.+?)\]", text or "", flags=re.IGNORECASE)
        return match.group(1).strip() if match else ""


# ---------------------------------------------------------------------------
# Resemblyzer-backed recognizer (real d-vector embeddings)
# ---------------------------------------------------------------------------

class ResemblyzerSpeakerRecognizer(SpeakerRecognizer):
    """
    Speaker recognizer using Resemblyzer d-vector embeddings.

    Audio-file input: computes a d-vector via Resemblyzer and matches
    it against enrolled profiles using cosine similarity.

    Text input or Resemblyzer unavailable: falls through to heuristic.

    Requirements:
        pip install resemblyzer
    """

    BACKEND = "resemblyzer"
    SIMILARITY_THRESHOLD = 0.75
    SINGLE_PROFILE_RELAXED_THRESHOLD = 0.62

    def __init__(
        self,
        registry: Optional[SpeakerRegistry] = None,
        threshold: float = 0.75,
    ):
        super().__init__(registry=registry)
        self.threshold = threshold

    def recognize(self, text: str, metadata: Optional[dict] = None) -> SpeakerRecognitionResult:
        metadata = metadata or {}

        # If an audio_path is passed in metadata, try Resemblyzer.
        audio_path = (metadata.get("audio_path") or "").strip()
        logger.info(
            "SpeakerRecognizer(resemblyzer): recognition request",
            has_audio_path=bool(audio_path),
            audio_path_exists=bool(audio_path and Path(audio_path).exists()),
            enrolled_profiles=len(self.registry.all_profiles()),
            audio_profiles=sum(1 for p in self.registry.all_profiles() if _is_audio_embedding(p.embedding)),
            threshold=float(self.threshold),
        )
        if audio_path and Path(audio_path).exists():
            result = self._recognize_audio(audio_path)
            if result is not None:
                logger.info(
                    "SpeakerRecognizer(resemblyzer): audio recognition result",
                    speaker=result.speaker,
                    confidence=float(result.confidence),
                    recognized=bool(result.recognized),
                    backend=result.backend,
                )
                return result

        # Delegate to heuristic for text-first path.
        result = super().recognize(text, metadata)
        logger.info(
            "SpeakerRecognizer(resemblyzer): fallback to heuristic",
            speaker=result.speaker,
            confidence=float(result.confidence),
            recognized=bool(result.recognized),
        )
        return SpeakerRecognitionResult(
            speaker=result.speaker,
            role=result.role,
            confidence=result.confidence,
            recognized=result.recognized,
            backend=f"resemblyzer/heuristic",
        )

    def _recognize_audio(self, audio_path: str) -> Optional[SpeakerRecognitionResult]:
        quality = assess_audio_sample(audio_path)
        if not quality.get("usable", False):
            logger.info(
                "SpeakerRecognizer(resemblyzer): insufficient audio quality",
                audio_path=audio_path,
                reason=str(quality.get("reason") or "unknown"),
                duration_s=round(float(quality.get("duration_s") or 0.0), 3),
                rms=round(float(quality.get("rms") or 0.0), 6),
            )
            return SpeakerRecognitionResult(backend="resemblyzer/insufficient-audio")

        embedding = _compute_resemblyzer_embedding([audio_path])
        if embedding is None:
            logger.warning("SpeakerRecognizer(resemblyzer): embedding generation returned None", audio_path=audio_path)
            return None

        profiles = self.registry.all_profiles()
        best_name = ""
        best_score = 0.0
        scores: list[tuple[str, float]] = []
        audio_profile_count = 0

        for profile in profiles:
            stored_vec = _hex_to_vec(profile.embedding)
            if stored_vec is None:
                logger.info("SpeakerRecognizer(resemblyzer): skipping non-audio profile", speaker=profile.name)
                continue
            if len(stored_vec) != len(embedding):
                logger.info(
                    "SpeakerRecognizer(resemblyzer): skipping profile due to embedding dimension mismatch",
                    speaker=profile.name,
                    profile_dims=len(stored_vec),
                    input_dims=len(embedding),
                )
                continue
            audio_profile_count += 1
            score = _cosine_similarity(embedding, stored_vec)
            scores.append((profile.name, round(score, 4)))
            if score > best_score:
                best_score = score
                best_name = profile.name

        logger.info(
            "SpeakerRecognizer(resemblyzer): candidate scores",
            scores=scores,
            best_name=best_name,
            best_score=round(best_score, 4),
            threshold=float(self.threshold),
        )

        if best_score >= self.threshold and best_name:
            return SpeakerRecognitionResult(
                speaker=best_name,
                role="user",
                confidence=round(best_score, 3),
                recognized=True,
                backend=self.BACKEND,
            )

        # When only one valid audio profile exists, use a slightly relaxed
        # threshold so normal variation in short utterances does not fail.
        if audio_profile_count == 1 and best_name and best_score >= self.SINGLE_PROFILE_RELAXED_THRESHOLD:
            logger.info(
                "SpeakerRecognizer(resemblyzer): accepted with single-profile relaxed threshold",
                best_name=best_name,
                best_score=round(best_score, 4),
                strict_threshold=float(self.threshold),
                relaxed_threshold=float(self.SINGLE_PROFILE_RELAXED_THRESHOLD),
            )
            return SpeakerRecognitionResult(
                speaker=best_name,
                role="user",
                confidence=round(best_score, 3),
                recognized=True,
                backend=f"{self.BACKEND}/relaxed-single-profile",
            )

        logger.info("SpeakerRecognizer(resemblyzer): no match above threshold", best_score=round(best_score, 4))
        return SpeakerRecognitionResult(backend=self.BACKEND)


# ---------------------------------------------------------------------------
# Resemblyzer embedding helpers
# ---------------------------------------------------------------------------

def _compute_resemblyzer_embedding(audio_paths: list[str]) -> Optional[list[float]]:
    """Return a mean d-vector from audio_paths, or None if unavailable."""
    try:
        from resemblyzer import VoiceEncoder, preprocess_wav  # type: ignore
        import numpy as np

        encoder = VoiceEncoder()
        embeddings = []
        for path in audio_paths:
            p = Path(path)
            if not p.exists():
                logger.warning("Resemblyzer: audio path does not exist", audio_path=path)
                continue
            logger.info("Resemblyzer: processing audio", audio_path=path, size_bytes=p.stat().st_size)
            wav = preprocess_wav(p)
            emb = encoder.embed_utterance(wav)
            embeddings.append(emb)

        if not embeddings:
            return None

        mean_emb = np.mean(embeddings, axis=0)
        logger.info("Resemblyzer: generated mean embedding", vectors=len(embeddings), dimensions=len(mean_emb))
        return mean_emb.tolist()
    except ImportError as ex:
        logger.warning(
            "Resemblyzer: import failed; dependency missing",
            error=str(ex),
            hint="Ensure resemblyzer stack is installed in active venv and setuptools provides pkg_resources",
        )
        return None
    except Exception as ex:
        logger.warning(f"Resemblyzer embedding failed: {ex}")
        return None


def _vec_to_hex(vec: list[float]) -> str:
    """Encode a float list as a compact hex string."""
    import struct
    packed = struct.pack(f"{len(vec)}f", *vec)
    return packed.hex()


def _hex_to_vec(hex_str: str) -> Optional[list[float]]:
    """Decode a float list from hex. Returns None for non-Resemblyzer entries."""
    try:
        import struct
        raw = bytes.fromhex(hex_str)
        count = len(raw) // 4
        if count == 0:
            return None
        return list(struct.unpack(f"{count}f", raw))
    except Exception:
        return None


def _is_audio_embedding(hex_str: str) -> bool:
    vec = _hex_to_vec(hex_str)
    return bool(vec and len(vec) >= 128)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    try:
        import math
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = math.sqrt(sum(x * x for x in a))
        mag_b = math.sqrt(sum(x * x for x in b))
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)
    except Exception:
        return 0.0


def _normalize_text(text: str) -> str:
    return " ".join((text or "").lower().split())


def assess_audio_sample(audio_path: str) -> dict:
    result = {
        "usable": False,
        "reason": "unknown",
        "duration_s": 0.0,
        "rms": 0.0,
    }
    try:
        import numpy as np
        import soundfile as sf

        audio, sample_rate = sf.read(audio_path, always_2d=False)
        samples = np.asarray(audio, dtype=np.float32)
        if samples.ndim > 1:
            samples = samples.mean(axis=1)
        if samples.size == 0 or sample_rate <= 0:
            result["reason"] = "empty_audio"
            return result

        duration_s = float(samples.size) / float(sample_rate)
        rms = float(np.sqrt(np.mean(np.square(samples))))
        result["duration_s"] = duration_s
        result["rms"] = rms

        if duration_s < MIN_AUDIO_SECONDS:
            result["reason"] = "too_short"
            return result
        if rms < MIN_AUDIO_RMS:
            result["reason"] = "too_quiet"
            return result

        result["usable"] = True
        result["reason"] = "ok"
        return result
    except Exception as ex:
        result["reason"] = f"audio_read_error:{ex.__class__.__name__}"
        return result
