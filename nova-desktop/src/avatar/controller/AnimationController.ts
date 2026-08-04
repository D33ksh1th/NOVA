import type { AvatarState } from "@/types";
import type { AvatarBrainEventName, AvatarEmotion } from "./types";

const EVENT_CLIP_OVERRIDE: Partial<Record<AvatarBrainEventName, string>> = {
  task_completed: "NOVA_Celebrate",
  good_morning: "NOVA_Wake_Up",
  good_night: "NOVA_Sleep",
};

const EMOTION_FALLBACK: Partial<Record<AvatarEmotion, string>> = {
  happy: "NOVA_Tail_Wag",
  thinking: "NOVA_Thinking",
  listening: "NOVA_Listen",
  sleepy: "NOVA_Sleep",
  proud: "NOVA_Observe_User",
  curious: "NOVA_Look_Around",
  concerned: "NOVA_Concerned",
};

const STATE_FALLBACK: Partial<Record<AvatarState, string>> = {
  idle: "NOVA_Idle_01",
  listening: "NOVA_Listen",
  thinking: "NOVA_Thinking",
  speaking: "NOVA_Talking",
  sleeping: "NOVA_Sleep",
  focused: "NOVA_Observe_User",
  relaxed: "NOVA_Idle_03",
  proud: "NOVA_Sit",
  shy: "NOVA_Idle_02",
  happy: "NOVA_Celebrate",
  curious: "NOVA_Look_Around",
  concerned: "NOVA_Concerned",
  excited: "NOVA_Happy_Jump",
};

export class AnimationController {
  private clipOverride: string | null = null;

  get override() {
    return this.clipOverride;
  }

  reset() {
    this.clipOverride = null;
  }

  choose(state: AvatarState, emotion: AvatarEmotion, eventName: AvatarBrainEventName) {
    this.clipOverride =
      EVENT_CLIP_OVERRIDE[eventName] ??
      EMOTION_FALLBACK[emotion] ??
      STATE_FALLBACK[state] ??
      null;

    return this.clipOverride;
  }
}
