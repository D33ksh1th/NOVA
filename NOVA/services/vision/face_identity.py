"""Face identity enrollment and recognition.

Primary backend:
    InsightFace buffalo_l — ArcFace 512-D embeddings
    Models bundled inside buffalo_l pack:
        • det_10g.onnx       — RetinaFace detection
        • w600k_r50.onnx     — ArcFace recognition (512-D)
        • genderage.onnx     — Gender + Age prediction
        • 1k3d68.onnx        — 3D 68-landmark pose
        • 2d106det.onnx      — Dense 106 2D landmark

Enrollment strategy:
    Multi-sample per person — caller sends N frames; we compute and
    AVERAGE the embeddings so the stored prototype covers variation
    in lighting, slight pose, and expression.  A single-sample enroll
    still works but is less robust.

Fallback backend (no InsightFace):
    OpenCV Haar + grayscale histogram.
"""
from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from packages.common import logger

_insightface_app = None
_INSIGHTFACE_LOAD_TRIED = False
_INSIGHTFACE_AVAILABLE = False
_INSIGHTFACE_PROVIDERS = ["CPUExecutionProvider"]
_INSIGHTFACE_MODEL = "buffalo_l"
_INSIGHTFACE_DET_SIZE = (640, 640)


def _resolve_speaker_identity_id(name: str) -> Optional[str]:
    """Return matching speaker profile ID by name, if present."""
    try:
        voice_file = Path(__file__).resolve().parents[2] / "data" / "voice_speakers.json"
        if not voice_file.exists():
            return None
        payload = json.loads(voice_file.read_text(encoding="utf-8"))
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
        logger.warning(f"FaceRegistry: failed to resolve speaker identity id: {ex}")
    return None


def _get_insightface_app():
    global _insightface_app, _INSIGHTFACE_LOAD_TRIED, _INSIGHTFACE_AVAILABLE
    if _INSIGHTFACE_LOAD_TRIED:
        return _insightface_app
    _INSIGHTFACE_LOAD_TRIED = True
    try:
        import warnings
        from insightface.app import FaceAnalysis  # type: ignore
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            app = FaceAnalysis(name=_INSIGHTFACE_MODEL, providers=_INSIGHTFACE_PROVIDERS)
            app.prepare(ctx_id=0, det_size=_INSIGHTFACE_DET_SIZE)
        _insightface_app = app
        _INSIGHTFACE_AVAILABLE = True
        logger.info("InsightFace buffalo_l loaded", backend="insightface")
    except Exception as exc:
        logger.warning("InsightFace unavailable, will use OpenCV fallback", error=str(exc))
    return _insightface_app


@dataclass
class FaceProfile:
    id: str
    name: str
    role: str
    embedding: List[float]
    backend: str
    created_at: str
    updated_at: str
    sample_count: int = 1
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FaceAttributes:
    age: Optional[int] = None
    gender: Optional[str] = None
    gender_confidence: float = 0.0
    pose_yaw: Optional[float] = None
    pose_pitch: Optional[float] = None
    pose_roll: Optional[float] = None
    landmarks_2d: Optional[List[List[float]]] = None
    landmarks_3d: Optional[List[List[float]]] = None
    bbox: Optional[Dict[str, Any]] = None
    det_score: float = 0.0


@dataclass
class FaceRecognitionResult:
    recognized: bool
    name: str = "unknown"
    role: str = "unknown"
    confidence: float = 0.0
    backend: str = "none"
    error: str = ""
    attributes: Optional[FaceAttributes] = None


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
                    sample_count=int(row.get("sample_count") or 1),
                    attributes=dict(row.get("attributes") or {}),
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
                        "id": p.id, "name": p.name, "role": p.role,
                        "embedding": p.embedding, "backend": p.backend,
                        "created_at": p.created_at, "updated_at": p.updated_at,
                        "sample_count": p.sample_count, "attributes": p.attributes,
                    }
                    for p in self._profiles.values()
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
        for p in self._profiles.values():
            if p.role == "admin":
                return p
        return None

    def _clear_admin(self) -> None:
        for key, p in list(self._profiles.items()):
            if p.role == "admin":
                self._profiles[key] = FaceProfile(
                    id=p.id, name=p.name, role="user",
                    embedding=p.embedding, backend=p.backend,
                    created_at=p.created_at, updated_at=self._now(),
                    sample_count=p.sample_count, attributes=p.attributes,
                )

    def upsert(
        self,
        name: str,
        role: str,
        embedding: List[float],
        backend: str,
        attributes: Optional[Dict[str, Any]] = None,
        merge_with_existing: bool = True,
    ) -> FaceProfile:
        existing = self.get(name)
        now = self._now()
        normalized_role = "admin" if role == "admin" else "user"
        if normalized_role == "admin":
            self._clear_admin()

        if merge_with_existing and existing and existing.backend == backend and len(existing.embedding) == len(embedding):
            n = existing.sample_count
            merged = [(existing.embedding[i] * n + embedding[i]) / (n + 1) for i in range(len(embedding))]
            norm = math.sqrt(sum(v * v for v in merged)) or 1.0
            merged = [v / norm for v in merged]
            profile = FaceProfile(
                id=existing.id, name=existing.name, role=normalized_role,
                embedding=merged, backend=backend,
                created_at=existing.created_at, updated_at=now,
                sample_count=n + 1,
                attributes=dict(attributes or existing.attributes or {}),
            )
        else:
            linked_speaker_id = _resolve_speaker_identity_id(name)
            profile = FaceProfile(
                id=existing.id if existing else (linked_speaker_id or str(uuid.uuid4())),
                name=name.strip(), role=normalized_role,
                embedding=embedding, backend=backend,
                created_at=existing.created_at if existing and existing.created_at else now,
                updated_at=now, sample_count=1,
                attributes=dict(attributes or {}),
            )
        self._profiles[profile.name.lower()] = profile
        self._save()
        return profile


