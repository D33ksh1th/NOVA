"""Clipboard intelligence — analyze clipboard content on demand.

"what did I copy", "explain this error", "review this code",
"analyze clipboard", "summarize what I copied"
"""

import re
import subprocess
from packages.common import logger
from services.skills.base import Skill, SkillContext

_TRIGGERS = [
    r"\bwhat did i copy\b",
    r"\bwhat('?s| is) (in |on )?(my )?clipboard\b",
    r"\banalyze (my )?clipboard\b",
    r"\bexplain (this |the )?(error|code|text)\b",
    r"\breview (this |the )?code\b",
    r"\bsummarize what i copied\b",
    r"\bcheck (my )?clipboard\b",
]


def get_clipboard() -> str:
    """Get macOS clipboard content."""
    try:
        result = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=3)
        return result.stdout.strip()
    except Exception:
        return ""


def classify_content(text: str) -> str:
    """Classify clipboard content type."""
    if not text:
        return "empty"
    if any(kw in text.lower() for kw in ["traceback", "error", "exception", "failed", "errno"]):
        return "error"
    if any(kw in text for kw in ["def ", "class ", "import ", "function ", "const ", "var ", "let ", "{", "}"]):
        return "code"
    if text.startswith("http://") or text.startswith("https://"):
        return "url"
    if len(text) > 500:
        return "long_text"
    return "text"


class ClipboardSkill(Skill):
    @property
    def name(self) -> str:
        return "clipboard"

    def can_handle(self, ctx: SkillContext) -> bool:
        text = (ctx.message or "").lower().strip()
        return any(re.search(p, text) for p in _TRIGGERS)

    def execute(self, ctx: SkillContext) -> dict:
        content = get_clipboard()
        if not content:
            return {
                "response": "Your clipboard is empty, sir.",
                "action": "clipboard",
            }

        content_type = classify_content(content)
        preview = content[:200] + ("..." if len(content) > 200 else "")

        if content_type == "error":
            return self._analyze_with_llm(content, "Explain this error concisely. What caused it and how to fix it.")

        if content_type == "code":
            return self._analyze_with_llm(content, "Review this code briefly. Mention any issues or improvements.")

        if content_type == "url":
            return {
                "response": f"You copied a URL: {content[:100]}",
                "action": "clipboard",
                "data": {"type": "url", "content": content},
            }

        if content_type == "long_text":
            return self._analyze_with_llm(content, "Summarize this text in 2 sentences.")

        return {
            "response": f"Your clipboard contains: {preview}",
            "action": "clipboard",
            "data": {"type": content_type, "preview": preview},
        }

    def _analyze_with_llm(self, content: str, instruction: str) -> dict:
        try:
            from services.llm import LLMClient, LLMRequest
            from packages.config import settings
            client = LLMClient()
            prompt = f"{instruction}\n\n```\n{content[:2000]}\n```"
            response = client.generate(LLMRequest(prompt=prompt, model=settings.CHAT_MODEL))
            return {
                "response": response.text,
                "action": "clipboard",
                "data": {"type": classify_content(content), "analyzed": True},
            }
        except Exception as ex:
            return {
                "response": f"Clipboard has content but analysis failed: {ex}",
                "action": "clipboard",
            }
