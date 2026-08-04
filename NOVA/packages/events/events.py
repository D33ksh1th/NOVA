"""
All NOVA Events

Every event in the system should be declared here.
"""

from enum import Enum


class Event(str, Enum):

    APP_STARTED = "app.started"

    APP_STOPPED = "app.stopped"

    VOICE_RECEIVED = "voice.received"

    THOUGHT_CREATED = "brain.thought.created"

    MEMORY_STORED = "memory.stored"

    RESPONSE_READY = "response.ready"

    SECURITY_SCAN_STARTED = "security.scan.started"

    SECURITY_SCAN_COMPLETED = "security.scan.completed"

    AVATAR_LISTENING_STARTED = "avatar.listening.started"

    AVATAR_LISTENING_COMPLETED = "avatar.listening.completed"

    AVATAR_THINKING_STARTED = "avatar.thinking.started"

    AVATAR_THINKING_COMPLETED = "avatar.thinking.completed"

    AVATAR_SPEAKING_STARTED = "avatar.speaking.started"

    AVATAR_SPEAKING_COMPLETED = "avatar.speaking.completed"

    AVATAR_IDLE = "avatar.idle"

    GMAIL_NEW_MESSAGE = "gmail.new_message"

    GMAIL_SEND_STARTED = "gmail.send.started"

    GMAIL_SEND_COMPLETED = "gmail.send.completed"