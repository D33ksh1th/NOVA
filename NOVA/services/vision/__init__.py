"""Vision services (Phase 2-D)."""

from .ocr import OCRResult, OCRService
from .screen import ScreenCaptureResult, ScreenCaptureService
from .camera import CameraCaptureResult, CameraService
from .detection import VisionAnalysisResult, VisionDetectionService
from .automation import AutomationResult, BrowserAutomationService

__all__ = [
	"OCRResult",
	"OCRService",
	"ScreenCaptureResult",
	"ScreenCaptureService",
	"CameraCaptureResult",
	"CameraService",
	"VisionAnalysisResult",
	"VisionDetectionService",
	"AutomationResult",
	"BrowserAutomationService",
]
