"""Screen awareness — capture and analyze what's on screen.

Uses macOS screencapture + VLM (qwen2.5-vl) to understand
what the user is looking at.

Skills: "what am I looking at", "summarize my screen",
        "what error is showing", "read my screen"
"""

import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from packages.common import logger
from services.skills.base import Skill, SkillContext

_TRIGGERS = [
    r"\bwhat('?s| is) on (my |the )?screen\b",
    r"\bwhat am i looking at\b",
    r"\bsummarize (my |the )?screen\b",
    r"\bread (my |the )?screen\b",
    r"\bwhat error is showing\b",
    r"\bscreen(shot)? (analysis|capture|check)\b",
    r"\banalyze (my |the )?screen\b",
    r"\bwhat('?s| is) this\b",
]


def capture_screen() -> Optional[str]:
    """Capture the current screen to a temp file. Returns path or None."""
    try:
        path = Path(tempfile.mkdtemp()) / "screen.png"
        subprocess.run(
            ["screencapture", "-x", "-C", str(path)],
            timeout=5,
            check=True,
        )
        if path.exists() and path.stat().st_size > 1000:
            return str(path)
    except Exception as ex:
        logger.warning(f"ScreenAwareness: capture failed: {ex}")
    return None


def analyze_with_vlm(image_path: str, query: str = "What is shown on this screen?") -> str:
    """Send screenshot to VLM for analysis."""
    import base64
    import requests
    from packages.config import settings

    try:
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()

        response = requests.post(
            f"{settings.OLLAMA_HOST}/api/generate",
            json={
                "model": settings.VISION_MODEL_NAME,
                "prompt": query,
                "images": [img_b64],
                "stream": False,
                "options": {"num_predict": 200, "temperature": 0.3},
            },
            timeout=30,
        )
        if response.ok:
            return response.json().get("response", "Could not analyze the screen.")
        return f"VLM request failed: {response.status_code}"
    except Exception as ex:
        return f"Screen analysis unavailable: {ex}"


class ScreenAwarenessSkill(Skill):
    @property
    def name(self) -> str:
        return "screen_awareness"

    def can_handle(self, ctx: SkillContext) -> bool:
        text = (ctx.message or "").lower().strip()
        return any(re.search(p, text) for p in _TRIGGERS)

    def execute(self, ctx: SkillContext) -> dict:
        text = (ctx.message or "").lower().strip()

        path = capture_screen()
        if not path:
            return {
                "response": "I couldn't capture the screen, sir. Screen recording permissions may be needed.",
                "action": "screen_awareness",
            }

        # Tailor the VLM query based on what the user asked
        if "error" in text:
            query = "What error or issue is shown on this screen? Describe it concisely."
        elif "summarize" in text:
            query = "Summarize what is shown on this screen in 2-3 sentences."
        elif "read" in text:
            query = "Read and transcribe the main text content visible on this screen."
        else:
            query = "Describe what is shown on this screen concisely. Focus on the main content and any errors or important information."

        logger.info(f"ScreenAwareness: analyzing screenshot at {path}")
        analysis = analyze_with_vlm(path, query)

        # Clean up
        try:
            Path(path).unlink()
        except Exception:
            pass

        return {
            "response": analysis,
            "action": "screen_awareness",
            "intent": "screen_analysis",
        }
