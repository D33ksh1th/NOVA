"""
Main API routes for NOVA Gateway.
"""

import asyncio
import base64
import json
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List, Any

from packages.common import logger
from packages.events import Event, bus
from packages.registry import registry
from starlette.responses import StreamingResponse

router = APIRouter()

UI_INDEX = Path(__file__).resolve().parent / "ui" / "index.html"
COMPANION_INDEX = Path(__file__).resolve().parent / "ui" / "companion2.html"


def _suffix_for_mime_type(mime_type: Optional[str]) -> str:
    mime = str(mime_type or "").lower()
    if "wav" in mime:
        return ".wav"
    if "ogg" in mime:
        return ".ogg"
    if "mp4" in mime or "m4a" in mime:
        return ".m4a"
    if "mpeg" in mime or "mp3" in mime:
        return ".mp3"
    return ".bin"


def _materialize_audio_payload(audio_base64: Optional[str], audio_mime_type: Optional[str]) -> Optional[str]:
    if not audio_base64:
        logger.info("voice_text: no audio payload attached")
        return None
    raw_value = str(audio_base64).strip()
    if not raw_value:
        logger.info("voice_text: audio payload present but empty after trim")
        return None

    payload = raw_value.split(",", 1)[1] if raw_value.startswith("data:") and "," in raw_value else raw_value
    try:
        audio_bytes = base64.b64decode(payload)
    except Exception:
        logger.warning("voice_text: failed to decode base64 audio payload")
        return None
    if not audio_bytes:
        logger.warning("voice_text: decoded audio payload is empty")
        return None

    suffix = _suffix_for_mime_type(audio_mime_type)
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(audio_bytes)
        logger.info(
            "voice_text: materialized audio payload",
            mime_type=str(audio_mime_type or ""),
            bytes=len(audio_bytes),
            temp_path=tmp.name,
        )
        return tmp.name


# ==========================
# Schemas
# ==========================

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    intent: Optional[str] = None
    action: Optional[str] = None
    # Present only for multi-step plans
    plan_id: Optional[str] = None
    tasks_executed: Optional[int] = None
    steps: Optional[List[Any]] = None
    data: Optional[dict] = None
    initiative: Optional[dict] = None
    reflected: Optional[bool] = None
    reflection_reason: Optional[str] = None


class PlanRequest(BaseModel):
    goal: str


class PlanPreviewResponse(BaseModel):
    goal: str
    plan_id: str
    tasks: List[str]
    is_simple: bool


class VoiceTextRequest(BaseModel):
    text: str
    speak: bool = True
    speaker: Optional[str] = None
    audio_base64: Optional[str] = None
    audio_mime_type: Optional[str] = None
    voice_mode: Optional[str] = None
    voice_style: Optional[str] = None
    voice_rate: Optional[int] = None
    voice_pitch: Optional[int] = None
    voice_name: Optional[str] = None
    accent_profile: Optional[str] = None


class VoiceEnrollmentRequest(BaseModel):
    name: str
    samples: List[str]
    role: Optional[str] = None


class VoiceEnrollmentStartRequest(BaseModel):
    name: Optional[str] = None


class VoiceEnrollmentAnswerRequest(BaseModel):
    session_id: Optional[str] = None
    answer: str


class VoiceSetAdminRequest(BaseModel):
    speaker_id: str


class VoiceSpeakRequest(BaseModel):
    text: str
    speak: bool = True
    voice_mode: Optional[str] = None
    voice_style: Optional[str] = None
    voice_rate: Optional[int] = None
    voice_pitch: Optional[int] = None
    voice_name: Optional[str] = None
    accent_profile: Optional[str] = None


class VoiceSettingsRequest(BaseModel):
    voice_mode: Optional[str] = None
    voice_style: Optional[str] = None
    voice_rate: Optional[int] = None
    voice_pitch: Optional[int] = None
    voice_name: Optional[str] = None
    accent_profile: Optional[str] = None


class VoiceResponse(BaseModel):
    enabled: bool
    state: Optional[str] = None
    response: str = ""
    action: Optional[str] = None
    intent: Optional[str] = None
    plan_id: Optional[str] = None
    tasks_executed: Optional[int] = None
    steps: Optional[List[Any]] = None
    data: Optional[dict] = None
    initiative: Optional[dict] = None
    voice: Optional[dict] = None


