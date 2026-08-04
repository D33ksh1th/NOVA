"""
Reflection rules.

These heuristics decide when NOVA should review and possibly
rewrite its first answer before returning it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ReflectionDecision:
    should_reflect: bool = False
    reason: str = ""
    confidence: float = 0.0
    issues: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ReflectionRules:
    """Heuristic review rules for answer quality and consistency."""

    def should_skip(self, action: str | None) -> bool:
        return action in {
            "time",
            "date",
            "weather",
            "location",
            "memory_store",
            "shell",
            "file",
            "calculator",
        }

    def assess(
        self,
        message: str,
        response: str,
        intent: str,
        action: str | None = None,
        memory: Optional[dict] = None,
        tool_result: Optional[dict] = None,
        plan_result: Optional[dict] = None,
    ) -> ReflectionDecision:
        text = (response or "").strip()
        prompt = message.lower().strip()
        issues: List[str] = []

        if not text:
            return ReflectionDecision(
                should_reflect=True,
                reason="empty_response",
                confidence=1.0,
                issues=["Response was empty."],
            )

        if self.should_skip(action):
            return ReflectionDecision(should_reflect=False, reason="tool_output")

        # Complex asks deserve a second look.
        if any(word in prompt for word in ["explain", "build", "create", "design", "teach", "how do i", "how to"]):
            issues.append("Complex request may need structure or missing details.")

        # Very short answers to complex prompts are usually under-specified.
        if len(text.split()) < 40 and any(word in prompt for word in ["explain", "build", "create", "teach", "how to"]):
            issues.append("Answer looks too short for the request.")

        # Memory consistency check: birth year mismatch is the most common,
        # low-risk contradiction to detect reliably.
        if memory:
            birth_year = memory.get("birth_year") if isinstance(memory, dict) else None
            if birth_year:
                match = re.search(r"\b(19|20)\d{2}\b", text)
                if match and match.group(0) != str(birth_year):
                    issues.append(
                        f"Possible memory contradiction: response mentions {match.group(0)} but memory says {birth_year}."
                    )

        # Example prompt quality checks.
        if "oauth" in prompt and "authentication protocol" in text.lower():
            issues.append("OAuth is usually described as an authorization framework, not an authentication protocol.")

        if "crud" in prompt and not any(term in text.lower() for term in ["database", "model", "route", "folder", "project structure"]):
            issues.append("CRUD response may be missing implementation structure.")

        if tool_result and isinstance(tool_result, dict):
            tool_response = str(tool_result.get("response", "")).strip()
            if tool_response and tool_response not in text:
                issues.append("Tool output should be preserved verbatim or summarized accurately.")

        if plan_result and isinstance(plan_result, dict):
            steps = plan_result.get("steps") or []
            if isinstance(steps, list) and len(steps) > 1 and "Next Steps" not in text:
                issues.append("Plan response may be missing a closing synthesis.")

        if not issues:
            return ReflectionDecision(
                should_reflect=False,
                reason="good_enough",
                confidence=0.5,
            )

        return ReflectionDecision(
            should_reflect=True,
            reason="; ".join(issues[:3]),
            confidence=min(0.95, 0.55 + (0.15 * len(issues))),
            issues=issues[:5],
            metadata={
                "intent": intent,
                "action": action,
            },
        )
