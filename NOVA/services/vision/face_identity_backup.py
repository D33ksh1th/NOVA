"""Face identity enrollment and recognition.

Primary backend (if installed):
- face_recognition (dlib 128D embeddings)

Fallback backend:
- OpenCV face crop + normalized grayscale histogram
"""

from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from packages.common import logger


@dataclass
class FaceProfile:
    id: str
    name: str
    role: str
    embedding: List[float]
    backend: str
    created_at: str
    updated_at: str


@dataclass
class FaceRecognitionResult:
    recognized: bool
    name: str = "unknown"
    role: str = "unknown"
    confidence: float = 0.0
    backend: str = "none"
    error: str = ""


class FaceRegistry:
    def __init__(self):
        self._profiles: dict[str, FaceProfile] = {}
        self._file = Path(__file__).resolve().parents[2] / "data" / "face_profiles.json"
        self._load()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _load(self) -> None:
        try:
            if not self._file.exists():
                return
            payload = json.loads(self._file.read_text(encoding="utf-8"))
            for row in payload.get("profiles", []):
                if not isinstance(row, dict):
                    continue
                name = str(row.get("name") or "").strip()
                embedding = row.get("embedding")
                if not name or not isinstance(embedding, list) or not embedding:
                    continue
                profile = FaceProfile(
                    id=str(row.get("id") or str(uuid.uuid4())),
                    name=name,
                    role="admin" if str(row.get("role") or "user").lower() == "admin" else "user",
                    embedding=[float(v) for v in embedding],
                    backend=str(row.get("backend") or "unknown"),
                    created_at=str(row.get("created_at") or ""),
                    updated_at=str(row.get("updated_at") or ""),
                )
                self._profiles[name.lower()] = profile
            logger.info("FaceRegistry: loaded profiles", total=len(self._profiles))
        except Exception as ex:
            logger.warning(f"FaceRegistry load failed: {ex}")

    def _save(self) -> None:
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "profiles": [
                    {
                        "id": profile.id,
                        "name": profile.name,
                        "role": profile.role,
                        "embedding": profile.embedding,
                        "backend": profile.backend,
                        "created_at": profile.created_at,
                        "updated_at": profile.updated_at,
                    }
                    for profile in self._profiles.values()
                ]
            }
            self._file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as ex:
            logger.warning(f"FaceRegistry save failed: {ex}")

    def all_profiles(self) -> list[FaceProfile]:
        return list(self._profiles.values())

    def get(self, name: str) -> Optional[FaceProfile]:
        return self._profiles.get((name or "").strip().lower())

    def get_admin(self) -> Optional[FaceProfile]:
        for profile in self._profiles.values():
            if profile.role == "admin":
                return profile
        return None

    def _clear_admin(self) -> None:
        for key, profile in list(self._profiles.items()):
            if profile.role == "admin":
                self._profiles[key] = FaceProfile(
                    id=profile.id,
                    name=profile.name,
                    role="user",
                    embedding=profile.embedding,
                    backend=profile.backend,
                    created_at=profile.created_at,
                    updated_at=self._now(),
                )

    def upsert(self, name: str, role: str, embedding: List[float], backend: str) -> FaceProfile:
        existing = self.get(name)
        now = self._now()
        normalized_role = "admin" if role == "admin" else "user"
        if normalized_role == "admin":
            self._clear_admin()
        profile = FaceProfile(
            id=existing.id if existing else str(uuid.uuid4()),
            name=name.strip(),
            role=normalized_role,
            embedding=embedding,
            backend=backend,
            created_at=existing.created_at if existing and existing.created_at else now,
            updated_at=now,
        )
        self._profiles[profile.name.lower()] = profile
        self._save()
        return profile