class AvatarEmitRequest(BaseModel):
    event: str
    payload: Optional[dict] = None


# ==========================
# Root / Health
# ==========================

@router.get("/")
def root():
    """Root endpoint."""
    return {
        "application": "NOVA",
        "version": "0.1.0",
        "status": "running"
    }


@router.get("/app")
def app_ui():
    """Serve NOVA interactive UI."""
    if UI_INDEX.exists():
        return FileResponse(str(UI_INDEX))
    return {
        "status": "unavailable",
        "message": "UI files not found.",
    }


@router.get("/companion")
def companion_ui():
    """Serve browser-based NOVA companion."""
    if COMPANION_INDEX.exists():
        return FileResponse(str(COMPANION_INDEX))
    return {
        "status": "unavailable",
        "message": "Companion UI file not found.",
    }


@router.get("/health")
def health():
    """Health check."""
    return {
        "status": "healthy"
    }


@router.get("/system")
def system_status():
    """Returns status of all registered services."""
    return registry.health()


# ==========================
# Voice
# ==========================

@router.get("/voice/status", response_model=dict)
def voice_status():
    """Return voice engine state."""
    return registry.voice_engine.status()


@router.get("/devices/connected", response_model=dict)
def connected_devices():
    """Return live connected Bluetooth and wired/external devices."""
    tool = registry.tool_registry.find_by_name("SystemInfoTool")
    if tool is None or not hasattr(tool, "get_connected_devices_snapshot"):
        return {"ok": False, "bluetooth": {"connected": []}, "wired_external": []}

    snapshot = tool.get_connected_devices_snapshot()
    if isinstance(snapshot, dict):
        return snapshot

    return {"ok": False, "bluetooth": {"connected": []}, "wired_external": []}


@router.get("/voice/settings", response_model=dict)
def get_voice_settings():
    """Return current runtime voice preferences."""
    return {
        "voice": registry.voice_engine.get_voice_preferences(),
        "controls": registry.voice_engine.status().get("controls", {}),
    }


@router.post("/voice/settings", response_model=dict)
def set_voice_settings(body: VoiceSettingsRequest):
    """Update runtime voice preferences used by chat and voice talkback."""
    updated = registry.voice_engine.set_voice_preferences({
        "voice_mode": body.voice_mode,
        "style": body.voice_style,
        "rate": body.voice_rate,
        "pitch": body.voice_pitch,
        "voice": body.voice_name,
        "accent_profile": body.accent_profile,
    })
    return {
        "ok": True,
        "voice": updated,
    }


@router.post("/voice/speakers/enroll", response_model=dict)
def enroll_voice_speaker(body: VoiceEnrollmentRequest):
    profile = registry.voice_engine.pipeline.speaker_registry.enroll(
        body.name,
        body.samples,
        role=(body.role or "user").strip().lower(),
    )
    return {
        "id": profile.id,
        "name": profile.name,
        "samples": profile.samples,
        "role": profile.role,
        "embedding": profile.embedding,
        "status": "enrolled",
    }


@router.post("/voice/enrollment/start", response_model=dict)
def voice_enrollment_start(body: VoiceEnrollmentStartRequest):
    return registry.voice_engine.start_enrollment_session(name=(body.name or None))


@router.post("/voice/enrollment/answer", response_model=dict)
def voice_enrollment_answer(body: VoiceEnrollmentAnswerRequest):
    logger.info(
        "voice_enrollment_answer: processing text-only enrollment continuation",
        has_session_id=bool(body.session_id),
        answer_len=len((body.answer or "").strip()),
    )
    return registry.voice_engine.continue_enrollment_session(
        answer=body.answer,
        session_id=body.session_id,
    )


@router.get("/voice/enrollment/{session_id}", response_model=dict)
def voice_enrollment_status(session_id: str):
    session = registry.voice_engine.get_enrollment_session(session_id)
    if session is None:
        return {"ok": False, "error": "session_not_found", "session_id": session_id}
    return {"ok": True, "session": session}


@router.get("/voice/recognition", response_model=dict)
def get_voice_recognition():
    """Return whether voice recognition (speaker identity checking) is enabled."""
    return {"enabled": registry.voice_engine.recognition_enabled}


