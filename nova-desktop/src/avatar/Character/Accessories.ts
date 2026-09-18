import type { AvatarState } from "@/types";

export interface PendantState {
  emissiveIntensity: number;
  color: string;
}

export function pendantForState(state: AvatarState): PendantState {
  if (state === "thinking") {
    return { emissiveIntensity: 1, color: "#38dfff" };
  }
  if (state === "speaking") {
    return { emissiveIntensity: 0.72, color: "#39ffc8" };
  }
  if (state === "sleeping") {
    return { emissiveIntensity: 0.18, color: "#5e78a0" };
  }
  return { emissiveIntensity: 0.45, color: "#38dfff" };
}
