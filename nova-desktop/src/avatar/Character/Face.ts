import type { AvatarEmotion } from "@/avatar/controller";

export interface FaceBlendTarget {
  blink: number;
  smile: number;
  concern: number;
  jawOpen: number;
}

export function faceFromEmotion(emotion: AvatarEmotion): FaceBlendTarget {
  switch (emotion) {
    case "happy":
      return { blink: 0.1, smile: 0.7, concern: 0, jawOpen: 0.08 };
    case "concerned":
      return { blink: 0.2, smile: 0, concern: 0.65, jawOpen: 0.02 };
    case "thinking":
      return { blink: 0.16, smile: 0.08, concern: 0.2, jawOpen: 0.03 };
    case "sleepy":
      return { blink: 0.85, smile: 0, concern: 0, jawOpen: 0.01 };
    default:
      return { blink: 0.12, smile: 0.05, concern: 0.05, jawOpen: 0.02 };
  }
}