@router.post("/voice/recognition", response_model=dict)
def set_voice_recognition(body: dict):
    """Enable or disable voice speaker recognition."""
    enabled = bool(body.get("enabled", True))
    registry.voice_engine.recognition_enabled = enabled
    return {"enabled": enabled}


@router.get("/voice/speakers", response_model=dict)
def voice_speakers():
    return {
        "ok": True,
        "speakers": registry.voice_engine.list_speakers(),
    }


@router.post("/voice/speakers/set-admin", response_model=dict)
def voice_set_admin(body: VoiceSetAdminRequest):
    profile = registry.voice_engine.set_admin_speaker(body.speaker_id)
    if profile is None:
        return {"ok": False, "error": "speaker_not_found", "speaker_id": body.speaker_id}
    return {
        "ok": True,
        "admin": profile,
    }


@router.delete("/voice/speakers/{speaker_id}", response_model=dict)
def voice_delete_speaker(speaker_id: str):
    profile = registry.voice_engine.delete_speaker(speaker_id)
    if profile is None:
        return {"ok": False, "error": "speaker_not_found", "speaker_id": speaker_id}
    return {
        "ok": True,
        "deleted": profile,
    }


@router.delete("/voice/speakers", response_model=dict)
def voice_delete_all_speakers():
    removed = registry.voice_engine.delete_all_speakers()
    return {
        "ok": True,
        "removed": removed,
    }


@router.post("/voice/text", response_model=VoiceResponse)
def voice_text(body: VoiceTextRequest):
    """
    Test the voice pipeline using text input.

    This is the safest way to validate the voice stack before
    wiring a real microphone and wake-word loop.
    """
    audio_path = _materialize_audio_payload(body.audio_base64, body.audio_mime_type)
    logger.info(
        "voice_text: received request",
        text_len=len((body.text or "").strip()),
        has_audio_payload=bool(body.audio_base64),
        audio_temp_path=audio_path or "",
    )
    voice_preferences = registry.voice_engine.resolve_voice_preferences({
        "voice_mode": body.voice_mode,
        "style": body.voice_style,
        "rate": body.voice_rate,
        "pitch": body.voice_pitch,
        "voice": body.voice_name,
        "accent_profile": body.accent_profile,
    })
    metadata = {
        "speaker": body.speaker,
        "audio_path": audio_path,
        "voice_preferences": voice_preferences,
    }
    try:
        result = registry.voice_engine.handle_text(
            body.text,
            speak=body.speak,
            force=True,
            metadata=metadata,
        )
        logger.info(
            "voice_text: handled",
            action=str(result.get("action") or ""),
            intent=str(result.get("intent") or ""),
            recognized_speaker=str(result.get("speaker") or "unknown"),
            recognition_backend=str(result.get("recognition_backend") or ""),
            recognition_confidence=float(result.get("recognition_confidence") or 0.0),
        )
        return VoiceResponse(**{
            "enabled": result.get("enabled", True),
            "state": result.get("voice", {}).get("state") if isinstance(result.get("voice"), dict) else result.get("state"),
            "response": result.get("response", ""),
            "action": result.get("action"),
            "intent": result.get("intent"),
            "plan_id": result.get("plan_id"),
            "tasks_executed": result.get("tasks_executed"),
            "steps": result.get("steps"),
            "data": result.get("data") if isinstance(result.get("data"), dict) else None,
            "initiative": result.get("initiative") if isinstance(result.get("initiative"), dict) else None,
            "voice": result.get("voice"),
        })
    finally:
        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
                logger.info("voice_text: removed temp audio payload", temp_path=audio_path)
            except OSError:
                logger.warning("voice_text: failed removing temp audio payload", temp_path=audio_path)
                pass


