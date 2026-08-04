"""
Gmail Skill — Jarvis-style email voice commands.

Handles:
  • "Read my emails" / "Any new mail?"
  • "Send email to X@Y.com subject Foo saying Bar"
  • "Send a message to X subject Foo body Bar"
  • "Check inbox" / "How many unread?"
"""

from __future__ import annotations

import re
from typing import Optional

from packages.common import logger
from services.skills.base import Skill, SkillContext


_READ_PATTERN = re.compile(
    r"(?:check|read|show|list|any|what|new|unread|open|how\s+many).{0,30}"
    r"(?:email|mail|inbox|message|gmail)",
    re.IGNORECASE,
)

_SEND_PATTERN = re.compile(
    r"(?:send|email|write|compose|draft)\s+(?:an?\s+)?(?:email|mail|message)?\s*"
    r"(?:to\s+)?(?P<to>[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})",
    re.IGNORECASE,
)


class GmailSkill(Skill):
    """Voice-controlled Gmail: read inbox + send email."""

    @property
    def name(self) -> str:
        return "gmail"

    def can_handle(self, ctx: SkillContext) -> bool:
        text = ctx.message.lower()
        return bool(
            _READ_PATTERN.search(text)
            or _SEND_PATTERN.search(text)
            or any(kw in text for kw in (
                "gmail", "inbox", "send email", "compose email",
                "email to", "mail to", "write to", "message to",
                "check mail", "any emails", "new emails",
                "unread", "check my email",
            ))
        )

    def execute(self, ctx: SkillContext) -> dict:
        try:
            from packages.registry import registry
            tool = registry.gmail_tool
        except Exception as ex:
            logger.error(f"GmailSkill: could not access registry — {ex}")
            return {
                "action": "gmail",
                "intent": "gmail_error",
                "response": "I couldn't reach the email service right now.",
            }

        if not tool.is_available():
            return {
                "action": "gmail",
                "intent": "gmail_unavailable",
                "response": (
                    "Gmail isn't connected yet. To set it up: download credentials.json "
                    "from Google Cloud Console, set GMAIL_CREDENTIALS_PATH in your .env, "
                    "then restart the backend and complete the OAuth flow."
                ),
            }

        send_match = _SEND_PATTERN.search(ctx.message)
        if send_match:
            return self._send(ctx.message, send_match.group("to"), tool)
        return self._read(tool)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def _read(self, tool) -> dict:
        from packages.config import settings
        msgs = tool.list_unread(max_results=settings.GMAIL_MAX_RESULTS)
        if not msgs:
            return {
                "action": "gmail_read",
                "intent": "gmail_inbox_empty",
                "response": "Your inbox is clear, sir. No unread messages.",
            }

        critical = [m for m in msgs if m.get("urgency") == "critical"]
        high = [m for m in msgs if m.get("urgency") == "high"]

        lines = [f"You have {len(msgs)} unread message{'s' if len(msgs) != 1 else ''}."]
        if critical:
            lines.append(f"🚨 {len(critical)} critical alert{'s' if len(critical) != 1 else ''}:")
            for m in critical[:3]:
                sender = m.get("from", "unknown").replace(r"<[^>]+>", "").strip()
                lines.append(f"  From {sender}: {m.get('subject', '')}")
        if high:
            lines.append(f"⚠️  {len(high)} high-priority message{'s' if len(high) != 1 else ''}:")
            for m in high[:3]:
                sender = m.get("from", "unknown").replace(r"<[^>]+>", "").strip()
                lines.append(f"  From {sender}: {m.get('subject', '')}")
        if not critical and not high:
            for m in msgs[:5]:
                emoji = m.get("urgency_emoji", "📬")
                sender = m.get("from", "?").split("<")[0].strip() or m.get("from", "?")
                lines.append(f"  {emoji} {sender}: {m.get('subject', '')}")

        return {
            "action": "gmail_read",
            "intent": "gmail_list_unread",
            "count": len(msgs),
            "critical_count": len(critical),
            "high_count": len(high),
            "messages": msgs,
            "response": "\n".join(lines),
        }

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    def _send(self, message: str, to_address: str, tool) -> dict:
        subject_match = re.search(
            r"subject[:\s]+(.+?)(?:\s+(?:body|saying|that|content)\b|$)",
            message, re.IGNORECASE
        )
        body_match = re.search(
            r"(?:body|saying|that|tell\s+(?:him|her|them)|content)[:\s]+(.+)$",
            message, re.IGNORECASE
        )

        subject = subject_match.group(1).strip() if subject_match else "Message from NOVA"
        body = body_match.group(1).strip() if body_match else message

        result = tool.send_email(to=to_address, subject=subject, body=body)
        if result.get("success"):
            return {
                "action": "gmail_send",
                "intent": "gmail_send_success",
                "to": to_address,
                "subject": subject,
                "response": f"Done. Email sent to {to_address} with subject '{subject}'.",
            }
        return {
            "action": "gmail_send",
            "intent": "gmail_send_failed",
            "response": f"I couldn't send that email. Error: {result.get('error', 'unknown')}",
        }
