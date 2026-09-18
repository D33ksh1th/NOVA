"""Handles greetings and capability queries instantly without LLM."""

import re
import random
import time
from services.skills.base import Skill, SkillContext

_CAPABILITY_TRIGGERS = [
    r"\bwhat can you do\b",
    r"\bwhat are your (capabilities|features|abilities)\b",
    r"\bwhat do you do\b",
    r"\btell me about yourself\b",
    r"\bwho are you\b",
    r"\bwhat are you\b",
    r"\bhelp me\b",
    r"\bshow (me )?your (skills|capabilities)\b",
    r"\bintroduce yourself\b",
]

_GREETING_TRIGGERS = [
    r"^(hi|hey|hello|hola|yo|howdy|sup)[\s!?.]*$",
    r"^good\s*(morning|afternoon|evening|night)[\s!?.]*$",
    r"^what'?s\s*up[\s!?.]*$",
    r"^how are you",
    r"^how'?s it going",
    r"^how do you do",
    r"^hey (nova|matrix|there)",
]

_PERSONA_TRIGGERS = [
    r"\bswitch (to |voice )?(jarvis|friday|devi)\b",
    r"\buse (jarvis|friday|devi)( voice)?\b",
    r"\bchange voice (to )?(jarvis|friday|devi)\b",
    r"\bset (voice |persona )?(to )?(jarvis|friday|devi)\b",
    r"\b(jarvis|friday|devi) (mode|voice|persona)\b",
]

CAPABILITIES_RESPONSE = (
    "I'm Nova, your personal AI sentinel. Here's what I can do: "
    "Chat and answer questions. "
    "Run security scans on your network and hosts. "
    "Detect and identify faces via camera. "
    "Recognize your voice and greet you by name. "
    "Check weather, time, and system info. "
    "Read and send Gmail. "
    "Set reminders. "
    "Run shell commands and manage files. "
    "Write and explain code. "
    "Search the web. "
    "Control music playback. "
    "What would you like to do?"
)


def _greeting_response() -> str:
    hour = int(time.strftime("%H"))
    try:
        from services.voice.tts import KokoroSpeechSynthesizer
        persona = getattr(KokoroSpeechSynthesizer, '_active_persona', 'jarvis')
    except Exception:
        persona = "jarvis"
    addr = "sir" if persona == "jarvis" else "boss"

    if hour < 12:
        period = "morning"
    elif hour < 17:
        period = "afternoon"
    else:
        period = "evening"
    return random.choice([
        f"Good {period}, {addr}. All systems operational. How may I assist?",
        f"Good {period}, {addr}. Standing by for your instructions.",
        f"Good {period}, {addr}. What can I do for you?",
    ])


class CapabilitiesSkill(Skill):
    @property
    def name(self) -> str:
        return "capabilities"

    def can_handle(self, ctx: SkillContext) -> bool:
        text = (ctx.message or "").lower().strip()
        if any(re.search(p, text) for p in _CAPABILITY_TRIGGERS):
            return True
        if any(re.search(p, text) for p in _GREETING_TRIGGERS):
            return True
        if any(re.search(p, text) for p in _PERSONA_TRIGGERS):
            return True
        return False

    def execute(self, ctx: SkillContext) -> dict:
        text = (ctx.message or "").lower().strip()

        # Persona switch
        for p in _PERSONA_TRIGGERS:
            match = re.search(p, text)
            if match:
                persona = match.group(match.lastindex or 0)
                return self._switch_persona(persona)

        if any(re.search(p, text) for p in _GREETING_TRIGGERS):
            return {
                "response": _greeting_response(),
                "action": "greeting",
                "intent": "greeting",
            }
        return {
            "response": CAPABILITIES_RESPONSE,
            "action": "capabilities",
            "intent": "help",
        }

    def _switch_persona(self, persona: str) -> dict:
        from services.voice.tts import KokoroSpeechSynthesizer
        personas = {
            "jarvis": {"voice": "bm_lewis", "speed": 0.94},
            "friday": {"voice": "bf_emma", "speed": 0.98},
            "devi": {"voice": "hf_alpha", "speed": 1.0},
        }
        key = persona.strip().lower()
        p = personas.get(key, personas["jarvis"])
        try:
            from packages.registry import registry
            registry.voice_engine.synthesizer.kokoro_voice = p["voice"]
            registry.voice_engine.synthesizer.kokoro_speed = p["speed"]
        except Exception:
            pass
        KokoroSpeechSynthesizer._active_persona = key
        addr = {"jarvis": "sir", "friday": "boss", "devi": "sir"}.get(key, "sir")
        return {
            "response": f"Voice switched to {key.upper()}. At your service, {addr}.",
            "action": "persona_switch",
            "intent": "persona",
            "data": {"persona": key, "voice": p["voice"]},
        }
