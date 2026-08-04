// ============================================================
// NOVA SSE Client — connects to /avatar/events
// ============================================================
import type { AvatarState } from "@/types";
import {
  AVATAR_EVENT_TO_STATE,
  normalizeAvatarState,
  stateFromAvatarEvent,
} from "@/services/avatarState";

export type SSEHandler = (state: AvatarState, eventName: string) => void;
export type SSEStatusHandler = (connected: boolean) => void;
export type SSEPayload = Record<string, unknown>;

export class AvatarSSEClient {
  private source: EventSource | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private destroyed = false;
  private onState: (state: AvatarState, eventName: string, payload?: SSEPayload) => void;
  private onStatus: SSEStatusHandler;
  private url: string;

  constructor(
    url: string,
    onState: (state: AvatarState, eventName: string, payload?: SSEPayload) => void,
    onStatus: SSEStatusHandler
  ) {
    this.url = url;
    this.onState = onState;
    this.onStatus = onStatus;
  }

  connect() {
    if (this.destroyed) return;
    this.cleanup();

    const src = new EventSource(this.url);
    this.source = src;

    src.onopen = () => {
      this.onStatus(true);
      if (this.reconnectTimer) {
        clearTimeout(this.reconnectTimer);
        this.reconnectTimer = null;
      }
    };

    src.onerror = () => {
      this.onStatus(false);
      src.close();
      if (!this.destroyed) {
        this.reconnectTimer = setTimeout(() => this.connect(), 2500);
      }
    };

    src.addEventListener("snapshot", (e) => {
      const p = tryParse(e.data);
      if (p?.state) this.onState(normalizeAvatarState(p.state), "snapshot", p);
    });

    Object.entries(AVATAR_EVENT_TO_STATE).forEach(([name, state]) => {
      src.addEventListener(name, (e) => {
        const p = tryParse(e.data);
        const nextState = p?.state ? normalizeAvatarState(p.state) : state;
        this.onState(nextState, name, p ?? undefined);
      });
    });

    src.onmessage = (e) => {
      const p = tryParse(e.data);
      if (!p) return;
      const state = p.state
        ? normalizeAvatarState(p.state)
        : stateFromAvatarEvent(p.event);
      this.onState(state, (p.event as string) || "message", p);
    };
  }

  private cleanup() {
    if (this.source) {
      this.source.close();
      this.source = null;
    }
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  destroy() {
    this.destroyed = true;
    this.cleanup();
  }
}

function tryParse(raw: string) {
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}
