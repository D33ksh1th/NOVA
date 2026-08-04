import type { AvatarBrainEvent } from "./types";

export interface VisemeFrame {
  phoneme: string;
  weight: number;
}

const SIMPLE_VISEME_MAP: Array<{ pattern: RegExp; viseme: string }> = [
  { pattern: /[aeiou]/i, viseme: "AA" },
  { pattern: /[fv]/i, viseme: "FV" },
  { pattern: /[bmp]/i, viseme: "MBP" },
  { pattern: /[lwq]/i, viseme: "WQ" },
];

export class LipSyncController {
  private active = false;

  get isActive() {
    return this.active;
  }

  reset() {
    this.active = false;
  }

  onEvent(event: AvatarBrainEvent) {
    if (event.name === "response_started" || event.name === "speaking_started") {
      this.active = true;
    }

    if (event.name === "response_finished" || event.name === "speaking_finished") {
      this.active = false;
    }
  }

  buildFrames(text: string): VisemeFrame[] {
    if (!text.trim()) {
      return [{ phoneme: "Rest", weight: 1 }];
    }

    return text
      .slice(0, 24)
      .split("")
      .map((ch) => {
        const hit = SIMPLE_VISEME_MAP.find((m) => m.pattern.test(ch));
        return {
          phoneme: hit?.viseme ?? "Rest",
          weight: hit ? 0.85 : 0.25,
        };
      });
  }
}
