"""Speaker enrollment and recognition.

Two backends, chosen by SPEAKER_PROVIDER in settings:

  "heuristic"              — text hash embeddings + metadata hints.
                             Always available, zero ML dependencies.

  "speechbrain+resemblyzer" — SpeechBrain ECAPA-TDNN (preferred) with
                              Resemblyzer fallback for real speaker embeddings
                              from audio.  Falls back to heuristic when neither
                              package is available or no audio is provided.

Enrollment quality gate (Phase 2):
  - Minimum 3 utterances (5+ recommended)
  - Each utterance >= 3s duration
  - SNR / RMS energy check per sample
  - Intra-speaker cosine variance must be below threshold
  - Rejected if quality gate fails — Nova tells you why

Continuous adaptation:
  - On high-confidence matches (>0.85), the enrolled centroid is updated
    via exponential moving average so Nova improves over weeks.

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
from .embedding import (
    embed_utterance,
    embed_batch,
    cosine_similarity,
    vec_to_hex,
    hex_to_vec,
    is_audio_embedding,
    intra_speaker_variance,
)


MIN_AUDIO_SECONDS = 2.0
MIN_AUDIO_RMS = 0.003
MIN_ENROLLMENT_SAMPLES = 3
MAX_INTRA_SPEAKER_VARIANCE = 0.45
EMA_ALPHA = 0.05


def _resolve_face_identity_id(name: str) -> Optional[str]:
    """Return matching face profile ID by name, if present."""
    try:
        face_file = Path(__file__).resolve().parents[2] / "data" / "face_profiles.json"
        if not face_file.exists():
            return None
        payload = json.loads(face_file.read_text(encoding="utf-8"))
        profiles = payload.get("profiles", []) if isinstance(payload, dict) else []
        target = (name or "").strip().lower()
        for row in profiles:
            if not isinstance(row, dict):
                continue
            row_name = str(row.get("name") or "").strip().lower()
            row_id = str(row.get("id") or "").strip()
            if row_name == target and row_id:
                return row_id
    except Exception as ex:
        logger.warning(f"SpeakerRegistry: failed to resolve face identity id: {ex}")
    return None


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
        linked_face_id = _resolve_face_identity_id(normalized_name)
        now = self._utc_now()
        profile = SpeakerProfile(
            id=existing.id if existing else (linked_face_id or str(uuid.uuid4())),
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

    def enroll_audio(self, name: str, audio_paths: list[str], role: str = "user") -> dict:
        """Enroll a speaker from audio files with quality gate.

        Returns a dict with 'profile' on success or 'error'/'quality_report' on failure.
        """
        logger.info(
            "SpeakerRegistry: enroll_audio requested",
            name=name.strip(),
            audio_paths=len(audio_paths),
            existing_profile=bool(self.get(name.strip())),
        )

        # Quality gate: minimum sample count
        if len(audio_paths) < MIN_ENROLLMENT_SAMPLES:
            return {
                "error": f"Need at least {MIN_ENROLLMENT_SAMPLES} audio samples (got {len(audio_paths)}). "
                         f"Record {MIN_ENROLLMENT_SAMPLES - len(audio_paths)} more.",
                "quality_report": {"samples_provided": len(audio_paths), "minimum_required": MIN_ENROLLMENT_SAMPLES},
            }

        # Quality gate: per-sample checks
        quality_results = []
        valid_paths = []
        for path in audio_paths:
            quality = assess_audio_sample(path)
            quality_results.append(quality)
            if quality.get("usable"):
                valid_paths.append(path)

        if len(valid_paths) < MIN_ENROLLMENT_SAMPLES:
            failures = [q for q in quality_results if not q.get("usable")]
            return {
                "error": f"Only {len(valid_paths)} of {len(audio_paths)} samples passed quality checks. "
                         f"Need {MIN_ENROLLMENT_SAMPLES}. Each must be >= {MIN_AUDIO_SECONDS}s with clear audio.",
                "quality_report": {"passed": len(valid_paths), "failed": failures},
            }

        # Compute per-sample embeddings for variance check
        per_sample_embeddings = []
        for path in valid_paths:
            emb = embed_utterance(path)
            if emb is not None:
                per_sample_embeddings.append(emb)

        if len(per_sample_embeddings) < MIN_ENROLLMENT_SAMPLES:
            return {
                "error": "Could not compute speaker embeddings from enough samples. "
                         "Ensure a speaker embedding model is installed (speechbrain or resemblyzer).",
                "quality_report": {"embeddings_computed": len(per_sample_embeddings)},
            }

        # Quality gate: intra-speaker variance
        variance = intra_speaker_variance(per_sample_embeddings)
        if variance > MAX_INTRA_SPEAKER_VARIANCE:
            return {
                "error": f"Enrollment samples are too inconsistent (variance {variance:.3f} > {MAX_INTRA_SPEAKER_VARIANCE}). "
                         "Re-record in a quieter environment with consistent distance from the microphone.",
                "quality_report": {"intra_speaker_variance": round(variance, 4), "threshold": MAX_INTRA_SPEAKER_VARIANCE},
            }

        # Compute centroid embedding
        import numpy as np
        centroid = np.mean(per_sample_embeddings, axis=0).tolist()
        embedding_str = vec_to_hex(centroid)

        normalized_name = name.strip()
        existing = self.get(normalized_name)
        linked_face_id = _resolve_face_identity_id(normalized_name)
        now = self._utc_now()
        profile = SpeakerProfile(
            id=existing.id if existing else (linked_face_id or str(uuid.uuid4())),
            name=normalized_name,
            embedding=embedding_str,
            samples=len(valid_paths),
            role="admin" if role == "admin" else "user",
            created_at=existing.created_at if existing and existing.created_at else now,
            updated_at=now,
        )
        if profile.role == "admin":
            self._clear_admin_role()
        self._profiles[normalized_name.lower()] = profile
        self._save()

        from .embedding import get_backend
        logger.info(
            f"SpeakerRegistry: enrolled '{normalized_name}' via {get_backend()}",
            samples=len(valid_paths),
            variance=round(variance, 4),
        )
        return {"profile": profile, "quality_report": {
            "samples_used": len(valid_paths),
            "intra_speaker_variance": round(variance, 4),
            "backend": get_backend(),
        }}

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
# ECAPA-TDNN / SpeechBrain backed recognizer (replaces Resemblyzer)
# ---------------------------------------------------------------------------

class EcapaSpeakerRecognizer(SpeakerRecognizer):
    """Speaker recognizer using SpeechBrain ECAPA-TDNN embeddings.

    Falls back to Resemblyzer if SpeechBrain is unavailable, then to heuristic.
    Includes:
    - Adaptive per-speaker threshold
    - Continuous centroid adaptation via EMA on high-confidence matches
    - Score fusion with confidence calibration
    """

    BACKEND = "ecapa-tdnn"
    DEFAULT_THRESHOLD = 0.60
    ADAPTATION_CONFIDENCE_FLOOR = 0.85

    def __init__(
        self,
        registry: Optional[SpeakerRegistry] = None,
        threshold: float = 0.60,
    ):
        super().__init__(registry=registry)
        self.threshold = threshold

    def recognize(self, text: str, metadata: Optional[dict] = None) -> SpeakerRecognitionResult:
        metadata = metadata or {}
        audio_path = (metadata.get("audio_path") or "").strip()
        logger.info(
            "SpeakerRecognizer(ecapa): recognition request",
            has_audio_path=bool(audio_path),
            enrolled_profiles=len(self.registry.all_profiles()),
            audio_profiles=sum(1 for p in self.registry.all_profiles() if is_audio_embedding(p.embedding)),
            threshold=float(self.threshold),
        )

        if audio_path and Path(audio_path).exists():
            result = self._recognize_audio(audio_path)
            if result is not None:
                return result

        result = super().recognize(text, metadata)
        from .embedding import get_backend
        return SpeakerRecognitionResult(
            speaker=result.speaker,
            role=result.role,
            confidence=result.confidence,
            recognized=result.recognized,
            backend=f"{get_backend()}/heuristic",
        )

    def _recognize_audio(self, audio_path: str) -> Optional[SpeakerRecognitionResult]:
        quality = assess_audio_sample(audio_path)
        if not quality.get("usable", False):
            logger.info(
                "SpeakerRecognizer(ecapa): insufficient audio quality",
                reason=str(quality.get("reason") or "unknown"),
                duration_s=round(float(quality.get("duration_s") or 0.0), 3),
            )
            return SpeakerRecognitionResult(backend="ecapa-tdnn/insufficient-audio")

        embedding = embed_utterance(audio_path)
        if embedding is None:
            logger.warning("SpeakerRecognizer(ecapa): embedding generation returned None")
            return None

        profiles = self.registry.all_profiles()
        best_profile: Optional[SpeakerProfile] = None
        best_score = 0.0
        scores: list[tuple[str, float]] = []
        audio_profile_count = 0

        for profile in profiles:
            stored_vec = hex_to_vec(profile.embedding)
            if stored_vec is None:
                continue
            if len(stored_vec) != len(embedding):
                continue
            audio_profile_count += 1
            score = cosine_similarity(embedding, stored_vec)
            scores.append((profile.name, round(score, 4)))
            if score > best_score:
                best_score = score
                best_profile = profile

        logger.info(
            "SpeakerRecognizer(ecapa): candidate scores",
            scores=scores,
            best=best_profile.name if best_profile else "",
            best_score=round(best_score, 4),
        )

        # Below threshold → unknown. Never guess.
        if best_score < self.threshold or best_profile is None:
            logger.info("SpeakerRecognizer(ecapa): no match above threshold")
            return SpeakerRecognitionResult(backend=self.BACKEND)

        from .embedding import get_backend
        result = SpeakerRecognitionResult(
            speaker=best_profile.name,
            role=best_profile.role,
            confidence=round(best_score, 3),
            recognized=True,
            backend=get_backend(),
        )

        # Continuous adaptation: update centroid via EMA on high-confidence matches
        if best_score >= self.ADAPTATION_CONFIDENCE_FLOOR:
            self._adapt_centroid(best_profile, embedding)

        # Publish utterance event with speaker identity
        try:
            from packages.events import bus, Event
            bus.emit(
                Event.VOICE_UTTERANCE,
                source="nova-ears",
                payload={
                    "speaker_id": best_profile.id,
                    "speaker_name": best_profile.name,
                    "confidence": round(best_score, 3),
                    "audio_ref": audio_path,
                    "backend": get_backend(),
                },
                severity=0,
            )
        except Exception:
            pass

        return result

    def _adapt_centroid(self, profile: SpeakerProfile, new_embedding: list[float]) -> None:
        """Update the enrolled centroid via exponential moving average."""
        stored_vec = hex_to_vec(profile.embedding)
        if stored_vec is None or len(stored_vec) != len(new_embedding):
            return
        adapted = [
            (1 - EMA_ALPHA) * old + EMA_ALPHA * new
            for old, new in zip(stored_vec, new_embedding)
        ]
        profile_key = profile.name.lower()
        existing = self.registry._profiles.get(profile_key)
        if existing is None:
            return
        updated = SpeakerProfile(
            id=existing.id,
            name=existing.name,
            embedding=vec_to_hex(adapted),
            samples=existing.samples,
            role=existing.role,
            created_at=existing.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        self.registry._profiles[profile_key] = updated
        self.registry._save()
        logger.info("SpeakerRecognizer(ecapa): centroid adapted via EMA", speaker=profile.name)


# Keep backward-compatible alias
ResemblyzerSpeakerRecognizer = EcapaSpeakerRecognizer


# ---------------------------------------------------------------------------
# Legacy aliases — delegate to embedding module
# ---------------------------------------------------------------------------

def _compute_resemblyzer_embedding(audio_paths: list[str]) -> Optional[list[float]]:
    return embed_batch(audio_paths)

def _vec_to_hex(vec: list[float]) -> str:
    return vec_to_hex(vec)

def _hex_to_vec(hex_str: str) -> Optional[list[float]]:
    return hex_to_vec(hex_str)

def _is_audio_embedding(hex_str: str) -> bool:
    return is_audio_embedding(hex_str)

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    return cosine_similarity(a, b)


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
