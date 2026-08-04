"""
Voice Identity Skill

Answers queries about enrolled voice profiles:
  - "am I enrolled?"
  - "what is my role?"
  - "list enrolled voices"
  - "who is the admin?"
  - "is voice recognition on?"
"""
import re
from typing import Optional
from services.skills.base import Skill, SkillContext


_TRIGGERS = [
    r"\bam i enrolled\b",
    r"\bis my voice enrolled\b",
    r"\bwhat is my role\b",
    r"\bwhat'?s my role\b",
    r"\bmy voice role\b",
    r"\blist (enrolled )?voices\b",
    r"\bwho(se)? (is |are )?(the )?enrolled\b",
    r"\bwho is (the )?admin\b",
    r"\benrolled (voice|profile|speaker)s?\b",
    r"\bvoice (recognition|identity) (status|on|off|enabled|disabled)\b",
    r"\bis voice recognition (on|off|enabled|disabled)\b",
    r"\bshow (my )?voice profile\b",
]


class VoiceIdentitySkill(Skill):

    def __init__(self, speaker_registry, voice_recognition_enabled_fn=None):
        self._registry = speaker_registry
        # Callable that returns current bool for voice recognition toggle.
        self._is_recognition_enabled = voice_recognition_enabled_fn or (lambda: True)

    @property
    def name(self) -> str:
        return "voice_identity"

    def can_handle(self, ctx: SkillContext) -> bool:
        text = (ctx.message or "").lower().strip()
        return any(re.search(p, text) for p in _TRIGGERS)

    def execute(self, ctx: SkillContext) -> dict:
        text = (ctx.message or "").lower().strip()
        profiles = self._registry.all_profiles()
        admin = self._registry.get_admin()
        recognition_on = self._is_recognition_enabled()

        # "list voices" queries
        if re.search(r"\blist (enrolled )?voices\b|\benrolled (voice|profile|speaker)s?\b", text):
            if not profiles:
                return {
                    "response": "No voice profiles are enrolled yet. Say 'recognize my voice' to enroll.",
                    "action": "voice_identity",
                }
            lines = []
            for p in profiles:
                tag = " [Admin]" if p.role == "admin" else ""
                lines.append(f"• {p.name}{tag} — {p.samples} samples")
            return {
                "response": "Enrolled voice profiles:\n" + "\n".join(lines),
                "action": "voice_identity",
            }

        # "who is admin" query
        if re.search(r"\bwho is (the )?admin\b", text):
            if admin:
                return {
                    "response": f"{admin.name} is the current admin voice.",
                    "action": "voice_identity",
                }
            return {
                "response": "No admin voice is set yet. Complete enrollment and say yes when asked to set admin.",
                "action": "voice_identity",
            }

        # "is voice recognition on/off" query
        if re.search(r"\bvoice recognition\b|\bis voice recognition\b", text):
            state = "enabled" if recognition_on else "disabled"
            return {
                "response": f"Voice recognition is currently {state}.",
                "action": "voice_identity",
            }

        # "am I enrolled / what is my role"
        # Try to get speaker hint from context metadata
        speaker_hint: Optional[str] = None
        if isinstance(ctx.context, dict):
            speaker_hint = str(ctx.context.get("speaker") or "").strip() or None

        if speaker_hint:
            profile = self._registry.get(speaker_hint)
            if profile:
                return {
                    "response": f"Yes, {profile.name} is enrolled with the role: {profile.role}.",
                    "action": "voice_identity",
                }
            return {
                "response": f"No enrolled profile found for '{speaker_hint}'.",
                "action": "voice_identity",
            }

        if not profiles:
            return {
                "response": "No voices are enrolled yet. Say 'recognize my voice' to start enrollment.",
                "action": "voice_identity",
            }

        # Generic summary
        names = ", ".join(p.name for p in profiles)
        admin_line = f" The admin is {admin.name}." if admin else " No admin is set."
        return {
            "response": f"Enrolled voices: {names}.{admin_line} Voice recognition is {'on' if recognition_on else 'off'}.",
            "action": "voice_identity",
        }
