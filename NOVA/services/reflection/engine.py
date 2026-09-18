"""
Reflection Engine

Reviews NOVA's first answer and optionally rewrites it before
it is returned to the user.
"""

from __future__ import annotations

from typing import Any, Optional

from packages.common import logger
from services.reflection.rules import ReflectionRules


_REFLECTION_PROMPT = """You are NOVA's reflection engine.

Your job is to review the assistant's draft answer and improve it if needed.

Rules:
- Be strict, but do not over-edit good answers.
- Preserve factual tool output exactly when it is already correct.
- If the answer is already good, return it unchanged.
- If something is missing, rewrite the answer so it is clearer and more complete.
- Use memory only when it is directly relevant to the user's current request.
- Do not add unrelated personal details (for example name, vehicle, city, projects).
- Do not mention that you are reflecting or critiquing.
- Return only the final user-facing answer.

User request:
{message}

Draft answer:
{draft}

Known memory:
{memory}

Recent context:
{context}

Your improved final answer:"""


class ReflectionEngine:
    def __init__(self, model_manager):
        self.model_manager = model_manager
        self.rules = ReflectionRules()
        logger.info("Reflection Engine Initialized")

    def reflect(
        self,
        message: str,
        draft: str,
        intent: str,
        action: Optional[str] = None,
        memory: Optional[dict] = None,
        context: Optional[dict] = None,
        tool_result: Optional[dict] = None,
        plan_result: Optional[dict] = None,
    ) -> dict:
        decision = self.rules.assess(
            message=message,
            response=draft,
            intent=intent,
            action=action,
            memory=memory,
            tool_result=tool_result,
            plan_result=plan_result,
        )

        if not decision.should_reflect:
            return {
                "response": draft,
                "reflected": False,
                "reflection_reason": decision.reason,
            }

        reflection_context = _REFLECTION_PROMPT.format(
            message=message,
            draft=draft,
            memory=memory or {},
            context=context or {},
        )

        logger.info(
            f"Reflection Engine -> reviewing draft (reason={decision.reason})"
        )

        result = self.model_manager.generate(
            message="reflection review",
            prompt=reflection_context,
        )

        improved = result.text if hasattr(result, "text") else str(result)
        improved = improved.strip()

        if not improved:
            improved = draft

        return {
            "response": improved,
            "reflected": True,
            "reflection_reason": decision.reason,
            "reflection_issues": decision.issues,
            "reflection_confidence": decision.confidence,
        }
