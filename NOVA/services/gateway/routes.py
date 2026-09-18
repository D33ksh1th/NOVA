"""
Main API routes for NOVA Gateway.
"""

import asyncio
import base64
import binascii
import hmac
import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
import requests

from fastapi import APIRouter, Header, HTTPException, Request, WebSocket
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List, Any

from packages.common import logger, cache
from packages.config.settings import settings
from packages.events import Event, bus
from packages.registry import registry
from starlette.responses import StreamingResponse
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from services.agent_runtime.conversation import agent_command
from services.gateway.agent_status import require_local

router = APIRouter()

_SECURITY_AGENT_PUBLIC_KEY: Ed25519PublicKey | None = None


def _canonical_json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _load_security_agent_public_key() -> Ed25519PublicKey:
    global _SECURITY_AGENT_PUBLIC_KEY
    if _SECURITY_AGENT_PUBLIC_KEY is not None:
        return _SECURITY_AGENT_PUBLIC_KEY
    path = (settings.SECURITY_AGENT_PUBLIC_KEY_PATH or "").strip()
    if not path:
        raise HTTPException(status_code=500, detail="security agent public key path is not configured")
    key_file = Path(path)
    if not key_file.exists():
        raise HTTPException(status_code=500, detail="security agent public key file not found")
    public_key = serialization.load_pem_public_key(key_file.read_bytes())
    if not isinstance(public_key, Ed25519PublicKey):
        raise HTTPException(status_code=500, detail="security agent public key must be Ed25519")
    _SECURITY_AGENT_PUBLIC_KEY = public_key
    return public_key


def _verify_signed_payload(payload: dict, signature: str, key_id: str) -> None:
    if not signature or not key_id:
        raise HTTPException(status_code=401, detail="missing payload signature")
    to_verify = dict(payload)
    to_verify.pop("signature", None)
    to_verify.pop("signature_key_id", None)
    try:
        signature_bytes = binascii.unhexlify(signature)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=401, detail="invalid signature encoding")

    public_key = _load_security_agent_public_key()
    try:
        public_key.verify(signature_bytes, _canonical_json_bytes(to_verify))
    except Exception:
        raise HTTPException(status_code=401, detail="invalid payload signature")


def _cached_json(key: str, loader, ttl_seconds: int):
    cached = cache.get_json(key)
    if cached is not None:
        return cached
    value = loader()
    cache.set_json(key, value, ttl_seconds)
    return value


def _invalidate_security_cache() -> None:
    cache.delete("security:status")
    cache.delete("security:agents")
    cache.delete("security:assets")
    cache.delete("security:findings")
    cache.delete_pattern("security:timeline:*")


def _invalidate_gmail_cache() -> None:
    cache.delete_pattern("gmail:*")

UI_INDEX = Path(__file__).resolve().parent / "ui" / "index.html"
COMPANION_INDEX = Path(__file__).resolve().parent / "ui" / "companion2.html"

FACE_ADMIN_GREETING_COOLDOWN_SECONDS = 45
FACE_USER_GREETING_COOLDOWN_SECONDS = 30
FACE_UNKNOWN_ALERT_COOLDOWN_SECONDS = 90
FACE_ADMIN_PRESENCE_MAX_AGE_SECONDS = 120


def _face_policy_defaults() -> dict:
    return {
        "unknown_face_alerts_enabled": True,
        "auto_greet_tts_enabled": True,
        "sensitive_action_lock_enabled": False,
    }


def _ensure_face_policy(tool: Any) -> dict:
    policy = getattr(tool, "face_advanced_policy", None)
    if not isinstance(policy, dict):
        policy = _face_policy_defaults()
        setattr(tool, "face_advanced_policy", policy)
        return policy

    defaults = _face_policy_defaults()
    for key, value in defaults.items():
        if key not in policy:
            policy[key] = value
    return policy


def _face_session_defaults() -> dict:
    return {
        "present": False,
        "last_seen_at": None,
        "active_identity": None,
        "last_recognition": None,
        "greeting_state": {
            "last_name": None,
            "last_role": None,
            "last_at": None,
        },
        "unknown_alert": {
            "last_at": None,
            "last_error": None,
        },
    }


def _ensure_face_session(tool: Any) -> dict:
    session = getattr(tool, "face_presence_session", None)
    if not isinstance(session, dict):
        session = _face_session_defaults()
        setattr(tool, "face_presence_session", session)
        return session

    # Backward-compatible hydration for old session shapes.
    defaults = _face_session_defaults()
    for key, value in defaults.items():
        if key not in session:
            session[key] = value
    if not isinstance(session.get("greeting_state"), dict):
        session["greeting_state"] = defaults["greeting_state"]
    if not isinstance(session.get("unknown_alert"), dict):
        session["unknown_alert"] = defaults["unknown_alert"]
    return session


def _face_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _serialize_attrs(attrs) -> Optional[dict]:
    """Convert a FaceAttributes dataclass or None to a plain dict safe for JSON."""
    if attrs is None:
        return None
    try:
        from dataclasses import asdict
        return asdict(attrs)
    except Exception:
        return {}


def _serialize_result(result) -> dict:
    """Serialize a FaceRecognitionResult safely, excluding non-serialisable attrs object."""
    return {
        "recognized": bool(result.recognized),
        "name": str(result.name or ""),
        "role": str(result.role or ""),
        "confidence": float(result.confidence or 0.0),
        "backend": str(result.backend or ""),
        "error": str(result.error or ""),
    }


