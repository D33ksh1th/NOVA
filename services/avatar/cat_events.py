"""
NOVA Cat Avatar Event Broadcaster

This module bridges the Python NOVA backend with the macOS Swift companion app.
It broadcasts state change events that trigger cat animations in real-time.

Usage:
    from services.avatar.cat_events import CatEventBroadcaster
    
    broadcaster = CatEventBroadcaster()
    
    # Trigger animations from backend events
    broadcaster.user_started_listening()
    broadcaster.started_thinking()
    broadcaster.started_speaking("Hello, I'm thinking about your request")
    broadcaster.user_recognized("Deekshith")
    broadcaster.error("Something went wrong")
"""

import json
import asyncio
from typing import Optional, List
from datetime import datetime
from enum import Enum
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


class CatAnimationEvent(str, Enum):
    """Avatar animation trigger events."""
    
    # Listen/Understand
    LISTENING_STARTED = "listening_started"
    LISTENING_COMPLETE = "listening_complete"
    
    # Think/Process
    THINKING_STARTED = "thinking_started"
    THINKING_COMPLETE = "thinking_complete"
    
    # Speak/Respond
    SPEAKING_STARTED = "speaking_started"
    SPEAKING_COMPLETE = "speaking_complete"
    
    # Recognition
    USER_RECOGNIZED = "user_recognized"
    
    # Emotional
    HAPPY = "happy"
    CONFUSED = "confused"
    
    # System
    ERROR = "error"
    IDLE = "idle"


@dataclass
class CatEvent:
    """Event data sent to companion app."""
    event: str
    text: Optional[str] = None
    user: Optional[str] = None
    message: Optional[str] = None
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()
    
    def to_json(self) -> str:
        """Serialize to JSON for transmission."""
        data = {
            "event": self.event,
            "timestamp": self.timestamp,
        }
        
        if self.text:
            data["text"] = self.text
        if self.user:
            data["user"] = self.user
        if self.message:
            data["message"] = self.message
        
        return json.dumps(data)


class CatEventBroadcaster:
    """Broadcasts events to connected cat companion instances."""
    
    def __init__(self, companion_url: str = "http://127.0.0.1:8001"):
        """
        Initialize broadcaster.
        
        Args:
            companion_url: Base URL of macOS companion app (default: localhost:8001)
        """
        self.companion_url = companion_url
        self.subscribers: List[str] = []
        self.event_history: List[CatEvent] = []
    
    def _record_event(self, event: CatEvent):
        """Keep history of recent events."""
        self.event_history.append(event)
        if len(self.event_history) > 100:
            self.event_history.pop(0)
    
    async def broadcast(self, event: CatEvent):
        """
        Broadcast event to all connected companions.
        
        Args:
            event: CatEvent to broadcast
        """
        self._record_event(event)
        
        # In production: Send via WebSocket or HTTP to companion app
        # For now: Log locally
        logger.info(f"🐱 Cat Event: {event.event}")
        if event.text:
            logger.info(f"   Text: {event.text}")
        if event.user:
            logger.info(f"   User: {event.user}")
    
    # MARK: - Animation Triggers (Call these from voice/brain services)
    
    async def user_started_listening(self):
        """Trigger listening animation."""
        event = CatEvent(event=CatAnimationEvent.LISTENING_STARTED)
        await self.broadcast(event)
    
    async def user_stopped_listening(self):
        """Listening complete."""
        event = CatEvent(event=CatAnimationEvent.LISTENING_COMPLETE)
        await self.broadcast(event)
    
    async def started_thinking(self):
        """Trigger thinking animation."""
        event = CatEvent(event=CatAnimationEvent.THINKING_STARTED)
        await self.broadcast(event)
    
    async def finished_thinking(self):
        """Thinking complete."""
        event = CatEvent(event=CatAnimationEvent.THINKING_COMPLETE)
        await self.broadcast(event)
    
    async def started_speaking(self, text: str, duration: float = 4.0):
        """
        Trigger speaking animation with response text.
        
        Args:
            text: Text the cat will "speak"
            duration: How long the speech bubble shows (seconds)
        """
        event = CatEvent(
            event=CatAnimationEvent.SPEAKING_STARTED,
            text=text
        )
        await self.broadcast(event)
    
    async def finished_speaking(self):
        """Speaking complete."""
        event = CatEvent(event=CatAnimationEvent.SPEAKING_COMPLETE)
        await self.broadcast(event)
    
    async def user_recognized(self, username: str):
        """
        Trigger happy animation when user is recognized.
        
        Args:
            username: Name of recognized user
        """
        event = CatEvent(
            event=CatAnimationEvent.USER_RECOGNIZED,
            user=username
        )
        await self.broadcast(event)
    
    async def show_confusion(self, error_msg: str = ""):
        """
        Trigger confused animation on error.
        
        Args:
            error_msg: Error message to display
        """
        event = CatEvent(
            event=CatAnimationEvent.CONFUSED,
            message=error_msg
        )
        await self.broadcast(event)
    
    async def show_happiness(self, reason: str = ""):
        """
        Trigger happy animation.
        
        Args:
            reason: Why the cat is happy (optional)
        """
        event = CatEvent(
            event=CatAnimationEvent.HAPPY,
            message=reason
        )
        await self.broadcast(event)
    
    async def return_to_idle(self):
        """Return to idle state."""
        event = CatEvent(event=CatAnimationEvent.IDLE)
        await self.broadcast(event)


# Global instance (singleton pattern)
_cat_broadcaster: Optional[CatEventBroadcaster] = None


def get_cat_broadcaster() -> CatEventBroadcaster:
    """
    Get or create global cat broadcaster instance.
    
    Usage:
        broadcaster = get_cat_broadcaster()
        await broadcaster.started_thinking()
    """
    global _cat_broadcaster
    
    if _cat_broadcaster is None:
        _cat_broadcaster = CatEventBroadcaster()
    
    return _cat_broadcaster


# Example integration with voice pipeline
class ExampleUsage:
    """
    How to integrate with existing NOVA services.
    
    # In services/voice/tts.py:
    
    from services.avatar.cat_events import get_cat_broadcaster
    
    async def synthesize(self, text: str, voice_mode: str = "human"):
        broadcaster = get_cat_broadcaster()
        
        # Trigger speaking animation
        await broadcaster.started_speaking(text)
        
        # ... do TTS ...
        audio = piper.synthesize(text)
        
        # Animation ends when TTS finishes
        await broadcaster.finished_speaking()
        return audio
    
    
    # In services/brain/engine.py:
    
    from services.avatar.cat_events import get_cat_broadcaster
    
    async def think(self, question: str):
        broadcaster = get_cat_broadcaster()
        
        await broadcaster.started_thinking()
        
        # ... LLM inference ...
        response = await llm.generate(question)
        
        await broadcaster.finished_thinking()
        await broadcaster.started_speaking(response)
        
        return response
    
    
    # In services/gateway/routes.py:
    
    from services.avatar.cat_events import get_cat_broadcaster
    
    @router.post("/voice/recognize")
    async def recognize_voice(request: VoiceRecognitionRequest):
        broadcaster = get_cat_broadcaster()
        
        # Trigger listening
        await broadcaster.user_started_listening()
        
        # ... process audio ...
        user = identify_speaker(audio)
        
        if user:
            await broadcaster.user_recognized(user)
        
        await broadcaster.user_stopped_listening()
    """
    pass
