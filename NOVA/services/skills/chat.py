"""
Chat Skill

Handles all conversational interactions.
"""

from services.skills.base import Skill
from services.skills.base import SkillContext
from services.brain.intent import Intent
from packages.config import settings
import re

from services.llm.models import LLMRequest


_AFFIRMATION_REPLIES = {
    "yes",
    "y",
    "yeah",
    "yep",
    "sure",
    "ok",
    "okay",
    "please do",
    "go ahead",
    "continue",
}

_NEGATIVE_REPLIES = {
    "no",
    "n",
    "nope",
    "not that",
    "not cve",
}

_GREETING_REPLIES = {
    "hi",
    "hey",
    "hello",
    "yo",
    "good morning",
    "good afternoon",
    "good evening",
}


def _is_cve_continuation(context: dict, message: str) -> bool:
    if not _is_short_affirmation(message):
        return False
    history = str((context or {}).get("conversation_history") or "").lower()
    return "cve" in history or "common vulnerabilities and exposures" in history


def _is_short_affirmation(message: str) -> bool:
    text = re.sub(r"\s+", " ", (message or "").strip().lower())
    return text in _AFFIRMATION_REPLIES


def _normalized_short_text(message: str) -> str:
    return re.sub(r"\s+", " ", (message or "").strip().lower())


def _is_short_negative(message: str) -> bool:
    return _normalized_short_text(message) in _NEGATIVE_REPLIES


def _is_short_greeting(message: str) -> bool:
    return _normalized_short_text(message) in _GREETING_REPLIES


def _has_cve_clarification_context(context: dict) -> bool:
    history = str((context or {}).get("conversation_history") or "").lower()
    return (
        "clarification" in history
        and (
            "cve" in history
            or "common vulnerabilities and exposures" in history
        )
    )


class ChatSkill(Skill):

    def __init__(
        self,
        llm,
        prompt_builder,
        knowledge,
        memory_context,
        context_engine,
    ):

        self.llm = llm
        self.prompt_builder = prompt_builder
        self.knowledge = knowledge
        self.memory_context = memory_context
        self.context_engine = context_engine

    @property
    def name(self):

        return "chat"

    def can_handle(self, ctx: SkillContext) -> bool:
        return ctx.intent == Intent.CHAT

    def execute(self, ctx: SkillContext) -> dict:
        message = ctx.message
        # Use upstream Brain context so conversation history is preserved.
        context = dict(ctx.context or {})
        if not context:
            context = self.context_engine.build(message)

        if _is_cve_continuation(context, message):
            return {
                "action": "chat",
                "intent": ctx.intent.value,
                "response": (
                    "Great. CVE is the public ID system for known security flaws. "
                    "Quick flow: CNA discovers/report receives issue -> CVE ID assigned -> "
                    "details published with affected products and references. "
                    "To use CVEs effectively: track CVSS score, affected version range, "
                    "exploit status, and available patch. "
                    "If you want, I can next explain CVE vs CVSS in 60 seconds."
                ),
            }

        if _has_cve_clarification_context(context) and _is_short_negative(message):
            return {
                "action": "chat",
                "intent": ctx.intent.value,
                "response": (
                    "Understood. Not CVE. Tell me what you want C V E to mean, "
                    "or ask your next question directly."
                ),
            }

        if _has_cve_clarification_context(context) and _is_short_greeting(message):
            return {
                "action": "chat",
                "intent": ctx.intent.value,
                "response": "Hey. Ready when you are. What do you want to do next?",
            }

        user_message = message
        if _is_short_affirmation(message) and context.get("conversation_history"):
            user_message = (
                "The user replied affirmatively to the previous turn. "
                "Continue the same topic and answer the previous assistant question directly. "
                f"User reply: {message}"
            )

        memory = self.memory_context.build()
        knowledge = self.knowledge.search(message)

        prompt = self.prompt_builder.build(
            user_message=user_message,
            memory=memory,
            context=context,
            knowledge=knowledge,
        )

        response = self.llm.generate(
            LLMRequest(
                prompt=prompt,
                model=settings.CHAT_MODEL,
            )
        )

        return {
            "action": "chat",
            "intent": ctx.intent.value,
            "response": response.text,
        }