"""Lightweight image analysis service."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from packages.common import logger


@dataclass
class VisionAnalysisResult:
	summary: str
	backend: str = "pil"
	width: int = 0
	height: int = 0
	mode: str = ""
	hints: list[str] = field(default_factory=list)
	error: str = ""


class VisionDetectionService:
	def analyze_image(self, image_path: str, question: str | None = None) -> VisionAnalysisResult:
		path = Path(image_path or "")
		if not path.exists():
			return VisionAnalysisResult(summary="", error=f"File not found: {path}")

		try:
			from PIL import Image, ImageStat  # type: ignore

			img = Image.open(path)
			width, height = img.size
			mode = img.mode
			stat = ImageStat.Stat(img.convert("RGB"))
			avg_rgb = tuple(int(v) for v in stat.mean[:3])

			hints = [
				f"resolution {width}x{height}",
				f"mode {mode}",
				f"average color rgb{avg_rgb}",
			]

			if question:
				summary = f"I analyzed '{path.name}' for '{question}'. It appears to be an image with {hints[0]}, {hints[1]}, and {hints[2]}."
			else:
				summary = f"Image '{path.name}' analyzed: {hints[0]}, {hints[1]}, {hints[2]}."

			return VisionAnalysisResult(
				summary=summary,
				backend="pil",
				width=width,
				height=height,
				mode=mode,
				hints=hints,
			)
		except ImportError:
			logger.warning("VisionDetectionService: Pillow is not installed")
			return VisionAnalysisResult(
				summary="",
				backend="pil",
				error="Pillow is not installed. Run: pip install pillow",
			)
		except Exception as ex:
			logger.error(f"VisionDetectionService error -> {ex}")
			return VisionAnalysisResult(summary="", backend="pil", error=str(ex))

