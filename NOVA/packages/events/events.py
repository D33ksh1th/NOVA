"""
All NOVA Events — subject taxonomy: nova.<domain>.<action>

Every event in the system should be declared here.
"""

from enum import Enum


class Event(str, Enum):
    # --- Application lifecycle ---
    APP_STARTED = "nova.app.started"
    APP_STOPPED = "nova.app.stopped"

    # --- Voice pipeline ---
    VOICE_RECEIVED = "nova.voice.received"
    VOICE_UTTERANCE = "nova.voice.utterance"
    VOICE_WAKE_WORD = "nova.voice.wake_word"

    # --- Speech output ---
    SPEECH_REQUEST = "nova.speech.request"
    SPEECH_STARTED = "nova.speech.started"
    SPEECH_COMPLETED = "nova.speech.completed"
    SPEECH_INTERRUPTED = "nova.speech.interrupted"

    # --- Brain / reasoning ---
    THOUGHT_CREATED = "nova.brain.thought_created"
    RESPONSE_READY = "nova.brain.response_ready"

    # --- Memory ---
    MEMORY_STORED = "nova.memory.stored"
    MEMORY_RECALLED = "nova.memory.recalled"

    # --- Security ---
    SECURITY_SCAN_STARTED = "nova.security.scan_started"
    SECURITY_SCAN_COMPLETED = "nova.security.scan_completed"
    SECURITY_ANOMALY = "nova.security.anomaly"
    SECURITY_HEARTBEAT = "nova.security.heartbeat"

    # --- Avatar state ---
    AVATAR_LISTENING_STARTED = "nova.avatar.listening_started"
    AVATAR_LISTENING_COMPLETED = "nova.avatar.listening_completed"
    AVATAR_THINKING_STARTED = "nova.avatar.thinking_started"
    AVATAR_THINKING_COMPLETED = "nova.avatar.thinking_completed"
    AVATAR_SPEAKING_STARTED = "nova.avatar.speaking_started"
    AVATAR_SPEAKING_COMPLETED = "nova.avatar.speaking_completed"
    AVATAR_IDLE = "nova.avatar.idle"

    # --- Mail ---
    MAIL_RECEIVED = "nova.mail.received"
    MAIL_SEND_STARTED = "nova.mail.send_started"
    MAIL_SEND_COMPLETED = "nova.mail.send_completed"

    # --- Legacy aliases (deprecated, map to new names) ---
    GMAIL_NEW_MESSAGE = "nova.mail.received"
    GMAIL_SEND_STARTED = "nova.mail.send_started"
    GMAIL_SEND_COMPLETED = "nova.mail.send_completed"

    # --- Asset / infrastructure ---
    ASSET_DISCOVERED = "nova.asset.discovered"
    ASSET_DRIFT = "nova.asset.drift"

    # --- Initiative / proactive ---
    INITIATIVE_MORNING_BRIEF = "nova.initiative.morning_brief"
    INITIATIVE_EVENING_SUMMARY = "nova.initiative.evening_summary"
    NOTIFICATION_DELIVERED = "nova.notification.delivered"
    NOTIFICATION_BATCHED = "nova.notification.batch"

    # --- System ---
    SYSTEM_HEALTH = "nova.system.health"
    SYSTEM_ERROR = "nova.system.error"

    # --- Actions (Phase 7) ---
    ACTION_EXECUTED = "nova.action.executed"
    ACTION_PENDING = "nova.action.pending"
    ACTION_DENIED = "nova.action.denied"