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
  GmailMessage,
  GmailSendRequest,
  GmailStatusResponse,
  SecurityAgentRecord,
  SecurityAsset,
  FaceEnrollResponse,
  FaceFrameAnalysisResponse,
  FaceAdvancedPolicy,
  FacePresenceSession,
  FaceProfileSummary,
  FaceRecognizeResponse,
  IdentitySyncResponse,
  SecurityFinding,
  SecurityStatusResponse,
  SecurityTimelineEvent,
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
export const apiMemories = (signal?: AbortSignal) => request<Record<string, unknown>>("/memory", { signal, cache: "no-store" });
export const apiSaveMemory = (key: string, value: string) => request<{ status: string; key: string }>("/memory", { method: "POST", body: JSON.stringify({ key, value }) });

export interface AgentRuntimeNode {
  id: string;
  name: string;
  agent: string;
  state: string;
  result_status: string | null;
  attempts: number;
  depends_on: string[];
}

export interface AgentRuntimeGraph {
  graph_id: string;
  status: string;
  nodes: AgentRuntimeNode[];
  finished_tasks: number;
  successful_tasks: number;
  total_tasks: number;
  finished_percent: number | null;
  elapsed_ms: number;
}

export interface AgentRuntimeStatus {
  state: "DISABLED" | "STARTING" | "UNAVAILABLE" | "READY" | "HALTED";
  reason_code: string;
  pending_runs: number;
  observed_at: string;
  graphs: AgentRuntimeGraph[];
  agents: { id: string; enabled: boolean; concurrency_limit: number; capabilities: string[]; risk: string }[];
}

export type AgentRuntimeAction = "research" | "status" | "results" | "stop";

export function apiAgentRuntimeStatus(signal?: AbortSignal): Promise<AgentRuntimeStatus> {
  return request("/api/agent-runtime/status", { signal, cache: "no-store" });
}

export function apiAgentRuntimeCommand(action: AgentRuntimeAction, objective = "") {
  return request<{ response: string; action: string; data?: { report_id?: string } }>("/api/agent-runtime/command", {
    method: "POST", body: JSON.stringify({ action, objective }), signal: AbortSignal.timeout(10000),
  });
}

export interface ResearchReportSummary {
  id: string;
  topic: string;
  status: string;
  created_at: string;
}

export function apiRepositoryReview(objective: string, files: string[]) {
  return request<{ response: string; action: string; data?: { report_id?: string } }>("/api/agent-runtime/repository-review", {
    method: "POST", body: JSON.stringify({ repository: "nova-desktop", objective, files }),
    signal: AbortSignal.timeout(10000),
  });
}

export interface ResearchFinding {
  task_id: string;
  agent_name: string;
  text: string;
  source_ids: string[];
  category?: "finding" | "agreement" | "tradeoff" | "contradiction" | "recommendation";
  subject?: string;
  priority?: "high" | "normal";
}

export interface SearchRelevance {
  score: number;
  matched_terms: string[];
  missing_terms: string[];
  method: string;
  query: string;
}

export interface ResearchReport extends ResearchReportSummary {
  kind?: "repository_review";
  scope?: { repository: string; files: string[]; mode: string };
  updated_at: string;
  graph_id: string | null;
  elapsed_ms: number;
  tasks: AgentRuntimeNode[];
  findings: ResearchFinding[];
  key_takeaways?: ResearchFinding[];
  coverage?: {
    cited_domains: number;
    evidence_scope: string;
    page_reads?: { task_id: string; agent_name: string; url: string; status: string; supplied_to_model: boolean; truncated: boolean }[];
    searches: { task_id: string; agent_name: string; query: string; status: string; sources: number; reviewed_sources: number;
      retrieval?: { candidate_sources?: number; providers_requested?: string[]; provider_limit?: number; pages_crawled?: number } }[];
  };
  sources: { id: string; url: string; domain: string; retrieved_at: string; digest: string; kind?: string; title?: string; relevance?: SearchRelevance | null }[];
  gaps: { task_id: string; name: string; reason: string }[];
  images?: { id: string; title: string; url: string; source_url: string; retrieved_at: string; digest: string; relevance?: SearchRelevance | null }[];
}

export function apiResearchReports(query = "", offset = 0, signal?: AbortSignal) {
  const params = new URLSearchParams({ query, offset: String(offset), limit: "30" });
  return request<{ items: ResearchReportSummary[]; total: number }>(`/api/agent-runtime/reports?${params}`, { signal, cache: "no-store" });
}

