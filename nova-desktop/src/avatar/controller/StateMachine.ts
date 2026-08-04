import type { AvatarState } from "@/types";
import type { AvatarBrainEventName } from "./types";

const DEFAULT: AvatarState = "idle";

const TRANSITIONS: Partial<Record<AvatarBrainEventName, AvatarState>> = {
  thinking_started: "thinking",
  thinking_finished: "idle",
  listening_started: "listening",
  listening_finished: "idle",
  response_started: "speaking",
  response_finished: "idle",
  speaking_started: "speaking",
  speaking_finished: "idle",
  sleep_started: "sleeping",
  sleep_finished: "idle",
  good_night: "sleeping",
  good_morning: "focused",
  user_arrived: "curious",
  task_completed: "happy",
};

export class StateMachine {
  private currentState: AvatarState = DEFAULT;

  get state() {
    return this.currentState;
  }

  reset(nextState: AvatarState = DEFAULT) {
    this.currentState = nextState;
  }

  transition(eventName: AvatarBrainEventName, snapshotState?: unknown) {
    if (eventName === "snapshot" && typeof snapshotState === "string") {
      this.currentState = this.normalize(snapshotState);
      return this.currentState;
    }

    this.currentState = TRANSITIONS[eventName] ?? this.currentState;
    return this.currentState;
  }

  private normalize(raw: string): AvatarState {
    const value = raw.trim().toLowerCase();
    const valid = new Set<AvatarState>([
      "idle",
      "listening",
      "thinking",
      "speaking",
      "sleeping",
      "focused",
      "relaxed",
      "proud",
      "shy",
      "happy",
      "curious",
      "concerned",
      "excited",
    ]);

    return valid.has(value as AvatarState) ? (value as AvatarState) : DEFAULT;
  }
}
