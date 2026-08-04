import type { AvatarState } from "@/types";

export function tailAmplitudeForState(state: AvatarState): number {
  switch (state) {
    case "sleeping":
      return 0.02;
    case "thinking":
      return 0.08;
    case "listening":
      return 0.1;
    case "happy":
    case "excited":
      return 0.22;
    case "concerned":
      return 0.04;
    default:
      return 0.06;
  }
}
