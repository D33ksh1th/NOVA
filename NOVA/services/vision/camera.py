"""Camera capture service."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from packages.common import logger


@dataclass
class CameraCaptureResult:
	success: bool
	path: str = ""
	backend: str = "none"
	error: str = ""


class CameraService:
	def capture(self, output_path: str | None = None, index: int = 0) -> CameraCaptureResult:
		try:
			import cv2  # type: ignore
		except ImportError:
			return CameraCaptureResult(
				success=False,
				backend="opencv",
				error="opencv-python is not installed. Run: pip install opencv-python",
			)

		path = Path(output_path) if output_path else Path(tempfile.mkstemp(prefix="nova_camera_", suffix=".jpg")[1])
		path.parent.mkdir(parents=True, exist_ok=True)

		cap = cv2.VideoCapture(index)
		if not cap.isOpened():
			return CameraCaptureResult(success=False, backend="opencv", error="Unable to open camera device")

		ok, frame = cap.read()
		cap.release()

		if not ok or frame is None:
			return CameraCaptureResult(success=False, backend="opencv", error="Failed to capture frame")

		cv2.imwrite(str(path), frame)
		logger.info(f"CameraService: captured image -> {path}")
		return CameraCaptureResult(success=True, path=str(path), backend="opencv")

