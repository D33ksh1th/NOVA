"""Core models for the modular voice pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class VoiceInputFrame:
    source: str
    source_type: str = "text"
    speak: bool = True
    force_wake: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VoiceActivityResult:
    speech_detected: bool
    confidence: float
    energy: float
    backend: str = "text-vad"


@dataclass
class LanguageDetectionResult:
    language: str = "en"
    confidence: float = 0.6
    backend: str = "heuristic"


@dataclass
class EmotionDetectionResult:
    emotion: str = "neutral"
    confidence: float = 0.5
    backend: str = "heuristic"


@dataclass
class VoiceProfile:
    speed: float = 1.0
    pitch: float = 0.0
    warmth: float = 0.5
    pause_strength: float = 0.5
    emotion: str = "neutral"
    voice: str = ""


@dataclass
class SpeakerProfile:
    id: str
    name: str
    embedding: str
    samples: int = 0
    role: str = "user"
    created_at: str = ""
    updated_at: str = ""


@dataclass
class SpeakerRecognitionResult:
    speaker: str = "unknown"
    role: str = "unknown"
    confidence: float = 0.0
    recognized: bool = False
    backend: str = "heuristic"


@dataclass
class SpeechPlan:
    text: str
    style: str = "natural"
    rate: int = 180
    pitch: int = 50
    pauses: List[str] = field(default_factory=list)
    emphasis: List[str] = field(default_factory=list)
    chunks: List[str] = field(default_factory=list)
    start_delay_ms: int = 0
    pause_ms: int = 120
    voice_profile: Optional[dict] = None


@dataclass
class ConversationTurnState:
    interrupted: bool = False
    should_listen: bool = True
    active_speaker: Optional[str] = None
    turn_count: int = 0
