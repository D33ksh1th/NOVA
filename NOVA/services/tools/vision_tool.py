"""Vision / OCR / browser automation tool."""

from __future__ import annotations

import re
from pathlib import Path

from packages.common import logger
from packages.config import settings
from services.tools.base import Tool
from services.vision import (
    BrowserAutomationService,
    CameraService,
    OCRService,
    ScreenCaptureService,
    VisionDetectionService,
)


class VisionTool(Tool):
    def __init__(self):
        self.ocr = OCRService(provider=settings.OCR_PROVIDER)
        self.screen = ScreenCaptureService()
        self.camera = CameraService()
        self.vision = VisionDetectionService()
        self.automation = BrowserAutomationService()

    @property
    def name(self):
        return "vision"

    def can_handle(self, message: str) -> bool:
        text = (message or "").lower()
        keys = [
            "ocr",
            "extract text",
            "read text from image",
            "analyze image",
            "describe image",
            "what am i looking at",
            "screenshot",
            "screen capture",
            "camera capture",
            "take photo",
            "open website",
            "open url",
            "navigate to",
            "search web for",
            "playwright",
            "browser automation",
        ]
        return any(k in text for k in keys)

    def execute(self, message: str):
        text = (message or "").strip()
        low = text.lower()

        if any(k in low for k in ["open website", "open url", "navigate to", "browse to"]):
            url = self._extract_url(text)
            if not url:
                return {
                    "action": "vision",
                    "success": False,
                    "response": "Please provide a URL, for example: open website https://example.com",
                }
            out = self.automation.open_and_describe(url, headless=settings.AUTOMATION_HEADLESS)
            return self._as_dict(out)

        if "search web for" in low or "automate search for" in low:
            query = self._extract_query(text)
            out = self.automation.search_web(query, headless=settings.AUTOMATION_HEADLESS)
            return self._as_dict(out)

        if "camera" in low and any(k in low for k in ["capture", "photo", "take"]):
            cap = self.camera.capture()
            if not cap.success:
                return {
                    "action": "vision",
                    "success": False,
                    "response": f"Camera capture failed: {cap.error}",
                    "backend": cap.backend,
                }
            analysis = self.vision.analyze_image(cap.path, question=text)
            return {
                "action": "vision",
                "success": analysis.error == "",
                "image_path": cap.path,
                "backend": analysis.backend,
                "response": analysis.summary if not analysis.error else analysis.error,
                "analysis": analysis.__dict__,
            }

        if "screenshot" in low or "screen capture" in low:
            cap = self.screen.capture()
            if not cap.success:
                return {
                    "action": "vision",
                    "success": False,
                    "response": f"Screenshot failed: {cap.error}",
                    "backend": cap.backend,
                }

            if "ocr" in low or "read text" in low or "extract text" in low:
                ocr = self.ocr.extract_text(cap.path)
                reply = ocr.text if ocr.text else (ocr.error or "No text found in screenshot")
                return {
                    "action": "vision",
                    "success": bool(ocr.text),
                    "image_path": cap.path,
                    "backend": ocr.backend,
                    "response": reply,
                    "ocr": ocr.__dict__,
                }

            analysis = self.vision.analyze_image(cap.path, question=text)
            return {
                "action": "vision",
                "success": analysis.error == "",
                "image_path": cap.path,
                "backend": analysis.backend,
                "response": analysis.summary if not analysis.error else analysis.error,
                "analysis": analysis.__dict__,
            }

        path = self._extract_path(text)
        if not path:
            return {
                "action": "vision",
                "success": False,
                "response": "Provide an image path, screenshot request, or automation command.",
            }

        if any(k in low for k in ["ocr", "extract text", "read text"]):
            out = self.ocr.extract_text(path)
            return {
                "action": "vision",
                "success": bool(out.text),
                "path": path,
                "backend": out.backend,
                "response": out.text if out.text else (out.error or "No text found"),
                "ocr": out.__dict__,
            }

        analysis = self.vision.analyze_image(path, question=text)
        return {
            "action": "vision",
            "success": analysis.error == "",
            "path": path,
            "backend": analysis.backend,
            "response": analysis.summary if not analysis.error else analysis.error,
            "analysis": analysis.__dict__,
        }

    def _extract_url(self, text: str) -> str:
        m = re.search(r"https?://\S+", text, flags=re.IGNORECASE)
        if m:
            return m.group(0).rstrip(".,)")

        m = re.search(r"\b(?:open website|open url|navigate to|browse to)\s+([^\s]+)", text, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip().rstrip(".,)")
        return ""

    def _extract_query(self, text: str) -> str:
        m = re.search(r"(?:search web for|automate search for)\s+(.+)$", text, flags=re.IGNORECASE)
        return m.group(1).strip() if m else ""

    def _extract_path(self, text: str) -> str:
        quote = re.search(r"['\"]([^'\"]+\.(?:png|jpg|jpeg|webp|bmp|tiff|gif|pdf|txt|md|log|csv))['\"]", text, flags=re.IGNORECASE)
        if quote:
            return quote.group(1).strip()

        token = re.search(r"(/[^\s]+\.(?:png|jpg|jpeg|webp|bmp|tiff|gif|pdf|txt|md|log|csv))", text, flags=re.IGNORECASE)
        if token:
            return token.group(1).strip()

        rel = re.search(r"\b([\w./\\-]+\.(?:png|jpg|jpeg|webp|bmp|tiff|gif|pdf|txt|md|log|csv))\b", text, flags=re.IGNORECASE)
        if rel:
            candidate = Path(rel.group(1)).expanduser()
            return str(candidate)
        return ""

    def _as_dict(self, out) -> dict:
        logger.info(f"VisionTool automation -> success={out.success}, backend={out.backend}")
        return {
            "action": "vision",
            "success": out.success,
            "response": out.response,
            "backend": out.backend,
            "title": out.title,
            "url": out.url,
            "error": out.error,
        }