class FaceIdentityService:
    def __init__(self, registry: FaceRegistry, similarity_threshold: float = 0.40):
        self.registry = registry
        self.similarity_threshold = similarity_threshold

    def enroll_from_image(self, name: str, image_path: str, role: str = "user", merge: bool = True) -> FaceRecognitionResult:
        if not name.strip():
            return FaceRecognitionResult(recognized=False, error="Name is required for face enrollment")

        embedding, attrs, backend, error = self._extract_embedding_and_attrs(image_path)
        if embedding is None:
            return FaceRecognitionResult(recognized=False, backend=backend, error=error or "No face detected")

        profile = self.registry.upsert(
            name=name.strip(), role=role, embedding=embedding, backend=backend,
            attributes=self._attrs_to_dict(attrs), merge_with_existing=merge,
        )
        return FaceRecognitionResult(
            recognized=True, name=profile.name, role=profile.role,
            confidence=1.0, backend=backend, attributes=attrs,
        )

    def recognize_from_image(self, image_path: str) -> FaceRecognitionResult:
        embedding, attrs, backend, error = self._extract_embedding_and_attrs(image_path)
        if embedding is None:
            return FaceRecognitionResult(recognized=False, backend=backend, error=error or "No face detected")

        best_profile: Optional[FaceProfile] = None
        best_score = 0.0
        for p in self.registry.all_profiles():
            score = self._cosine_similarity(embedding, p.embedding)
            if score > best_score:
                best_score = score
                best_profile = p

        if best_profile and best_score >= self.similarity_threshold:
            return FaceRecognitionResult(
                recognized=True, name=best_profile.name, role=best_profile.role,
                confidence=round(best_score, 4), backend=backend, attributes=attrs,
            )

        return FaceRecognitionResult(
            recognized=False, confidence=round(best_score, 4), backend=backend,
            error="Face did not match any enrolled profile", attributes=attrs,
        )

    def analyze_image(self, image_path: str) -> dict:
        app = _get_insightface_app()
        if app is not None:
            return self._analyze_with_insightface(image_path, app)
        return self._analyze_with_opencv(image_path)

    def _analyze_with_insightface(self, image_path: str, app) -> dict:
        try:
            import cv2  # type: ignore
        except ImportError:
            return {"ok": False, "error": "opencv not installed", "ready_for_enrollment": False, "guidance": ["Install opencv-python."]}

        frame = cv2.imread(image_path)
        if frame is None:
            return {"ok": False, "error": "failed_to_read_image", "ready_for_enrollment": False, "guidance": ["Camera frame could not be decoded."]}

        frame_h, frame_w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness = round(float(gray.mean()), 2)
        sharpness = round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 2)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        faces = app.get(rgb)

        if len(faces) == 0:
            return {
                "ok": True, "face_count": 0, "ready_for_enrollment": False,
                "primary_instruction": "No face detected. Center your face in the camera.",
                "guidance": ["Move your face into frame.", "Ensure good lighting.", "Hold still."],
                "bbox": None, "quality": {"brightness": brightness, "sharpness": sharpness}, "attributes": None,
            }

        face = sorted(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]), reverse=True)[0]
        x1, y1, x2, y2 = [int(v) for v in face.bbox]
        w, h = x2 - x1, y2 - y1
        cx = (x1 + w / 2.0) / max(1, frame_w)
        cy = (y1 + h / 2.0) / max(1, frame_h)
        area_ratio = (w * h) / max(1, frame_w * frame_h)

        guidance: list[str] = []
        if cx < 0.38: guidance.append("Move slightly right")
        elif cx > 0.62: guidance.append("Move slightly left")
        if cy < 0.38: guidance.append("Move slightly down")
        elif cy > 0.62: guidance.append("Move slightly up")
        if area_ratio < 0.09: guidance.append("Move closer to the camera")
        elif area_ratio > 0.45: guidance.append("Move a bit back from the camera")
        if brightness < 50: guidance.append("Increase lighting on your face")
        if sharpness < 40: guidance.append("Hold still — image is blurry")

        pose_yaw = pose_pitch = pose_roll = None
        try:
            if hasattr(face, "pose") and face.pose is not None:
                pose_pitch = float(face.pose[0])
                pose_yaw = float(face.pose[1])
                pose_roll = float(face.pose[2])
                if abs(pose_yaw) > 30: guidance.append("Face the camera more directly (turn head)")
                if abs(pose_pitch) > 25: guidance.append("Level your head up/down")
        except Exception:
            pass

        age = gender = gender_conf = None
        try:
            if hasattr(face, "age") and face.age is not None:
                age = int(face.age)
            if hasattr(face, "gender") and face.gender is not None:
                gender = "male" if int(face.gender) == 1 else "female"
                gender_conf = 1.0
        except Exception:
            pass

        ready = (len(faces) == 1) and len(guidance) == 0
        primary = "Perfect framing. You can enroll now." if ready else (guidance[0] if guidance else "Center your face and hold still.")
        if len(faces) > 1:
            primary = "Multiple faces detected. Keep only one face in frame."
            guidance.insert(0, primary)
            ready = False

        return {
            "ok": True, "face_count": len(faces),
            "ready_for_enrollment": bool(ready), "primary_instruction": primary,
            "guidance": guidance,
            "bbox": {"x": x1, "y": y1, "w": w, "h": h, "frame_w": frame_w, "frame_h": frame_h,
                     "center_x": round(cx, 3), "center_y": round(cy, 3), "area_ratio": round(area_ratio, 3)},
            "quality": {"brightness": brightness, "sharpness": sharpness},
            "attributes": {
                "age": age, "gender": gender, "gender_confidence": gender_conf,
                "pose_yaw": round(pose_yaw, 2) if pose_yaw is not None else None,
                "pose_pitch": round(pose_pitch, 2) if pose_pitch is not None else None,
                "pose_roll": round(pose_roll, 2) if pose_roll is not None else None,
                "det_score": round(float(face.det_score), 3) if hasattr(face, "det_score") and face.det_score is not None else None,
            },
        }

    def _extract_embedding_and_attrs(self, image_path: str) -> Tuple[Optional[List[float]], Optional[FaceAttributes], str, str]:
        p = Path(image_path or "")
        if not p.exists():
            return None, None, "none", f"Image not found: {p}"

        app = _get_insightface_app()
        if app is not None:
            vec, attrs, err = self._extract_insightface(str(p), app)
            if vec is not None:
                return vec, attrs, "insightface", ""
            insight_err = err
        else:
            insight_err = "insightface unavailable"

        vec, err = self._extract_opencv_hist_embedding(str(p))
        if vec is not None:
            return vec, None, "opencv-hist", ""

        return None, None, "opencv-hist", f"{err or 'no face'} (insightface: {insight_err})"

    def _extract_insightface(self, image_path: str, app) -> Tuple[Optional[List[float]], Optional[FaceAttributes], str]:
        try:
            import cv2  # type: ignore
        except ImportError:
            return None, None, "opencv not installed"

        frame = cv2.imread(image_path)
        if frame is None:
            return None, None, "failed to read image"

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        faces = app.get(rgb)
        if not faces:
            return None, None, "no face detected by insightface"

        face = sorted(faces, key=lambda f: float(f.det_score or 0), reverse=True)[0]
        if face.embedding is None:
            return None, None, "no embedding from insightface"

        vec = [float(v) for v in face.embedding.tolist()]
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        vec = [v / norm for v in vec]

        frame_h, frame_w = frame.shape[:2]
        x1, y1, x2, y2 = [int(v) for v in face.bbox]

        age = gender = gender_conf = None
        try:
            if hasattr(face, "age") and face.age is not None:
                age = int(face.age)
            if hasattr(face, "gender") and face.gender is not None:
                gender = "male" if int(face.gender) == 1 else "female"
                gender_conf = 1.0
        except Exception:
            pass

        pose_yaw = pose_pitch = pose_roll = None
        try:
            if hasattr(face, "pose") and face.pose is not None:
                pose_pitch = float(face.pose[0])
                pose_yaw = float(face.pose[1])
                pose_roll = float(face.pose[2])
        except Exception:
            pass

        lm_2d = lm_3d = None
        try:
            if hasattr(face, "landmark_2d_106") and face.landmark_2d_106 is not None:
                lm_2d = [[round(float(v[0]), 1), round(float(v[1]), 1)] for v in face.landmark_2d_106]
        except Exception:
            pass
        try:
            if hasattr(face, "landmark_3d_68") and face.landmark_3d_68 is not None:
                lm_3d = [[round(float(v[0]), 1), round(float(v[1]), 1), round(float(v[2]), 1)] for v in face.landmark_3d_68]
        except Exception:
            pass

        attrs = FaceAttributes(
            age=age, gender=gender, gender_confidence=gender_conf or 0.0,
            pose_yaw=pose_yaw, pose_pitch=pose_pitch, pose_roll=pose_roll,
            landmarks_2d=lm_2d, landmarks_3d=lm_3d,
            bbox={"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1, "frame_w": frame_w, "frame_h": frame_h},
            det_score=float(face.det_score or 0.0),
        )
        return vec, attrs, ""

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

    def _analyze_with_opencv(self, image_path: str) -> dict:
        try:
            import cv2  # type: ignore
        except ImportError:
            return {"ok": False, "error": "opencv-python is not installed", "ready_for_enrollment": False, "guidance": ["Install opencv-python."]}

        frame = cv2.imread(image_path)
        if frame is None:
            return {"ok": False, "error": "failed_to_read_image", "ready_for_enrollment": False, "guidance": ["Camera frame could not be decoded."]}

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(48, 48))
        frame_h, frame_w = gray.shape
        brightness = round(float(gray.mean()), 2)
        sharpness = round(float(cv2.Laplacian(gray, cv2.CV_64F).var()), 2)

        if len(faces) == 0:
            return {
                "ok": True, "face_count": 0, "ready_for_enrollment": False,
                "primary_instruction": "No face detected. Center your face in the camera.",
                "guidance": ["Move your face into frame.", "Use brighter lighting.", "Hold still."],
                "bbox": None, "quality": {"brightness": brightness, "sharpness": sharpness},
            }

        x, y, w, h = sorted(faces, key=lambda it: it[2] * it[3], reverse=True)[0]
        cx = (x + w / 2.0) / max(1, frame_w)
        cy = (y + h / 2.0) / max(1, frame_h)
        area_ratio = (w * h) / max(1, frame_w * frame_h)

        guidance: list[str] = []
        if cx < 0.38: guidance.append("Move slightly right")
        elif cx > 0.62: guidance.append("Move slightly left")
        if cy < 0.38: guidance.append("Move slightly down")
        elif cy > 0.62: guidance.append("Move slightly up")
        if area_ratio < 0.09: guidance.append("Move closer to the camera")
        elif area_ratio > 0.42: guidance.append("Move a bit back from the camera")
        if brightness < 55: guidance.append("Increase lighting on your face")
        if sharpness < 40: guidance.append("Hold still and reduce camera shake")

        ready = (len(faces) == 1) and len(guidance) == 0
        primary = "Perfect framing. You can enroll now." if ready else (guidance[0] if guidance else "Center your face and hold still.")
        if len(faces) > 1:
            primary = "Multiple faces detected. Keep only one face in frame."
            guidance.insert(0, primary)
            ready = False

        return {
            "ok": True, "face_count": int(len(faces)), "ready_for_enrollment": bool(ready),
            "primary_instruction": primary, "guidance": guidance,
            "bbox": {"x": int(x), "y": int(y), "w": int(w), "h": int(h), "frame_w": frame_w, "frame_h": frame_h,
                     "center_x": round(float(cx), 3), "center_y": round(float(cy), 3), "area_ratio": round(float(area_ratio), 3)},
            "quality": {"brightness": brightness, "sharpness": sharpness},
        }

    @staticmethod
    def _attrs_to_dict(attrs: Optional[FaceAttributes]) -> Dict[str, Any]:
        if attrs is None:
            return {}
        return {
            "age": attrs.age, "gender": attrs.gender, "gender_confidence": attrs.gender_confidence,
            "pose_yaw": attrs.pose_yaw, "pose_pitch": attrs.pose_pitch, "pose_roll": attrs.pose_roll,
            "det_score": attrs.det_score,
        }

    @staticmethod
    def _cosine_similarity(left: List[float], right: List[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        dot = sum(a * b for a, b in zip(left, right))
        mag_l = math.sqrt(sum(a * a for a in left))
        mag_r = math.sqrt(sum(b * b for b in right))
        if mag_l == 0 or mag_r == 0:
            return 0.0
        return dot / (mag_l * mag_r)
