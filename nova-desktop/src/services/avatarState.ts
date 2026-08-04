import type { AvatarState } from "@/types";

export const AVATAR_EVENT_TO_STATE: Record<string, AvatarState> = {
  listening_started: "listening",
  listening_completed: "idle",
  thinking_started: "thinking",
  thinking_completed: "idle",
  speaking_started: "speaking",
  speaking_completed: "idle",
  idle: "idle",
};

const VALID_STATES = new Set<AvatarState>([
  "idle",
  "listening",
  "thinking",
  "speaking",
  "sleeping",
  "happy",
  "curious",
  "concerned",
  "excited",
]);

export function normalizeAvatarState(input: unknown): AvatarState {
  const value = String(input ?? "idle").toLowerCase().trim() as AvatarState;
  return VALID_STATES.has(value) ? value : "idle";
}

export function stateFromAvatarEvent(eventName: unknown): AvatarState {
  const key = String(eventName ?? "").toLowerCase().trim();
  return AVATAR_EVENT_TO_STATE[key] ?? "idle";
}
