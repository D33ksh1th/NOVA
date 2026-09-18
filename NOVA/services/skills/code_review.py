"""Code review skill — review git changes via LLM.

"review my last commit", "check my changes", "what did I change"
"""

import re
import subprocess
from packages.common import logger
from services.skills.base import Skill, SkillContext


_TRIGGERS = [
    r"\breview (my |the )?(last |latest )?(commit|changes|diff|code)\b",
    r"\bcheck (my |the )?(last |latest )?(commit|changes|diff)\b",
    r"\bwhat did i change\b",
    r"\bgit diff\b",
    r"\bshow (my |the )?(last |latest )?changes\b",
]


def get_git_diff(cwd: str = ".") -> str:
    """Get staged + unstaged diff, or last commit diff."""
    try:
        # Try staged + unstaged first
        result = subprocess.run(
            ["git", "diff", "HEAD", "--stat", "--patch"],
            capture_output=True, text=True, timeout=10, cwd=cwd,
        )
        if result.stdout.strip():
            return result.stdout.strip()[:3000]

        # Fall back to last commit
        result = subprocess.run(
            ["git", "log", "-1", "--stat", "--patch"],
            capture_output=True, text=True, timeout=10, cwd=cwd,
        )
        return result.stdout.strip()[:3000] if result.stdout.strip() else "No git changes found."
    except Exception as ex:
        return f"Git error: {ex}"


class CodeReviewSkill(Skill):
    @property
    def name(self) -> str:
        return "code_review"

    def can_handle(self, ctx: SkillContext) -> bool:
        text = (ctx.message or "").lower().strip()
        return any(re.search(p, text) for p in _TRIGGERS)

    def execute(self, ctx: SkillContext) -> dict:
        diff = get_git_diff()
        if "No git changes" in diff or "Git error" in diff:
            return {"response": f"{diff}", "action": "code_review"}

        try:
            from services.llm import LLMClient, LLMRequest
            from packages.config import settings
            client = LLMClient()
            prompt = f"""Review this git diff concisely. Focus on:
1. What changed (1 sentence)
2. Any bugs or security issues (if any)
3. One improvement suggestion

```diff
{diff[:2000]}
```"""
            response = client.generate(LLMRequest(prompt=prompt, model=settings.CHAT_MODEL))
            return {
                "response": response.text,
                "action": "code_review",
                "data": {"type": "code_review", "diff_lines": diff.count("\n")},
            }
        except Exception as ex:
            return {
                "response": f"Here are the changes:\n```\n{diff[:500]}\n```",
                "action": "code_review",
                "data": {"type": "raw_diff"},
            }
