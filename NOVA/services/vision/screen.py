"""Screen capture service."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from packages.common import logger


@dataclass
class ScreenCaptureResult:
	success: bool
	path: str = ""
	backend: str = "none"
	error: str = ""


class ScreenCaptureService:
	def capture(self, output_path: str | None = None) -> ScreenCaptureResult:
		try:
			path = Path(output_path) if output_path else Path(tempfile.mkstemp(prefix="nova_screen_", suffix=".png")[1])
			path.parent.mkdir(parents=True, exist_ok=True)

			try:
				from PIL import ImageGrab  # type: ignore

				img = ImageGrab.grab(all_screens=True)
				img.save(path)
				return ScreenCaptureResult(success=True, path=str(path), backend="pil-imagegrab")
			except ImportError:
				logger.warning("ScreenCaptureService: Pillow is not installed")
				return ScreenCaptureResult(
					success=False,
					path=str(path),
					backend="pil-imagegrab",
					error="Pillow is not installed. Run: pip install pillow",
				)
		except Exception as ex:
			logger.error(f"ScreenCaptureService error -> {ex}")
			return ScreenCaptureResult(success=False, backend="screen", error=str(ex))

