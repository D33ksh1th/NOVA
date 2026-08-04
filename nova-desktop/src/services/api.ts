// ============================================================
// NOVA API client — HTTP calls to FastAPI backend
// ============================================================
import type {
  ChatRequest,
  ChatResponse,
  ConnectedDevicesResponse,
  VoiceEnrollmentResponse,
  VoiceSpeakerProfile,
  VoiceTextRequest,
  VoiceTextResponse,
  VoiceSettings,
  GmailInboxResponse,
  GmailSendRequest,
  GmailStatusResponse,
} from "@/types";

const BASE = import.meta.env.VITE_NOVA_API_URL ?? "http://127.0.0.1:8000";
// Monotonic token so only the newest speak request is allowed to play.
let speakToken = 0;

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers ?? {}) },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`NOVA API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ── Chat ─────────────────────────────────────────────────────
export async function apiChat(req: ChatRequest): Promise<ChatResponse> {
  return request<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

// ── Voice ────────────────────────────────────────────────────
export async function apiVoiceText(
  req: VoiceTextRequest
): Promise<VoiceTextResponse> {
  return request<VoiceTextResponse>("/voice/text", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function apiVoiceSpeak(
  text: string,
  settings: Partial<VoiceSettings>
): Promise<void> {
  const token = ++speakToken;

  // Best-effort stop to prevent overlap from in-flight or previous responses.
  await request("/voice/stop", {
    method: "POST",
  }).catch(() => {
    // Non-fatal. We'll still attempt the latest speak request.
  });

  // If a newer speak was requested while we were stopping, skip this one.
  if (token !== speakToken) return;

  await request("/voice/speak", {
    method: "POST",
    body: JSON.stringify({
      text,
      speak: true,
      voice_mode: settings.mode,
      voice_style: settings.style,
      voice_rate: settings.rate,
      voice_pitch: settings.pitch,
      voice_name: settings.model,
      accent_profile: settings.accent,
    }),
  });
}

export async function apiVoiceStop(): Promise<{ ok: boolean; stop?: { success?: boolean; stopped?: string[] } }> {
  // Invalidate any pending/in-flight speak call in the client layer.
  speakToken += 1;
  return request("/voice/stop", {
    method: "POST",
  });
}

export async function apiVoiceSettings(
  settings: Partial<VoiceSettings>
): Promise<void> {
  await request("/voice/settings", {
    method: "POST",
    body: JSON.stringify({
      voice_mode: settings.mode,
      voice_style: settings.style,
      voice_rate: settings.rate,
      voice_pitch: settings.pitch,
      voice_name: settings.model,
      accent_profile: settings.accent,
    }),
  });
}

export async function apiVoiceStatus(): Promise<{
  enabled: boolean;
  controls?: { current?: Record<string, unknown> };
}> {
  return request("/voice/status");
}

export async function apiVoiceEnrollmentStart(name?: string): Promise<VoiceEnrollmentResponse> {
  return request<VoiceEnrollmentResponse>("/voice/enrollment/start", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function apiVoiceEnrollmentAnswer(
  answer: string,
  sessionId?: string
): Promise<VoiceEnrollmentResponse> {
  return request<VoiceEnrollmentResponse>("/voice/enrollment/answer", {
    method: "POST",
    body: JSON.stringify({
      answer,
      session_id: sessionId,
    }),
  });
}

export async function apiVoiceEnrollmentStatus(sessionId: string): Promise<{
  ok: boolean;
  session?: Record<string, unknown>;
  error?: string;
}> {
  return request(`/voice/enrollment/${encodeURIComponent(sessionId)}`);
}

export async function apiVoiceSpeakers(): Promise<{
  ok: boolean;
  speakers: VoiceSpeakerProfile[];
}> {
  return request("/voice/speakers");
}

export async function apiVoiceSetAdmin(speakerId: string): Promise<{
  ok: boolean;
  admin?: VoiceSpeakerProfile;
  error?: string;
}> {
  return request("/voice/speakers/set-admin", {
    method: "POST",
    body: JSON.stringify({ speaker_id: speakerId }),
  });
}

export async function apiVoiceDeleteSpeaker(speakerId: string): Promise<{
  ok: boolean;
  deleted?: VoiceSpeakerProfile;
  error?: string;
}> {
  return request(`/voice/speakers/${encodeURIComponent(speakerId)}`, {
    method: "DELETE",
  });
}

export async function apiVoiceDeleteAllSpeakers(): Promise<{
  ok: boolean;
  removed: number;
}> {
  return request("/voice/speakers", {
    method: "DELETE",
  });
}

export async function apiGetVoiceRecognition(): Promise<{ enabled: boolean }> {
  return request("/voice/recognition");
}

export async function apiSetVoiceRecognition(enabled: boolean): Promise<{ enabled: boolean }> {
  return request("/voice/recognition", {
    method: "POST",
    body: JSON.stringify({ enabled }),
  });
}

// ── Avatar ────────────────────────────────────────────────────
export async function apiAvatarEmit(
  event: string,
  payload: Record<string, unknown> = {}
): Promise<void> {
  await request("/avatar/emit", {
    method: "POST",
    body: JSON.stringify({ event, payload }),
  });
}

// ── Health ────────────────────────────────────────────────────
export async function apiHealth(): Promise<{ status: string }> {
  return request("/health");
}

export async function apiConnectedDevices(): Promise<ConnectedDevicesResponse> {
  return request<ConnectedDevicesResponse>("/devices/connected");
}

// ── Gmail ─────────────────────────────────────────────────────
export async function apiGmailStatus(): Promise<GmailStatusResponse> {
  return request<GmailStatusResponse>("/gmail/status");
}

export async function apiGmailInbox(maxResults = 20): Promise<GmailInboxResponse> {
  return request<GmailInboxResponse>(`/gmail/inbox?max_results=${maxResults}`);
}

export async function apiGmailSend(req: GmailSendRequest): Promise<{ success: boolean; error?: string }> {
  return request("/gmail/send", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function apiGmailMarkRead(messageId: string): Promise<{ ok: boolean }> {
  return request(`/gmail/mark-read/${encodeURIComponent(messageId)}`, { method: "POST" });
}