@router.post("/voice/speak", response_model=dict)
def voice_speak(body: VoiceSpeakRequest):
    """Speak arbitrary text through configured backend TTS (Kokoro/Piper/say/espeak)."""
    prefs = registry.voice_engine.resolve_voice_preferences({
        "voice_mode": body.voice_mode,
        "style": body.voice_style,
        "rate": body.voice_rate,
        "pitch": body.voice_pitch,
        "voice": body.voice_name,
        "accent_profile": body.accent_profile,
    })
    bus.publish(
        Event.AVATAR_SPEAKING_STARTED,
        {
            "text": body.text,
            "style": prefs.get("style"),
            "rate": prefs.get("rate"),
            "pitch": prefs.get("pitch"),
            "voice_mode": prefs.get("voice_mode"),
        },
    )
    result = registry.voice_engine.synthesizer.speak(
        body.text,
        play=body.speak,
        style=prefs.get("style"),
        rate=prefs.get("rate"),
        pitch=prefs.get("pitch"),
        voice=prefs.get("voice") or None,
        voice_mode=prefs.get("voice_mode"),
    )
    bus.publish(
        Event.AVATAR_SPEAKING_COMPLETED,
        {
            "backend": result.backend,
            "error": result.error,
        },
    )
    bus.publish(Event.AVATAR_IDLE, {"reason": "voice_speak_completed"})
    return {
        "success": result.error == "",
        "backend": result.backend,
        "spoken": result.spoken,
        "error": result.error,
        "command": result.command,
        "voice": prefs,
    }


@router.post("/voice/stop", response_model=dict)
def voice_stop():
    """Stop currently speaking output and return avatar to idle."""
    stopped = registry.voice_engine.stop_speaking()
    return {
        "ok": True,
        "stop": stopped,
    }


@router.get("/avatar/state", response_model=dict)
def avatar_state():
    """Current avatar stream state and recent event history."""
    return registry.avatar_stream.snapshot()


@router.get("/avatar/events")
async def avatar_events():
    """Server-Sent Events stream consumed by the macOS avatar companion."""
    queue = registry.avatar_stream.subscribe()

    async def event_generator():
        snapshot = registry.avatar_stream.snapshot()
        yield f"event: snapshot\ndata: {json.dumps(snapshot)}\n\n"
        try:
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield message
                except asyncio.TimeoutError:
                    yield "event: ping\ndata: {\"ok\": true}\n\n"
        finally:
            registry.avatar_stream.unsubscribe(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/avatar/emit", response_model=dict)
def avatar_emit(body: AvatarEmitRequest):
    """Manual event injection for quickly testing avatar animations."""
    envelope = registry.avatar_stream.publish(body.event, body.payload or {})
    return {
        "ok": True,
        "event": envelope,
    }


# ==========================
# Chat  (clean endpoint)
# ==========================

@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest):
    """
    Send a message to NOVA and receive a clean response.

    Example request:
        {"message": "Build me a weather app in FastAPI"}

    Example response (complex goal):
        {
          "response": "Here is your complete weather app...",
          "intent": "code_help",
          "action": "plan",
          "plan_id": "abc123",
          "tasks_executed": 5,
          "steps": [{"step": 1, "task": "Create project structure"}, ...]
        }
    """
    message = (body.message or "").strip()

    if registry.voice_engine.has_active_enrollment_session():
        raw = registry.voice_engine.continue_enrollment_session(answer=message)
    elif registry.voice_engine.is_enrollment_trigger(message):
        hinted_name = registry.voice_engine.extract_enrollment_name_hint(message)
        raw = registry.voice_engine.start_enrollment_session(name=hinted_name or None)
    else:
        raw = registry.conversation.handle(message)

    if isinstance(raw, dict):
        return ChatResponse(
            response=raw.get("response") or raw.get("text") or "",
            intent=raw.get("intent"),
            action=raw.get("action", "chat"),
            plan_id=raw.get("plan_id"),
            tasks_executed=raw.get("tasks_executed"),
            steps=raw.get("steps"),
            data=raw.get("data") if isinstance(raw.get("data"), dict) else None,
            initiative=raw.get("initiative"),
            reflected=raw.get("reflected"),
            reflection_reason=raw.get("reflection_reason"),
        )

    text = raw.text if hasattr(raw, "text") else str(raw)
    return ChatResponse(response=text, action="chat")


# ==========================
# Plan preview  (inspect plan without executing)
# ==========================