export function apiResearchReport(identity: string, signal?: AbortSignal) {
  return request<ResearchReport>(`/api/agent-runtime/reports/${encodeURIComponent(identity)}`, { signal, cache: "no-store" });
}

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

  window.dispatchEvent(new CustomEvent("nova-playback", { detail: { active: true, text, token } }));
  try {
    const result = await request<{ success: boolean; error?: string }>("/voice/speak", {
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
    if (result.success === false && result.error !== "interrupted") {
      throw new Error(result.error || "Speech playback failed");
    }
  } finally {
    if (token === speakToken) window.dispatchEvent(new CustomEvent("nova-playback", { detail: { active: false, token } }));
  }
}

export async function apiVoiceStop(): Promise<{ ok: boolean; stop?: { success?: boolean; stopped?: string[] } }> {
  // Invalidate any pending/in-flight speak call in the client layer.
  const token = ++speakToken;
  window.dispatchEvent(new Event("nova-speech-interrupted"));
  const result = await request<{ ok: boolean; stop?: { success?: boolean; stopped?: string[] } }>("/voice/stop", {
    method: "POST",
  });
  if (token === speakToken) window.dispatchEvent(new CustomEvent("nova-playback", { detail: { active: false, token } }));
  return result;
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

export async function apiIdentitySync(prefer: "face" | "voice" = "face"): Promise<IdentitySyncResponse> {
  return request<IdentitySyncResponse>("/identity/sync", {
    method: "POST",
    body: JSON.stringify({ prefer }),
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

export async function apiGmailMessage(messageId: string, full = true): Promise<{ ok: boolean; message?: GmailMessage; error?: string }> {
  return request(`/gmail/message/${encodeURIComponent(messageId)}?full=${full ? "true" : "false"}`);
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

// ── Security ──────────────────────────────────────────────────
export async function apiSecurityStatus(): Promise<SecurityStatusResponse> {
  return request<SecurityStatusResponse>("/security/status");
}

export async function apiSecurityScan(): Promise<{ ok: boolean; findings: number; error?: string }> {
  return request("/security/scan", { method: "POST" });
}

export async function apiSecurityFindings(): Promise<{ ok: boolean; count: number; findings: SecurityFinding[] }> {
  return request("/security/findings");
}

export async function apiSecurityTimeline(limit = 50): Promise<{ ok: boolean; count: number; events: SecurityTimelineEvent[] }> {
  return request(`/security/timeline?limit=${limit}`);
}

export async function apiSecurityAgents(): Promise<{ ok: boolean; count: number; agents: SecurityAgentRecord[] }> {
  return request<{ ok: boolean; count: number; agents: SecurityAgentRecord[] }>("/security/agents");
}

export async function apiSecurityAssets(): Promise<{ ok: boolean; count: number; assets: SecurityAsset[] }> {
  return request<{ ok: boolean; count: number; assets: SecurityAsset[] }>("/security/assets");
}

export async function apiSecurityPull(req: {
  agent_url: string;
  timeout?: number;
  token?: string;
  verify_ssl?: boolean;
}): Promise<{ ok: boolean; pulled_from: string; agent: SecurityAgentRecord }> {
  return request<{ ok: boolean; pulled_from: string; agent: SecurityAgentRecord }>("/security/agents/pull", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

// ── Vision / Face ───────────────────────────────────────────
export async function apiVisionFaceAnalyze(imageBase64: string): Promise<FaceFrameAnalysisResponse> {
  return request<FaceFrameAnalysisResponse>("/vision/face/analyze", {
    method: "POST",
    body: JSON.stringify({ image_base64: imageBase64 }),
  });
}

export async function apiVisionFaceEnroll(payload: {
  name: string;
  role: "admin" | "user";
  imageBase64?: string;
}): Promise<FaceEnrollResponse> {
  return request<FaceEnrollResponse>("/vision/face/enroll", {
    method: "POST",
    body: JSON.stringify({
      name: payload.name,
      role: payload.role,
      image_base64: payload.imageBase64,
    }),
  });
}

export async function apiVisionFaceRecognize(imageBase64?: string): Promise<FaceRecognizeResponse> {
  return request<FaceRecognizeResponse>("/vision/face/recognize", {
    method: "POST",
    body: JSON.stringify({ image_base64: imageBase64 }),
  });
}

export async function apiVisionFaceProfiles(): Promise<{ ok: boolean; profiles: FaceProfileSummary[]; error?: string }> {
  return request<{ ok: boolean; profiles: FaceProfileSummary[]; error?: string }>("/vision/face/profiles");
}

export async function apiVisionFaceDeleteProfile(profileId: string): Promise<{ ok: boolean; deleted?: { id: string; name: string; role: string }; error?: string }> {
  return request(`/vision/face/profiles/${encodeURIComponent(profileId)}`, { method: "DELETE" });
}

export async function apiGetFacialRecognition(): Promise<{ ok: boolean; enabled: boolean; error?: string }> {
  return request<{ ok: boolean; enabled: boolean; error?: string }>("/vision/face/recognition");
}

export async function apiSetFacialRecognition(enabled: boolean): Promise<{ ok: boolean; enabled: boolean; error?: string }> {
  return request<{ ok: boolean; enabled: boolean; error?: string }>("/vision/face/recognition", {
    method: "POST",
    body: JSON.stringify({ enabled }),
  });
}

export async function apiVisionFaceSession(): Promise<{ ok: boolean; session: FacePresenceSession; error?: string }> {
  return request<{ ok: boolean; session: FacePresenceSession; error?: string }>("/vision/face/session");
}

export async function apiVisionFaceSessionReset(): Promise<{ ok: boolean; session: FacePresenceSession; error?: string }> {
  return request<{ ok: boolean; session: FacePresenceSession; error?: string }>("/vision/face/session/reset", {
    method: "POST",
  });
}

export async function apiVisionFacePolicyGet(): Promise<{ ok: boolean; policy: FaceAdvancedPolicy; error?: string }> {
  return request<{ ok: boolean; policy: FaceAdvancedPolicy; error?: string }>("/vision/face/policy");
}

export async function apiVisionFacePolicySet(policy: Partial<FaceAdvancedPolicy>): Promise<{ ok: boolean; policy: FaceAdvancedPolicy; error?: string }> {
  return request<{ ok: boolean; policy: FaceAdvancedPolicy; error?: string }>("/vision/face/policy", {
    method: "POST",
    body: JSON.stringify(policy),
  });
}
