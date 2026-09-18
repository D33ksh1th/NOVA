"""Human perception helpers for camera-based face/gesture/emotion understanding.

This module keeps dependencies optional:
- OpenCV (required for capture + face heuristics)
- MediaPipe (optional, enables finger/gesture understanding)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from packages.common import logger


@dataclass
class HumanPerceptionResult:
    success: bool
    summary: str
    face_count: int = 0
    finger_count: Optional[int] = None
    gesture: str = "unknown"
    emotion: str = "unknown"
    backend: str = "opencv"
    error: str = ""


class HumanPerceptionService:
    def analyze(self, image_path: str, question: str = "") -> HumanPerceptionResult:
        path = Path(image_path or "")
        if not path.exists():
            return HumanPerceptionResult(
                success=False,
                summary="",
                error=f"Image not found: {path}",
            )

        try:
            import cv2  # type: ignore
        except ImportError:
            return HumanPerceptionResult(
                success=False,
                summary="",
                backend="opencv",
                error="opencv-python is not installed. Run: pip install opencv-python",
            )

        frame = cv2.imread(str(path))
        if frame is None:
            return HumanPerceptionResult(
                success=False,
                summary="",
                backend="opencv",
                error="Failed to read image",
            )

        face_count = self._detect_faces(frame)
        emotion = self._detect_emotion(frame, face_count)
        finger_count, gesture, hand_backend_error = self._detect_fingers_and_gesture(frame)

        requested_fingers = any(
            token in (question or "").lower()
            for token in ["finger", "fingers", "gesture", "hand sign", "hand gesture"]
        )

        lines = []
        lines.append(f"I can see {face_count} face{'s' if face_count != 1 else ''}.")
        if face_count > 0:
            lines.append(f"Estimated visible emotion: {emotion}.")

        if finger_count is not None:
            lines.append(f"Detected raised fingers: {finger_count}.")
            lines.append(f"Detected gesture: {gesture}.")
        elif requested_fingers:
            lines.append(
                "I could not reliably read hand landmarks in this frame. "
                "Install mediapipe for precise finger/gesture tracking: pip install mediapipe"
            )

        lines.append(
            "Face identity tracking can be added as the next phase using persistent face embeddings."
        )

        summary = " ".join(lines)
        backend = "opencv+mediapipe" if finger_count is not None else "opencv"
        if hand_backend_error:
            logger.info("HumanPerceptionService: hand detection fallback", reason=hand_backend_error)

        return HumanPerceptionResult(
            success=True,
            summary=summary,
            face_count=face_count,
            finger_count=finger_count,
            gesture=gesture,
            emotion=emotion,
            backend=backend,
        )

    def _detect_faces(self, frame) -> int:
        import cv2  # type: ignore

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(36, 36))
        return int(len(faces))

    def _detect_emotion(self, frame, face_count: int) -> str:
        if face_count == 0:
            return "unknown"

        # Lightweight heuristic: smile presence -> happy, else neutral.
        try:
            import cv2  # type: ignore

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            smile = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_smile.xml")
            smiles = smile.detectMultiScale(gray, scaleFactor=1.7, minNeighbors=22, minSize=(25, 25))
            if len(smiles) > 0:
                return "happy"
            return "neutral"
        except Exception:
            return "neutral"

    def _detect_fingers_and_gesture(self, frame) -> Tuple[Optional[int], str, str]:
        try:
            import cv2  # type: ignore
            import mediapipe as mp  # type: ignore
        except ImportError:
            return None, "unknown", "mediapipe_missing"

        mp_hands = mp.solutions.hands
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        with mp_hands.Hands(
            static_image_mode=True,
            max_num_hands=1,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        ) as hands:
            result = hands.process(rgb)

        if not result.multi_hand_landmarks:
            return None, "unknown", "no_hand_detected"

        hand = result.multi_hand_landmarks[0]
        handedness = "Right"
        if result.multi_handedness and len(result.multi_handedness) > 0:
            try:
                handedness = result.multi_handedness[0].classification[0].label
            except Exception:
                handedness = "Right"

        landmarks = hand.landmark

        # Landmark indices: tip and pip joints for each finger.
        tips = [4, 8, 12, 16, 20]
        pips = [3, 6, 10, 14, 18]
        raised = 0

        # Thumb uses x comparison depending on hand orientation.
        thumb_tip = landmarks[tips[0]]
        thumb_joint = landmarks[pips[0]]
        if handedness.lower() == "right":
            if thumb_tip.x < thumb_joint.x:
                raised += 1
        else:
            if thumb_tip.x > thumb_joint.x:
                raised += 1

        # Other fingers use y comparison (tip above pip).
        for idx in range(1, 5):
            if landmarks[tips[idx]].y < landmarks[pips[idx]].y:
                raised += 1

        gesture_map = {
            0: "fist",
            1: "one",
            2: "two",
            3: "three",
            4: "four",
            5: "open_palm",
        }
        gesture = gesture_map.get(raised, "unknown")
        return raised, gesture, ""