def _is_sensitive_action_request(message: str) -> bool:
    low = str(message or "").lower()
    if not low:
        return False
    sensitive_keys = [
        "delete",
        "remove",
        "drop database",
        "truncate",
        "shutdown",
        "reboot",
        "kill process",
        "sudo",
        "chmod",
        "security",
        "firewall",
        "asset discovery",
        "scan network",
        "send email",
        "gmail send",
        "rm -rf",
        "install package",
        "execute script",
    ]
    return any(k in low for k in sensitive_keys)


def _active_face_is_admin() -> bool:
    tool = registry.tool_registry.find_by_name("VisionTool")
    if tool is None:
        return False

    session = _ensure_face_session(tool)
    active = session.get("active_identity") if isinstance(session, dict) else None
    if not isinstance(active, dict):
        return False
    if str(active.get("role") or "").lower() != "admin":
        return False

    last_seen_at = session.get("last_seen_at")
    if not last_seen_at:
        return False

    try:
        seen_dt = datetime.strptime(str(last_seen_at), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return False

    return (time.time() - seen_dt.timestamp()) <= FACE_ADMIN_PRESENCE_MAX_AGE_SECONDS


def _should_block_sensitive_request(message: str) -> bool:
    tool = registry.tool_registry.find_by_name("VisionTool")
    if tool is None:
        return False
    policy = _ensure_face_policy(tool)
    if not bool(policy.get("sensitive_action_lock_enabled", False)):
        return False
    if not _is_sensitive_action_request(message):
        return False
    return not _active_face_is_admin()


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
    success: Optional[bool] = None
    playback_state: Optional[str] = None
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


class IdentitySyncRequest(BaseModel):
    prefer: Optional[str] = "face"


class VoiceResponse(BaseModel):
    enabled: bool
    state: Optional[str] = None
    response: str = ""
    success: Optional[bool] = None
    playback_state: Optional[str] = None
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


class SecurityAgentFindingRequest(BaseModel):
    title: str
    summary: str
    risk: str = "medium"
    confidence: float = 0.0
    tags: List[str] = []
    evidence: dict = {}


class SecurityAgentHeartbeatRequest(BaseModel):
    agent_id: str
    hostname: str
    platform: str
    sent_at: Optional[int] = None
    nonce: Optional[str] = None
    signature_key_id: Optional[str] = None
    signature: Optional[str] = None
    telemetry: dict
    findings: List[SecurityAgentFindingRequest] = []


class SecurityAgentPullRequest(BaseModel):
    agent_url: str
    timeout: int = 45
    token: Optional[str] = None
    verify_ssl: bool = True


class FaceEnrollRequest(BaseModel):
    name: str = "Admin"
    role: Optional[str] = "user"
    image_base64: Optional[str] = None


class FaceRecognizeRequest(BaseModel):
    image_base64: Optional[str] = None


class FaceAnalyzeRequest(BaseModel):
    image_base64: str


def _materialize_image_payload(image_base64: Optional[str]) -> Optional[str]:
    if not image_base64:
        return None
    raw_value = str(image_base64).strip()
    if not raw_value:
        return None

    payload = raw_value.split(",", 1)[1] if raw_value.startswith("data:") and "," in raw_value else raw_value
    try:
        image_bytes = base64.b64decode(payload)
    except Exception:
        return None
    if not image_bytes:
        return None

    suffix = ".jpg"
    if raw_value.startswith("data:image/png"):
        suffix = ".png"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(image_bytes)
        return tmp.name


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


@router.get("/mobile")
def mobile_ui():
    """Serve mobile chat UI for phone access."""
    mobile_path = Path(__file__).parent / "ui" / "mobile.html"
    if mobile_path.exists():
        return FileResponse(str(mobile_path), media_type="text/html")
    return {"error": "mobile UI not found"}


@router.get("/system")
def system_status():
    """Returns status of all registered services."""
    return registry.health()


@router.get("/security/status")
def security_status():
    """Return phased Security Center status and collector readiness."""
    return _cached_json(
        "security:status",
        registry.security_center.status,
        settings.SECURITY_CACHE_TTL,
    )


@router.post("/security/scan")
def security_scan():
    """Trigger an immediate local security scan and return results."""
    result = registry.security_center.local_scan()
    _invalidate_security_cache()
    return {"ok": result.get("ok", False), "findings": result.get("findings", 0), "error": result.get("error")}


@router.get("/security/findings")
def security_findings():
    """Return current correlated security findings."""
    findings = _cached_json(
        "security:findings",
        registry.security_center.list_findings,
        settings.SECURITY_CACHE_TTL,
    )
    return {
        "ok": True,
        "count": len(findings),
        "findings": findings,
    }


@router.get("/security/agents")
def security_agents():
    agents = _cached_json(
        "security:agents",
        registry.security_center.list_agents,
        settings.SECURITY_CACHE_TTL,
    )
    return {
        "ok": True,
        "count": len(agents),
        "agents": agents,
    }


@router.get("/security/assets")
def security_assets():
    assets = _cached_json(
        "security:assets",
        registry.security_center.list_assets,
        settings.SECURITY_CACHE_TTL,
    )
    return {
        "ok": True,
        "count": len(assets),
        "assets": assets,
    }


@router.post("/security/agents/heartbeat")
def security_agent_heartbeat(
    body: SecurityAgentHeartbeatRequest,
    x_nova_agent_token: Optional[str] = Header(default=None),
):
    if not settings.SECURITY_AGENT_INGEST_ENABLED:
        raise HTTPException(status_code=403, detail="security agent ingest disabled")

    expected = (settings.SECURITY_AGENT_SHARED_TOKEN or "").strip()
    if not expected:
        raise HTTPException(status_code=403, detail="security agent shared token is not configured")
    provided = (x_nova_agent_token or "").strip()
    if not provided or not hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(status_code=401, detail="invalid security agent token")

    if settings.SECURITY_AGENT_SIGNATURE_REQUIRED:
        _verify_signed_payload(
            body.model_dump(),
            signature=str(body.signature or ""),
            key_id=str(body.signature_key_id or ""),
        )

    record = registry.security_center.ingest_agent_heartbeat(
        agent_id=body.agent_id,
        hostname=body.hostname,
        platform=body.platform,
        telemetry=body.telemetry,
        findings=[finding.model_dump() for finding in body.findings],
    )
    _invalidate_security_cache()
    return {
        "ok": True,
        "agent": record,
    }


@router.post("/security/agents/pull")
def security_agent_pull(body: SecurityAgentPullRequest):
    if not settings.SECURITY_AGENT_PULL_ENABLED:
        raise HTTPException(status_code=403, detail="security agent pull disabled")

    base = body.agent_url.strip().rstrip("/")
    if not base:
        raise HTTPException(status_code=400, detail="agent_url is required")
    endpoint = base if base.endswith("/security/agent/snapshot") else f"{base}/security/agent/snapshot"

    headers = {"Accept": "application/json"}
    token = (body.token or settings.SECURITY_AGENT_SHARED_TOKEN or "").strip()
    if token:
        headers["X-Nova-Agent-Token"] = token

    try:
        response = requests.get(
            endpoint,
            headers=headers,
            timeout=max(1, min(body.timeout, 120)),
            verify=body.verify_ssl,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"agent pull request failed: {exc}") from exc

    if response.status_code >= 400:
        detail = response.text[:300] if response.text else f"status {response.status_code}"
        raise HTTPException(status_code=502, detail=f"agent returned error: {detail}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="agent response was not valid JSON") from exc

    agent_id = str(payload.get("agent_id") or "").strip()
    hostname = str(payload.get("hostname") or "").strip()
    platform_name = str(payload.get("platform") or "").strip()
    telemetry = payload.get("telemetry")
    findings = payload.get("findings", [])

    if not agent_id or not hostname or not platform_name or not isinstance(telemetry, dict):
        raise HTTPException(status_code=502, detail="agent response missing required fields")

    if not isinstance(findings, list):
        findings = []

    if settings.SECURITY_AGENT_SIGNATURE_REQUIRED:
        _verify_signed_payload(
            payload,
            signature=str(payload.get("signature") or ""),
            key_id=str(payload.get("signature_key_id") or ""),
        )

    record = registry.security_center.ingest_agent_heartbeat(
        agent_id=agent_id,
        hostname=hostname,
        platform=platform_name,
        telemetry=telemetry,
        findings=[item for item in findings if isinstance(item, dict)],
    )
    _invalidate_security_cache()

    return {
        "ok": True,
        "pulled_from": endpoint,
        "agent": record,
    }


@router.get("/security/timeline")
def security_timeline(limit: int = 50):
    """Return recent security timeline events."""
    events = _cached_json(
        f"security:timeline:{limit}",
        lambda: registry.security_center.timeline_recent(limit=limit),
        settings.SECURITY_CACHE_TTL,
    )
    return {
        "ok": True,
        "count": len(events),
        "events": events,
    }


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


@router.post("/voice/persona", response_model=dict)
def set_voice_persona(persona: str = "jarvis"):
    """Switch Nova's voice persona. Options: jarvis, friday."""
    from services.voice.tts import KokoroSpeechSynthesizer
    personas = {
        "jarvis": {"voice": "bm_george", "speed": 0.94, "style": "calm", "accent": "english_jarvis"},
        "friday": {"voice": "bf_emma", "speed": 0.98, "style": "clear", "accent": "english_friday"},
        "devi": {"voice": "hf_alpha", "speed": 1.0, "style": "warm", "accent": "indian_warm"},
    }
    key = persona.strip().lower()
    if key not in personas:
        key = "jarvis"
    p = personas.get(key, personas["jarvis"])
    registry.voice_engine.set_voice_preferences({
        "voice_mode": "human",
        "accent_profile": p["accent"],
        "style": p["style"],
    })
    registry.voice_engine.synthesizer.kokoro_voice = p["voice"]
    registry.voice_engine.synthesizer.kokoro_speed = p["speed"]
    KokoroSpeechSynthesizer._active_persona = key if key in personas else "jarvis"
    addr = {"jarvis": "sir", "friday": "boss", "devi": "sir"}.get(key, "sir")
    return {"ok": True, "persona": key, "voice": p["voice"], "speed": p["speed"], "address": addr}


@router.get("/voice/persona", response_model=dict)
def get_voice_persona():
    """Get current voice persona."""
    from services.voice.tts import KokoroSpeechSynthesizer
    persona = getattr(KokoroSpeechSynthesizer, '_active_persona', 'jarvis')
    return {"persona": persona, "address": "sir" if persona == "jarvis" else "boss"}


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
    name = (body.name or "").strip()
    if name:
        # Quick enroll: name provided → enroll immediately as admin, skip multi-step
        return registry.voice_engine.quick_enroll(f"enroll me as {name}")
    return registry.voice_engine.start_enrollment_session(name=None)


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


@router.post("/identity/sync", response_model=dict)
def sync_identity_profiles(body: IdentitySyncRequest):
    """Sync speaker and face profile IDs by matching names."""
    face_tool = registry.tool_registry.find_by_name("VisionTool")
    if face_tool is None or not hasattr(face_tool, "face_registry"):
        return {
            "ok": False,
            "error": "vision_tool_unavailable",
        }

    speaker_registry = registry.voice_engine.pipeline.speaker_registry
    face_registry = face_tool.face_registry
    prefer = str(body.prefer or "face").strip().lower()
    if prefer not in {"face", "voice"}:
        prefer = "face"

    speakers = speaker_registry.all_profiles()
    faces = face_registry.all_profiles()
    face_by_name = {p.name.strip().lower(): p for p in faces}
    speaker_by_id = {p.id: p for p in speakers}
    face_by_id = {p.id: p for p in faces}
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    updates: list[dict] = []
    skipped: list[dict] = []

    for speaker in speakers:
        key = speaker.name.strip().lower()
        if not key:
            continue
        face = face_by_name.get(key)
        if face is None:
            continue
        if speaker.id == face.id:
            continue

        source_id = face.id if prefer == "face" else speaker.id
        # Guard against assigning an ID that already belongs to another person.
        speaker_owner = speaker_by_id.get(source_id)
        face_owner = face_by_id.get(source_id)
        speaker_conflict = speaker_owner is not None and speaker_owner.name.strip().lower() != key
        face_conflict = face_owner is not None and face_owner.name.strip().lower() != key
        if speaker_conflict or face_conflict:
            skipped.append({
                "name": speaker.name,
                "speaker_id": speaker.id,
                "face_id": face.id,
                "reason": "id_conflict",
            })
            continue

        old_speaker_id = speaker.id
        old_face_id = face.id
        speaker.id = source_id
        face.id = source_id
        speaker.updated_at = now_iso
        face.updated_at = now_iso
        speaker_by_id.pop(old_speaker_id, None)
        face_by_id.pop(old_face_id, None)
        speaker_by_id[source_id] = speaker
        face_by_id[source_id] = face
        updates.append({
            "name": speaker.name,
            "speaker_id_before": old_speaker_id,
            "face_id_before": old_face_id,
            "id_after": source_id,
        })

    if updates:
        speaker_registry._save()
        face_registry._save()

    return {
        "ok": True,
        "prefer": prefer,
        "updated": updates,
        "updated_count": len(updates),
        "skipped": skipped,
        "skipped_count": len(skipped),
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
def voice_text(body: VoiceTextRequest, request: Request):
    """
    Test the voice pipeline using text input.

    This is the safest way to validate the voice stack before
    wiring a real microphone and wake-word loop.
    """
    if agent_command(body.text) is not None:
        require_local(request)
    if _should_block_sensitive_request(body.text):
        blocked_message = (
            "Sensitive action blocked. Admin face verification required. "
            "Look at the camera and ensure admin recognition is active, then retry."
        )
        return VoiceResponse(**{
            "enabled": True,
            "state": "idle",
            "response": blocked_message,
            "action": "blocked",
            "intent": "security_lock",
            "data": {
                "reason": "face_admin_required",
                "sensitive_action_lock_enabled": True,
            },
        })

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
        # Get the brain response without blocking on TTS playback.
        # Speech plays in background via the streaming player.
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
            "success": result.get("success"),
            "playback_state": result.get("playback_state"),
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
    """Speak text and return after playback completes or is interrupted."""
    prefs = registry.voice_engine.resolve_voice_preferences({
        "voice_mode": body.voice_mode,
        "style": body.voice_style,
        "rate": body.voice_rate,
        "pitch": body.voice_pitch,
        "voice": body.voice_name,
        "accent_profile": body.accent_profile,
    })
    text = str(body.text or "").strip()
    if not text:
        return {"success": False, "error": "empty_text", "backend": "none", "spoken": False}

    bus.publish(
        Event.AVATAR_SPEAKING_STARTED,
        {
            "text": text,
            "style": prefs.get("style"),
            "rate": prefs.get("rate"),
            "pitch": prefs.get("pitch"),
            "voice_mode": prefs.get("voice_mode"),
        },
    )

    from services.voice.state import VoiceState

    engine = registry.voice_engine
    engine._speech_generation = getattr(engine, "_speech_generation", 0) + 1
    generation = engine._speech_generation

    # Mark session as SPEAKING so echo suppression works
    registry.voice_engine.session.touch(VoiceState.SPEAKING)

    def _speak_to_completion():
        try:
            chunks = [text] if len(text) <= 200 else registry.voice_engine.pipeline.speech_planner._chunk_text(text)
            return registry.voice_engine.synthesizer.speak_sequence(
                chunks,
                play=body.speak,
                style=prefs.get("style"),
                rate=prefs.get("rate"),
                pitch=prefs.get("pitch"),
                voice=prefs.get("accent_profile") or prefs.get("voice") or None,
                voice_mode=prefs.get("voice_mode"),
                pause_ms=120,
                start_delay_ms=0,
            )
        except Exception as ex:
            from services.voice.tts import SpeechSynthesisResult
            logger.error(f"voice_speak error: {ex}")
            return SpeechSynthesisResult(text=text, backend="error", error="speech_failed")
        finally:
            if generation == engine._speech_generation:
                engine.session.touch(VoiceState.IDLE)
                bus.publish(Event.AVATAR_SPEAKING_COMPLETED, {"backend": "kokoro"})
                bus.publish(Event.AVATAR_IDLE, {"reason": "voice_speak_completed"})

    result = _speak_to_completion()
    interrupted = generation != engine._speech_generation or result.error == "interrupted"

    return {
        "success": not interrupted and not result.error and (not body.speak or result.spoken),
        "backend": result.backend,
        "spoken": result.spoken and not interrupted,
        "error": "interrupted" if interrupted else result.error,
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


@router.websocket("/voice/stream")
async def voice_stream_ws(websocket: WebSocket):
    """WebSocket endpoint for real-time voice streaming (wake word + STT)."""
    from services.voice.stream import handle_voice_stream
    await handle_voice_stream(websocket)


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


@router.post("/vision/face/enroll", response_model=dict)
def vision_face_enroll(body: FaceEnrollRequest):
    tool = registry.tool_registry.find_by_name("VisionTool")
    if tool is None or not hasattr(tool, "face_identity"):
        return {
            "ok": False,
            "error": "vision_tool_unavailable",
        }

    temp_image_path = _materialize_image_payload(body.image_base64)
    use_uploaded_image = bool(temp_image_path)
    if use_uploaded_image:
        image_path = str(temp_image_path)
        capture_backend = "browser_upload"
    else:
        cap = tool.camera.capture()
        if not cap.success:
            return {
                "ok": False,
                "error": f"camera_capture_failed: {cap.error}",
                "backend": cap.backend,
            }
        image_path = cap.path
        capture_backend = cap.backend

    try:
        role = "admin" if str(body.role or "user").strip().lower() == "admin" else "user"
        result = tool.face_identity.enroll_from_image(
            name=body.name, image_path=image_path, role=role, merge=True
        )
        if not result.recognized:
            return {
                "ok": False,
                "error": result.error or "face_enrollment_failed",
                "backend": result.backend,
                "image_path": image_path,
                "capture_backend": capture_backend,
                "result": _serialize_result(result),
            }

        # count how many samples the profile now has
        profile = tool.face_registry.get(body.name)
        sample_count = profile.sample_count if profile else 1
        attrs = _serialize_attrs(result.attributes)
        return {
            "ok": True,
            "image_path": image_path,
            "capture_backend": capture_backend,
            "result": _serialize_result(result),
            "attributes": attrs,
            "sample_count": sample_count,
            "response": (
                f"Face enrolled for {result.name} as {result.role}. "
                f"(Sample #{sample_count} captured via {result.backend}.)"
                + (" Hi boss, how are you?" if result.role == "admin" else "")
            ),
        }
    finally:
        if temp_image_path and os.path.exists(temp_image_path):
            try:
                os.remove(temp_image_path)
            except OSError:
                pass


@router.post("/vision/face/recognize", response_model=dict)
def vision_face_recognize(body: FaceRecognizeRequest):
    tool = registry.tool_registry.find_by_name("VisionTool")
    if tool is None or not hasattr(tool, "face_identity"):
        return {
            "ok": False,
            "error": "vision_tool_unavailable",
        }

    if not bool(getattr(tool, "face_recognition_enabled", True)):
        return {
            "ok": False,
            "error": "facial_recognition_disabled",
            "response": "Facial recognition is disabled in Settings.",
        }

    temp_image_path = _materialize_image_payload(body.image_base64)
    use_uploaded_image = bool(temp_image_path)
    if use_uploaded_image:
        image_path = str(temp_image_path)
        capture_backend = "browser_upload"
    else:
        cap = tool.camera.capture()
        if not cap.success:
            return {
                "ok": False,
                "error": f"camera_capture_failed: {cap.error}",
                "backend": cap.backend,
            }
        image_path = cap.path
        capture_backend = cap.backend

    try:
        result = tool.face_identity.recognize_from_image(image_path)
        session = _ensure_face_session(tool)
        policy = _ensure_face_policy(tool)
        now_iso = _face_now_iso()
        now_epoch = time.time()
        auto_greeting = {
            "triggered": False,
            "message": None,
        }
        unknown_alert = {
            "triggered": False,
            "message": None,
        }

        session["last_recognition"] = {
            "recognized": bool(result.recognized),
            "name": str(result.name or ""),
            "role": str(result.role or ""),
            "confidence": float(result.confidence or 0.0),
            "backend": str(result.backend or ""),
            "error": str(result.error or ""),
            "at": now_iso,
        }

        if result.recognized:
            session["present"] = True
            session["last_seen_at"] = now_iso
            session["active_identity"] = {
                "name": str(result.name or "Unknown"),
                "role": str(result.role or "user"),
                "confidence": float(result.confidence or 0.0),
                "backend": str(result.backend or ""),
            }

            role = str(result.role or "user").lower()
            greeting_state = session.get("greeting_state")
            if not isinstance(greeting_state, dict):
                greeting_state = {"last_name": None, "last_role": None, "last_at": None}
                session["greeting_state"] = greeting_state

            last_name = str(greeting_state.get("last_name") or "")
            last_role = str(greeting_state.get("last_role") or "")
            last_at_epoch = float(greeting_state.get("last_at") or 0.0)
            cooldown_window = FACE_ADMIN_GREETING_COOLDOWN_SECONDS if role == "admin" else FACE_USER_GREETING_COOLDOWN_SECONDS
            cooldown_ok = (now_epoch - last_at_epoch) >= cooldown_window
            identity_changed = last_name.lower() != str(result.name or "").lower() or last_role != role

            if identity_changed or cooldown_ok:
                if role == "admin":
                    auto_greeting = {
                        "triggered": True,
                        "message": f"Hi boss, how are you?",
                    }
                else:
                    auto_greeting = {
                        "triggered": True,
                        "message": f"Hello {result.name}, welcome back.",
                    }
                greeting_state["last_name"] = str(result.name or "")
                greeting_state["last_role"] = role
                greeting_state["last_at"] = now_epoch

                if bool(policy.get("auto_greet_tts_enabled", True)) and auto_greeting.get("message"):
                    try:
                        registry.voice_engine.synthesizer.speak(
                            str(auto_greeting.get("message")),
                            play=True,
                        )
                    except Exception as exc:
                        logger.warning("face auto greeting TTS failed", error=str(exc))
        else:
            session["present"] = False
            session["active_identity"] = None

            unknown_state = session.get("unknown_alert")
            if not isinstance(unknown_state, dict):
                unknown_state = {"last_at": None, "last_error": None}
                session["unknown_alert"] = unknown_state

            last_unknown_at = float(unknown_state.get("last_at") or 0.0)
            cooldown_ok = (now_epoch - last_unknown_at) >= FACE_UNKNOWN_ALERT_COOLDOWN_SECONDS
            enrolled_profiles = []
            if hasattr(tool, "face_registry"):
                try:
                    enrolled_profiles = tool.face_registry.all_profiles()
                except Exception:
                    enrolled_profiles = []

            if bool(policy.get("unknown_face_alerts_enabled", True)) and enrolled_profiles and cooldown_ok:
                message = "Unknown face detected in active camera session."
                registry.security_center.add_finding(
                    source="vision:face",
                    title="Unknown face detected",
                    summary=message,
                    risk="medium",
                    confidence=0.68,
                    tags=["vision", "identity", "camera"],
                    evidence={
                        "camera_backend": str(capture_backend or ""),
                        "recognition_backend": str(result.backend or ""),
                        "recognition_error": str(result.error or ""),
                        "enrolled_profiles": len(enrolled_profiles),
                    },
                )
                unknown_alert = {
                    "triggered": True,
                    "message": message,
                }
                unknown_state["last_at"] = now_epoch
                unknown_state["last_error"] = str(result.error or "")

        if result.recognized and result.role == "admin":
            greeting = "Hi boss, how are you?"
        elif result.recognized:
            greeting = f"Hello {result.name}, good to see you."
        else:
            greeting = result.error or "Face not recognized."

        attrs = _serialize_attrs(result.attributes)
        return {
            "ok": bool(result.recognized),
            "image_path": image_path,
            "capture_backend": capture_backend,
            "result": _serialize_result(result),
            "attributes": attrs,
            "response": greeting,
            "session": session,
            "policy": policy,
            "auto_greeting": auto_greeting,
            "unknown_alert": unknown_alert,
        }
    finally:
        if temp_image_path and os.path.exists(temp_image_path):
            try:
                os.remove(temp_image_path)
            except OSError:
                pass


@router.post("/vision/face/analyze", response_model=dict)
def vision_face_analyze(body: FaceAnalyzeRequest):
    tool = registry.tool_registry.find_by_name("VisionTool")
    if tool is None or not hasattr(tool, "face_identity"):
        return {
            "ok": False,
            "error": "vision_tool_unavailable",
            "ready_for_enrollment": False,
            "guidance": ["Vision tool unavailable."],
        }

    temp_image_path = _materialize_image_payload(body.image_base64)
    if not temp_image_path:
        return {
            "ok": False,
            "error": "invalid_image_payload",
            "ready_for_enrollment": False,
            "guidance": ["Frame payload was invalid."],
        }

    try:
        analysis = tool.face_identity.analyze_image(str(temp_image_path))
        analysis["capture_backend"] = "browser_upload"
        return analysis
    finally:
        if os.path.exists(temp_image_path):
            try:
                os.remove(temp_image_path)
            except OSError:
                pass


@router.get("/vision/face/profiles", response_model=dict)
def vision_face_profiles():
    tool = registry.tool_registry.find_by_name("VisionTool")
    if tool is None or not hasattr(tool, "face_registry"):
        return {
            "ok": False,
            "profiles": [],
            "error": "vision_tool_unavailable",
        }

    profiles = []
    for profile in tool.face_registry.all_profiles():
        profiles.append(
            {
                "id": profile.id,
                "name": profile.name,
                "role": profile.role,
                "backend": profile.backend,
                "sample_count": getattr(profile, "sample_count", 1),
                "attributes": getattr(profile, "attributes", {}),
                "created_at": profile.created_at,
                "updated_at": profile.updated_at,
            }
        )
    return {
        "ok": True,
        "profiles": profiles,
    }


@router.delete("/vision/face/profiles/{profile_id}", response_model=dict)
def vision_face_delete_profile(profile_id: str):
    tool = registry.tool_registry.find_by_name("VisionTool")
    if tool is None or not hasattr(tool, "face_registry"):
        return {"ok": False, "error": "vision_tool_unavailable"}

    registry_obj = tool.face_registry
    profile = None
    for p in registry_obj.all_profiles():
        if p.id == profile_id or p.name.lower() == profile_id.lower():
            profile = p
            break

    if profile is None:
        return {"ok": False, "error": f"profile_not_found: {profile_id}"}

    key = profile.name.lower()
    registry_obj._profiles.pop(key, None)
    registry_obj._save()
    return {"ok": True, "deleted": {"id": profile.id, "name": profile.name, "role": profile.role}}


@router.get("/vision/face/recognition", response_model=dict)
def get_face_recognition():
    tool = registry.tool_registry.find_by_name("VisionTool")
    if tool is None:
        return {"enabled": False, "ok": False, "error": "vision_tool_unavailable"}
    return {
        "ok": True,
        "enabled": bool(getattr(tool, "face_recognition_enabled", True)),
    }


@router.get("/vision/face/session", response_model=dict)
def get_face_session():
    tool = registry.tool_registry.find_by_name("VisionTool")
    if tool is None:
        return {
            "ok": False,
            "error": "vision_tool_unavailable",
            "session": _face_session_defaults(),
        }

    return {
        "ok": True,
        "session": _ensure_face_session(tool),
        "policy": _ensure_face_policy(tool),
    }


@router.post("/vision/face/session/reset", response_model=dict)
def reset_face_session():
    tool = registry.tool_registry.find_by_name("VisionTool")
    if tool is None:
        return {
            "ok": False,
            "error": "vision_tool_unavailable",
            "session": _face_session_defaults(),
        }

    fresh = _face_session_defaults()
    setattr(tool, "face_presence_session", fresh)
    return {
        "ok": True,
        "session": fresh,
        "policy": _ensure_face_policy(tool),
    }


@router.get("/vision/face/policy", response_model=dict)
def get_face_policy():
    tool = registry.tool_registry.find_by_name("VisionTool")
    if tool is None:
        return {"ok": False, "error": "vision_tool_unavailable", "policy": _face_policy_defaults()}
    return {"ok": True, "policy": _ensure_face_policy(tool)}


@router.post("/vision/face/policy", response_model=dict)
def set_face_policy(body: dict):
    tool = registry.tool_registry.find_by_name("VisionTool")
    if tool is None:
        return {"ok": False, "error": "vision_tool_unavailable", "policy": _face_policy_defaults()}

    policy = _ensure_face_policy(tool)
    if "unknown_face_alerts_enabled" in body:
        policy["unknown_face_alerts_enabled"] = bool(body.get("unknown_face_alerts_enabled"))
    if "auto_greet_tts_enabled" in body:
        policy["auto_greet_tts_enabled"] = bool(body.get("auto_greet_tts_enabled"))
    if "sensitive_action_lock_enabled" in body:
        policy["sensitive_action_lock_enabled"] = bool(body.get("sensitive_action_lock_enabled"))

    setattr(tool, "face_advanced_policy", policy)
    return {"ok": True, "policy": policy}


@router.post("/vision/face/recognition", response_model=dict)
def set_face_recognition(body: dict):
    tool = registry.tool_registry.find_by_name("VisionTool")
    if tool is None:
        return {"enabled": False, "ok": False, "error": "vision_tool_unavailable"}
    enabled = bool(body.get("enabled", True))
    setattr(tool, "face_recognition_enabled", enabled)
    if not enabled:
        setattr(tool, "face_presence_session", _face_session_defaults())
    return {
        "ok": True,
        "enabled": enabled,
    }


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
def chat(body: ChatRequest, request: Request):
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

    if agent_command(message) is not None:
        require_local(request)

    if _should_block_sensitive_request(message):
        return ChatResponse(
            response=(
                "Sensitive action blocked. Admin face verification is required. "
                "Open Vision, verify admin face presence, and try again."
            ),
            intent="security_lock",
            action="blocked",
            data={
                "reason": "face_admin_required",
                "sensitive_action_lock_enabled": True,
            },
        )

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
            success=raw.get("success"),
            playback_state=raw.get("playback_state"),
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
def think(message: str, request: Request):
    """Process a message using NOVA Brain (legacy query-param form)."""
    if agent_command(message) is not None:
        require_local(request)
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
    def _load_status():
        token_exists = Path(settings.GMAIL_TOKEN_PATH).expanduser().exists()
        creds_exists = Path(settings.GMAIL_CREDENTIALS_PATH).expanduser().exists()
        return {
            "enabled": settings.GMAIL_MONITOR_ENABLED,
            "authenticated": token_exists,
            "credentials_present": creds_exists,
            "poll_interval": settings.GMAIL_POLL_INTERVAL,
        }

    return _cached_json("gmail:status", _load_status, settings.GMAIL_CACHE_TTL)


@router.get("/gmail/inbox", response_model=dict)
def gmail_inbox(max_results: int = 20):
    """Fetch recent unread messages with urgency classification."""
    tool = registry.gmail_tool
    size = max(1, min(int(max_results or 20), 100))
    cache_key = f"gmail:inbox:{size}"
    try:
        messages = _cached_json(
            cache_key,
            lambda: tool.list_unread(max_results=size),
            settings.GMAIL_CACHE_TTL,
        )
        return {
            "ok": True,
            "count": len(messages),
            "messages": messages,
        }
    except Exception as ex:
        logger.error(f"gmail_inbox error: {ex}")
        return {"ok": False, "error": str(ex), "messages": []}


@router.get("/gmail/message/{message_id}", response_model=dict)
def gmail_get_message(message_id: str, full: bool = True):
    """Get a single Gmail message by ID."""
    tool = registry.gmail_tool
    try:
        msg = tool.get_message(message_id, full=full)
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
        _invalidate_gmail_cache()
    return result


@router.post("/gmail/mark-read/{message_id}", response_model=dict)
def gmail_mark_read(message_id: str):
    """Mark a Gmail message as read."""
    tool = registry.gmail_tool
    ok = tool.mark_read(message_id)
    if ok:
        _invalidate_gmail_cache()
    return {"ok": ok, "message_id": message_id}


# ------------------------------------------------------------------
# Event Bus — Phase 1 Nervous System endpoints
# ------------------------------------------------------------------

@router.get("/events/replay")
def events_replay(
    event_type: Optional[str] = None,
    since_seq: int = 0,
    limit: int = 100,
):
    """Replay persisted events from the bus (like `nats sub nova.>`)."""
    events = bus.replay(event_type=event_type, since_seq=since_seq, limit=min(limit, 1000))
    return {"ok": True, "count": len(events), "last_seq": bus.last_seq(), "events": events}


@router.get("/events/stats")
def events_stats():
    """Event bus statistics."""
    now = time.time()
    return {
        "ok": True,
        "total_events": bus.event_count(),
        "last_hour": bus.event_count(since=now - 3600),
        "last_seq": bus.last_seq(),
        "categories": {
            "voice": bus.event_count(event_type="nova.voice.>"),
            "security": bus.event_count(event_type="nova.security.>"),
            "mail": bus.event_count(event_type="nova.mail.>"),
            "brain": bus.event_count(event_type="nova.brain.>"),
            "avatar": bus.event_count(event_type="nova.avatar.>"),
            "system": bus.event_count(event_type="nova.system.>"),
            "memory": bus.event_count(event_type="nova.memory.>"),
        },
    }


@router.post("/events/emit")
def events_emit(
    event_type: str,
    source: str = "api",
    severity: int = 0,
    payload: Optional[dict] = None,
):
    """Manually emit an event onto the bus (for testing/debugging)."""
    envelope = bus.emit(
        event_type=event_type,
        source=source,
        severity=severity,
        payload=payload or {},
    )
    return {"ok": True, "event_id": envelope.id, "type": envelope.type}


# ------------------------------------------------------------------
# State Store — Phase 1 endpoints
# ------------------------------------------------------------------

@router.get("/state/entities")
def state_entities(entity_type: Optional[str] = None, limit: int = 100):
    from packages.database import state_store
    return {"ok": True, "entities": state_store.get_entities(entity_type=entity_type, limit=limit)}


@router.get("/state/episodes")
def state_episodes(limit: int = 20):
    from packages.database import state_store
    return {"ok": True, "episodes": state_store.recent_episodes(limit=limit)}


@router.get("/state/audit")
def state_audit(limit: int = 50):
    from packages.database import state_store
    return {"ok": True, "audit": state_store.recent_audit(limit=limit)}


# ------------------------------------------------------------------
# Notifications — Phase 5
# ------------------------------------------------------------------

@router.get("/notifications")
def notifications_list(limit: int = 20):
    return {"ok": True, "notifications": registry.notification_policy.recent_notifications(limit=limit)}


@router.get("/notifications/stats")
def notifications_stats():
    return {"ok": True, **registry.notification_policy.stats()}


@router.post("/notifications/dnd")
def notifications_dnd(enabled: bool = True):
    registry.notification_policy.set_dnd(enabled)
    return {"ok": True, "dnd": enabled}


@router.post("/notifications/feedback")
def notifications_feedback(engaged: bool = True):
    registry.notification_policy.record_feedback(engaged)
    return {"ok": True}


# ------------------------------------------------------------------
# Actions — Phase 7 Agency
# ------------------------------------------------------------------

@router.get("/actions/pending")
def actions_pending():
    return {"ok": True, "pending": registry.action_gate.pending_actions()}


@router.post("/actions/confirm/{action_id}")
def actions_confirm(action_id: str, speaker_id: Optional[str] = None):
    result = registry.action_gate.confirm(action_id, speaker_id=speaker_id)
    return {"ok": result.get("approved", False), **result}


@router.post("/actions/cancel/{action_id}")
def actions_cancel(action_id: str):
    result = registry.action_gate.cancel(action_id)
    return {"ok": result.get("cancelled", False), **result}


@router.get("/actions/tools")
def actions_tools():
    from services.tools.tool_schemas import list_tool_schemas
    return {"ok": True, "tools": list_tool_schemas()}


@router.get("/actions/audit")
def actions_audit(limit: int = 50):
    from packages.database import state_store
    return {"ok": True, "audit": state_store.recent_audit(limit=limit)}