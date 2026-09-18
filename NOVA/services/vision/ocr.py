"""OCR adapter service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from packages.common import logger


@dataclass
class OCRResult:
	text: str
	lines: list[str]
	backend: str = "none"
	confidence: float = 0.0
	error: str = ""


class OCRService:
	def __init__(self, provider: str = "paddleocr"):
		self.provider = (provider or "paddleocr").lower()

	def extract_text(self, image_path: str) -> OCRResult:
		path = Path(image_path or "")
		if not path.exists():
			return OCRResult(text="", lines=[], backend="none", error=f"File not found: {path}")

		# Convenience: plain text files can be returned directly.
		if path.suffix.lower() in {".txt", ".md", ".log", ".csv"}:
			try:
				txt = path.read_text(encoding="utf-8", errors="ignore")
				lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
				return OCRResult(text="\n".join(lines), lines=lines, backend="text", confidence=1.0)
			except Exception as ex:
				return OCRResult(text="", lines=[], backend="text", error=str(ex))

		if self.provider == "paddleocr":
			return self._extract_with_paddleocr(path)

		return OCRResult(text="", lines=[], backend=self.provider, error=f"Unsupported OCR provider: {self.provider}")

	def _extract_with_paddleocr(self, path: Path) -> OCRResult:
		try:
			from paddleocr import PaddleOCR  # type: ignore

			ocr = PaddleOCR(use_angle_cls=True, lang="en")
			data = ocr.ocr(str(path), cls=True)
			lines: list[str] = []
			scores: list[float] = []

			for block in data or []:
				for item in block or []:
					text = ""
					score = 0.0
					if isinstance(item, (list, tuple)) and len(item) >= 2:
						payload = item[1]
						if isinstance(payload, (list, tuple)) and len(payload) >= 2:
							text = str(payload[0] or "").strip()
							try:
								score = float(payload[1])
							except Exception:
								score = 0.0
					if text:
						lines.append(text)
						scores.append(score)

			confidence = (sum(scores) / len(scores)) if scores else 0.0
			return OCRResult(
				text="\n".join(lines),
				lines=lines,
				backend="paddleocr",
				confidence=round(confidence, 3),
			)
		except ImportError:
			logger.warning("OCRService: paddleocr is not installed")
			return OCRResult(
				text="",
				lines=[],
				backend="paddleocr",
				error="paddleocr is not installed. Run: pip install paddleocr",
			)
		except Exception as ex:
			logger.error(f"OCRService error -> {ex}")
			return OCRResult(text="", lines=[], backend="paddleocr", error=str(ex))
