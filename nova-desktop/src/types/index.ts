// ============================================================
// NOVA Desktop — Shared Types
// ============================================================

// ── Avatar ────────────────────────────────────────────────────
export type AvatarState =
  | "idle"
  | "listening"
  | "thinking"
  | "speaking"
  | "sleeping"
  | "focused"
  | "relaxed"
  | "proud"
  | "shy"
  | "happy"
  | "curious"
  | "concerned"
  | "excited";

export interface AvatarEvent {
  event: string;
  state: AvatarState;
  payload?: Record<string, unknown>;
  timestamp?: string;
}

// ── Chat ─────────────────────────────────────────────────────
export type MessageRole = "user" | "nova" | "system" | "error";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: Date;
  details?: Record<string, unknown>;
  meta?: {
    intent?: string;
    action?: string;
    source?: string;
    tts?: string;
    tokens?: number;
  };
  streaming?: boolean;
}

export interface ChatRequest {
  message: string;
  session_id?: string;
}

export interface ChatResponse {
  response: string;
  intent?: string;
  action?: string;
  plan_id?: string;
  tasks_executed?: number;
  steps?: unknown[];
  data?: Record<string, unknown>;
  initiative?: { message: string };
  reflected?: boolean;
}

// ── Voice ────────────────────────────────────────────────────
export type VoiceMode = "human" | "cat";
export type VoiceStyle = "natural" | "warm" | "clear" | "excited" | "calm";
export type AccentProfile =
  | "english_clear"
  | "english_jarvis";

export interface VoiceSettings {
  enabled: boolean;
  speakBack: boolean;
  mode: VoiceMode;
  style: VoiceStyle;
  accent: AccentProfile;
  rate: number;
  pitch: number;
  model: string;
  handsFreeWake: boolean;
  micEnabled: boolean;
}

export interface VoiceTextRequest {
  text: string;
  speak: boolean;
  speaker?: string;
  audio_base64?: string;
  audio_mime_type?: string;
  voice_mode?: VoiceMode;
  voice_style?: VoiceStyle;
  voice_rate?: number;
  voice_pitch?: number;
  voice_name?: string;
  accent_profile?: AccentProfile;
}

export interface VoiceTextResponse {
  response: string;
  intent?: string;
  action?: string;
  plan_id?: string;
  tasks_executed?: number;
  steps?: unknown[];
  data?: Record<string, unknown>;
  initiative?: { message: string };
  voice?: {
    metadata?: {
      synthesis?: { backend?: string };
    };
  };
}

export interface VoiceEnrollmentResponse {
  action?: string;
  response: string;
  data?: {
    session_id?: string | null;
    stage?: string;
    required_samples?: number;
    samples_collected?: number;
    completed?: boolean;
    profile?: {
      id?: string;
      name?: string;
      role?: string;
      samples?: number;
    };
  };
}

export interface VoiceSpeakerProfile {
  id: string;
  name: string;
  samples: number;
  role: string;
  created_at?: string;
  updated_at?: string;
}

// ── Memory ────────────────────────────────────────────────────
export interface MemoryEntry {
  id: string;
  content: string;
  category: string;
  timestamp: Date;
  tags?: string[];
}

// ── Navigation ────────────────────────────────────────────────
export type NavPage =
  | "companion"
  | "chat"
  | "mail"
  | "memory"
  | "tasks"
  | "skills"
  | "vision"
  | "voice"
  | "settings"
  | "developer";

// ── App ───────────────────────────────────────────────────────
export interface NovaStatus {
  backendConnected: boolean;
  avatarStreamConnected: boolean;
  voiceEnabled: boolean;
  micPermission: "granted" | "denied" | "unknown";
}

export interface ConnectedBluetoothDevice {
  name: string;
  address?: string;
  battery?: string | null;
}

export interface ConnectedExternalDevice {
  name: string;
  type?: string;
  transport?: string;
  connected?: string;
  manufacturer?: string;
}

export interface ConnectedDevicesResponse {
  ok: boolean;
  power?: {
    available?: boolean;
    source?: string | null;
    charging?: boolean | null;
    percentage?: number | null;
    state?: string | null;
  };
  wifi?: {
    connected?: boolean;
    ssid?: string | null;
    interface?: string | null;
    ssid_hidden?: boolean;
  };
  bluetooth?: {
    controller?: Record<string, unknown>;
    connected?: ConnectedBluetoothDevice[];
  };
  wired_external?: ConnectedExternalDevice[];
}

// ── Tasks ────────────────────────────────────────────────────
export type TaskStatus = "pending" | "in_progress" | "review" | "done";

export interface NovaTask {
  id: string;
  title: string;
  status: TaskStatus;
  priority?: "low" | "medium" | "high";
  project?: string;
  updatedAt?: Date;
}

// ── Gmail ─────────────────────────────────────────────────────
export type GmailUrgency = "critical" | "high" | "normal" | "low";

export interface GmailMessage {
  id: string;
  from: string;
  to?: string;
  subject: string;
  date?: string;
  snippet?: string;
  urgency: GmailUrgency;
  urgency_emoji: string;
  thread_id?: string;
  detected_at?: string;
}

export interface GmailInboxResponse {
  ok: boolean;
  count: number;
  messages: GmailMessage[];
  error?: string;
}

export interface GmailSendRequest {
  to: string;
  subject: string;
  body: string;
  html?: boolean;
}

export interface GmailStatusResponse {
  enabled: boolean;
  authenticated: boolean;
  credentials_present: boolean;
  poll_interval: number;
}

