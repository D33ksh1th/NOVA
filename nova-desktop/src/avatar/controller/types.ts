import type { AvatarState } from "@/types";

export type AvatarEngineState = AvatarState;

export type AvatarEmotion =
  | "neutral"
  | "happy"
  | "concerned"
  | "thinking"
  | "listening"
  | "sleepy"
  | "curious"
  | "proud"
  | "relaxed";

export type EyeTarget =
  | "cursor"
  | "user_face"
  | "speech_bubble"
  | "microphone"
  | "notification"
  | "ambient";

export type AvatarBrainEventName =
  | "snapshot"
  | "thinking_started"
  | "thinking_finished"
  | "listening_started"
  | "listening_finished"
  | "response_started"
  | "response_finished"
  | "speaking_started"
  | "speaking_finished"
  | "sleep_started"
  | "sleep_finished"
  | "user_arrived"
  | "task_completed"
  | "good_morning"
  | "good_night"
  | "idle_tick";

export interface AvatarBrainEvent {
  name: AvatarBrainEventName;
  timestamp: number;
  payload?: Record<string, unknown>;
}

export interface AvatarEngineSnapshot {
  state: AvatarEngineState;
  emotion: AvatarEmotion;
  speechText: string | null;
  animationOverride: string | null;
  eyeTarget: EyeTarget;
  lastEvent: AvatarBrainEventName;
}
