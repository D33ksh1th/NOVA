import type { AvatarBrainEvent, AvatarEmotion } from "./types";

const EVENT_EMOTIONS: Partial<Record<AvatarBrainEvent["name"], AvatarEmotion>> = {
  listening_started: "listening",
  listening_finished: "neutral",
  thinking_started: "thinking",
  thinking_finished: "relaxed",
  response_started: "proud",
  response_finished: "neutral",
  sleep_started: "sleepy",
  sleep_finished: "relaxed",
  good_night: "sleepy",
  good_morning: "curious",
  task_completed: "happy",
  user_arrived: "curious",
};

export class EmotionController {
  private emotion: AvatarEmotion = "neutral";

  get current() {
    return this.emotion;
  }

  reset() {
    this.emotion = "neutral";
  }

  update(event: AvatarBrainEvent) {
    if (event.name === "snapshot") {
      const raw = event.payload?.emotion;
      if (typeof raw === "string") {
        this.emotion = this.normalize(raw);
      }
      return this.emotion;
    }

    this.emotion = EVENT_EMOTIONS[event.name] ?? this.emotion;
    return this.emotion;
  }

  private normalize(value: string): AvatarEmotion {
    const key = value.trim().toLowerCase();
    const map: Record<string, AvatarEmotion> = {
      neutral: "neutral",
      happy: "happy",
      concerned: "concerned",
      thinking: "thinking",
      listening: "listening",
      sleepy: "sleepy",
      curious: "curious",
      proud: "proud",
      relaxed: "relaxed",
    };
    return map[key] ?? "neutral";
  }
}
