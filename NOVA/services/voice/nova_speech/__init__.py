"""NOVA Speech Layer — JARVIS-style fully-local voice assistant."""

from .ears import NovaEars
from .greet import NovaGreet
from .voice import NovaVoice
from .fx import NovaFX
from .persona import NovaPersona
from .skills import NovaSkills
from .orchestrator import NovaOrchestrator

__all__ = [
    "NovaEars",
    "NovaGreet",
    "NovaVoice",
    "NovaFX",
    "NovaPersona",
    "NovaSkills",
    "NovaOrchestrator",
]