class FaceIdentityService:
    def __init__(self, registry: FaceRegistry, similarity_threshold: float = 0.58):
        self.registry = registry
        self.similarity_threshold = similarity_threshold

    def enroll_from_image(self, name: str, image_path: str, role: str = "user") -> FaceRecognitionResult:
        if not name.strip():
            return FaceRecognitionResult(recognized=False, error="Name is required for face enrollment")

        embedding, backend, error = self._extract_embedding(image_path)
        if embedding is None:
            return FaceRecognitionResult(recognized=False, backend=backend, error=error or "No face detected")

        profile = self.registry.upsert(name=name.strip(), role=role, embedding=embedding, backend=backend)
        return FaceRecognitionResult(
            recognized=True,
            name=profile.name,
            role=profile.role,
            confidence=1.0,
            backend=backend,
        )

    def recognize_from_image(self, image_path: str) -> FaceRecognitionResult:
        embedding, backend, error = self._extract_embedding(image_path)
        if embedding is None:
            return FaceRecognitionResult(recognized=False, backend=backend, error=error or "No face detected")

        best_profile: Optional[FaceProfile] = None
        best_score = 0.0
        for profile in self.registry.all_profiles():
            score = self._cosine_similarity(embedding, profile.embedding)
            if score > best_score:
                best_score = score
                best_profile = profile

        if best_profile and best_score >= self.similarity_threshold:
            return FaceRecognitionResult(
                recognized=True,
                name=best_profile.name,
                role=best_profile.role,
                confidence=round(best_score, 3),
                backend=backend,
            )

        return FaceRecognitionResult(
            recognized=False,
            confidence=round(best_score, 3),
            backend=backend,
            error="Face did not match any enrolled profile",
        )

    def analyze_image(self, image_path: str) -> dict:
        try:
            import cv2  # type: ignore
        except ImportError:
            return {
                "ok": False,
                "error": "opencv-python is not installed",
                "ready_for_enrollment": False,
                "guidance": ["Install opencv-python to enable live face guidance."],
            }

        frame = cv2.imread(image_path)
        if frame is None:
            return {
                "ok": False,
                "error": "failed_to_read_image",
                "ready_for_enrollment": False,
                "guidance": ["Camera frame could not be decoded."],
            }

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(48, 48))

        frame_h, frame_w = gray.shape
        if len(faces) == 0:
            return {
                "ok": True,
                "face_count": 0,
                "ready_for_enrollment": False,
                "primary_instruction": "No face detected. Center your face in the camera.",
                "guidance": [
                    "Move your face into frame.",
                    "Use brighter lighting on your face.",
                    "Hold still for 1-2 seconds.",
                ],
                "bbox": None,
                "quality": {
                    "brightness": round(float(gray.mean()), 2),
                    "sharpness": round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 2),
                },
            }

        x, y, w, h = sorted(faces, key=lambda it: it[2] * it[3], reverse=True)[0]
        cx = (x + (w / 2.0)) / max(1, frame_w)
        cy = (y + (h / 2.0)) / max(1, frame_h)
        area_ratio = (w * h) / max(1, frame_w * frame_h)

        brightness = float(gray.mean())
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())

        guidance: list[str] = []
        if cx < 0.38:
            guidance.append("Move slightly right")
        elif cx > 0.62:
            guidance.append("Move slightly left")

        if cy < 0.38:
            guidance.append("Move slightly down")
        elif cy > 0.62:
            guidance.append("Move slightly up")

        if area_ratio < 0.09:
            guidance.append("Move closer to the camera")
        elif area_ratio > 0.42:
            guidance.append("Move a bit back from the camera")

        if brightness < 55:
            guidance.append("Increase lighting on your face")
        if sharpness < 40:
            guidance.append("Hold still and reduce camera shake")

        ready = (len(faces) == 1) and len(guidance) == 0
        if ready:
            primary = "Perfect framing. You can enroll now."
        elif guidance:
            primary = guidance[0]
        elif len(faces) > 1:
            primary = "Multiple faces detected. Keep only one face in frame."
            guidance.append(primary)
        else:
            primary = "Center your face and hold still."
            guidance.append(primary)

        return {
            "ok": True,
            "face_count": int(len(faces)),
            "ready_for_enrollment": bool(ready),
            "primary_instruction": primary,
            "guidance": guidance,
            "bbox": {
                "x": int(x),
                "y": int(y),
                "w": int(w),
                "h": int(h),
                "frame_w": int(frame_w),
                "frame_h": int(frame_h),
                "center_x": round(float(cx), 3),
                "center_y": round(float(cy), 3),
                "area_ratio": round(float(area_ratio), 3),
            },
            "quality": {
                "brightness": round(brightness, 2),
                "sharpness": round(sharpness, 2),
            },
        }

    def _extract_embedding(self, image_path: str) -> Tuple[Optional[List[float]], str, str]:
        p = Path(image_path or "")
        if not p.exists():
            return None, "none", f"Image not found: {p}"

        vector, face_err = self._extract_face_recognition_embedding(str(p))
        if vector is not None:
            return vector, "face_recognition", ""

        fallback_vector, fallback_err = self._extract_opencv_hist_embedding(str(p))
        if fallback_vector is not None:
            return fallback_vector, "opencv-hist", ""

        if fallback_err:
            if face_err:
                return None, "opencv-hist", f"{fallback_err} (face_recognition unavailable: {face_err})"
            return None, "opencv-hist", fallback_err
        if face_err:
            return None, "face_recognition", face_err
        return None, "none", "No face found"

    def _extract_face_recognition_embedding(self, image_path: str) -> Tuple[Optional[List[float]], str]:
        try:
            import face_recognition  # type: ignore
        except ImportError:
            return None, "face_recognition dependency not installed"

        try:
            image = face_recognition.load_image_file(image_path)
            locations = face_recognition.face_locations(image, model="hog")
            if not locations:
                return None, "no face detected by face_recognition"

            encodings = face_recognition.face_encodings(image, known_face_locations=locations)
            if not encodings:
                return None, "no embedding produced by face_recognition"

            if len(encodings) > 1:
                # Pick the largest face region when multiple faces are present.
                largest_idx = 0
                largest_area = -1
                for idx, loc in enumerate(locations):
                    top, right, bottom, left = loc
                    area = max(0, bottom - top) * max(0, right - left)
                    if area > largest_area:
                        largest_area = area
                        largest_idx = idx
                enc = encodings[largest_idx]
            else:
                enc = encodings[0]

            return [float(v) for v in enc.tolist()], ""
        except Exception as ex:
            return None, f"face_recognition failed: {ex}"

    def _extract_opencv_hist_embedding(self, image_path: str) -> Tuple[Optional[List[float]], str]:
        try:
            import cv2  # type: ignore
        except ImportError:
            return None, "opencv-python is not installed"

        frame = cv2.imread(image_path)
        if frame is None:
            return None, "failed to read image"

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(36, 36))
        if len(faces) == 0:
            return None, "no face detected by opencv"

        x, y, w, h = sorted(faces, key=lambda it: it[2] * it[3], reverse=True)[0]
        crop = gray[y:y + h, x:x + w]
        if crop.size == 0:
            return None, "invalid face crop"

        resized = cv2.resize(crop, (96, 96))
        hist = cv2.calcHist([resized], [0], None, [64], [0, 256])
        hist = cv2.normalize(hist, hist).flatten()
        return [float(v) for v in hist.tolist()], ""

    def _cosine_similarity(self, left: List[float], right: List[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        dot = sum(a * b for a, b in zip(left, right))
        mag_left = math.sqrt(sum(a * a for a in left))
        mag_right = math.sqrt(sum(b * b for b in right))
        if mag_left == 0 or mag_right == 0:
            return 0.0
        return dot / (mag_left * mag_right)
