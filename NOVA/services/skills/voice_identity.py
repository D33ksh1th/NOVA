"""
Voice Identity Skill

Answers queries about enrolled voice profiles:
  - "am I enrolled?"
  - "what is my role?"
  - "list enrolled voices"
  - "who is the admin?"
  - "is voice recognition on?"
  - "recognize me" (also triggers face recognition)
"""
import re
from typing import Optional
from packages.common import logger
from services.skills.base import Skill, SkillContext


_TRIGGERS = [
    r"\bam i enrolled\b",
    r"\bis my voice enrolled\b",
    r"\bwhat is my role\b",
    r"\bwhat'?s my role\b",
    r"\bmy voice role\b",
    r"\blist (enrolled )?voices\b",
    r"\bwho(se)? (is |are )?(the )?(enrolled|registered)\b",
    r"\bwho is (the )?admin\b",
    r"\benrolled (voice|profile|speaker|user)s?\b",
    r"\bvoice (recognition|identity) (status|on|off|enabled|disabled)\b",
    r"\bis voice recognition (on|off|enabled|disabled)\b",
    r"\bshow (my )?voice profile\b",
    r"\bwhat are the enrolled\b",
    r"\bshow enrolled\b",
    r"\bhow many (voice |speaker )?profiles?\b",
    r"\bregistered (voice|speaker|user)s?\b",
    r"\brecognize me\b",
    r"\bidentify me\b",
    r"\bdo you (know|recognize|recognise) (me|my voice|who i am)\b",
    r"\bwho am i\b",
    r"\bwhat('?s| is) my name\b",
    r"\bdo you know who i am\b",
    r"\bcan you (recognize|recognise|identify) me\b",
]


class VoiceIdentitySkill(Skill):

    def __init__(self, speaker_registry, voice_recognition_enabled_fn=None):
        self._registry = speaker_registry
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
        if re.search(r"\blist (enrolled )?voices\b|\benrolled (voice|profile|speaker|user)s?\b|\bwhat are the enrolled\b|\bshow enrolled\b|\bhow many\b|\bregistered\b", text):
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

        # "am I enrolled / what is my role / recognize me / who am i"
        speaker_hint: Optional[str] = None
        if isinstance(ctx.context, dict):
            speaker_hint = str(ctx.context.get("speaker") or "").strip() or None

        # "recognize me" / "who am i" / "identify me" — attempt face + voice recognition
        if re.search(r"\brecognize me\b|\bidentify me\b|\bwho am i\b|\bdo you (know|recognize|recognise)\b|\bcan you (recognize|recognise|identify)\b|\bwhat('?s| is) my name\b", text):
            face_result = self._try_face_recognition()
            if face_result and face_result.get("recognized"):
                name = face_result["name"]
                role = face_result.get("role", "user")
                confidence = face_result.get("confidence", 0.0)
                role_text = f" You are the {role}." if role == "admin" else ""
                return {
                    "response": f"I recognize you, {name}! (face match, confidence: {confidence:.0%}){role_text}",
                    "action": "voice_identity",
                }
            if speaker_hint:
                profile = self._registry.get(speaker_hint)
                if profile:
                    role_text = f" You are the {profile.role}." if profile.role == "admin" else ""
                    return {
                        "response": f"I recognize you, {profile.name}.{role_text}",
                        "action": "voice_identity",
                    }
            face_error = face_result.get("error", "") if face_result else "camera unavailable"
            if not recognition_on:
                return {
                    "response": f"Voice recognition is disabled. Face check: {face_error}. Enable voice recognition or try better lighting for face ID.",
                    "action": "voice_identity",
                }
            return {
                "response": f"I couldn't match you. Voice: no match. Face: {face_error}. Try re-enrolling by saying 'enroll my voice' or enroll your face in the Vision tab.",
                "action": "voice_identity",
            }

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

    def _try_face_recognition(self) -> Optional[dict]:
        """Capture from camera and attempt face recognition."""
        try:
            from packages.registry import registry
            tool = registry.tool_registry.find_by_name("VisionTool")
            if tool is None or not hasattr(tool, "face_identity"):
                return {"recognized": False, "error": "vision tool unavailable"}
            if not bool(getattr(tool, "face_recognition_enabled", True)):
                return {"recognized": False, "error": "face recognition disabled"}
            cap = tool.camera.capture()
            if not cap.success:
                return {"recognized": False, "error": f"camera capture failed: {cap.error}"}
            result = tool.face_identity.recognize_from_image(cap.path)
            return {
                "recognized": bool(result.recognized),
                "name": result.name or "",
                "role": result.role or "",
                "confidence": float(result.confidence or 0.0),
                "error": result.error or "",
            }
        except Exception as ex:
            logger.warning(f"VoiceIdentitySkill: face recognition attempt failed: {ex}")
            return {"recognized": False, "error": str(ex)}