@router.post("/plan/preview", response_model=PlanPreviewResponse)
def plan_preview(body: PlanRequest):
    """
    Show what TaskPlanner would decompose a goal into — without executing.

    Useful for understanding how NOVA will approach a complex task.

    Example request:
        {"goal": "Teach me Machine Learning from scratch"}

    Example response:
        {
          "goal": "Teach me Machine Learning from scratch",
          "plan_id": "xyz789",
          "tasks": ["Introduction", "Linear Regression", "Neural Networks", ...],
          "is_simple": false
        }
    """
    planner = registry.planner
    if planner.task_planner is None:
        return PlanPreviewResponse(
            goal=body.goal,
            plan_id="unavailable",
            tasks=[body.goal],
            is_simple=True,
        )
    plan = planner.task_planner.plan(body.goal)
    return PlanPreviewResponse(
        goal=plan.goal,
        plan_id=plan.plan_id,
        tasks=plan.summary(),
        is_simple=plan.is_simple(),
    )


# ==========================
# Brain  (legacy – kept for compatibility)
# ==========================

@router.post("/brain")
def think(message: str):
    """Process a message using NOVA Brain (legacy query-param form)."""
    raw = registry.conversation.handle(message)

    if isinstance(raw, dict):
        return raw

    text = raw.text if hasattr(raw, "text") else str(raw)
    return {"response": text, "action": "chat"}


# ==========================
# Memory
# ==========================

class MemorySetRequest(BaseModel):
    key: str
    value: str


@router.post("/memory")
def remember(body: MemorySetRequest):
    """Store a memory."""
    registry.memory.remember(body.key, body.value)
    return {
        "status": "stored",
        "key": body.key,
    }


@router.get("/memory/{key}")
def recall(key: str):
    """Recall a stored memory."""
    return {
        "key": key,
        "value": registry.memory.recall(key)
    }


@router.get("/memory")
def recall_all():
    """Dump all stored memories."""
    return registry.memory.recall_all()


# ==========================
# Planner
# ==========================

@router.post("/planner")
def create_goal(goal: str):
    """Create a new planner goal."""
    return registry.planner.create_goal(goal)


@router.get("/planner")
def list_tasks():
    """List all planner tasks."""
    return registry.planner.list_tasks()


# ==========================
# Gmail
# ==========================

class GmailSendRequest(BaseModel):
    to: str
    subject: str
    body: str
    html: bool = False


@router.get("/gmail/status", response_model=dict)
def gmail_status():
    """Return whether Gmail integration is configured and available."""
    from pathlib import Path
    from packages.config import settings
    token_exists = Path(settings.GMAIL_TOKEN_PATH).expanduser().exists()
    creds_exists = Path(settings.GMAIL_CREDENTIALS_PATH).expanduser().exists()
    return {
        "enabled": settings.GMAIL_MONITOR_ENABLED,
        "authenticated": token_exists,
        "credentials_present": creds_exists,
        "poll_interval": settings.GMAIL_POLL_INTERVAL,
    }


@router.get("/gmail/inbox", response_model=dict)
def gmail_inbox():
    """Fetch recent unread messages with urgency classification."""
    tool = registry.gmail_tool
    try:
        messages = tool.list_unread(max_results=20)
        return {
            "ok": True,
            "count": len(messages),
            "messages": messages,
        }
    except Exception as ex:
        logger.error(f"gmail_inbox error: {ex}")
        return {"ok": False, "error": str(ex), "messages": []}


@router.get("/gmail/message/{message_id}", response_model=dict)
def gmail_get_message(message_id: str):
    """Get a single Gmail message by ID."""
    tool = registry.gmail_tool
    try:
        msg = tool.get_message(message_id)
        return {"ok": True, "message": msg}
    except Exception as ex:
        return {"ok": False, "error": str(ex)}


@router.post("/gmail/send", response_model=dict)
def gmail_send(body: GmailSendRequest):
    """Send an email via Gmail."""
    tool = registry.gmail_tool
    bus.publish(Event.GMAIL_SEND_STARTED, {"to": body.to, "subject": body.subject})
    result = tool.send_email(to=body.to, subject=body.subject, body=body.body, html=body.html)
    if result.get("success"):
        bus.publish(Event.GMAIL_SEND_COMPLETED, {"to": body.to, "subject": body.subject})
    return result


@router.post("/gmail/mark-read/{message_id}", response_model=dict)
def gmail_mark_read(message_id: str):
    """Mark a Gmail message as read."""
    tool = registry.gmail_tool
    ok = tool.mark_read(message_id)
    return {"ok": ok, "message_id": message_id}