import type { EyeTarget } from "@/avatar/controller";

export interface EyeRigTarget {
  target: EyeTarget;
  yaw: number;
  pitch: number;
}

export function resolveEyeTarget(target: EyeTarget): EyeRigTarget {
  switch (target) {
    case "microphone":
      return { target, yaw: -0.15, pitch: -0.08 };
    case "speech_bubble":
      return { target, yaw: 0.05, pitch: 0.12 };
    case "user_face":
      return { target, yaw: 0, pitch: 0.04 };
    case "notification":
      return { target, yaw: 0.2, pitch: 0.1 };
    case "cursor":
      return { target, yaw: 0.08, pitch: 0 };
    default:
      return { target: "ambient", yaw: 0, pitch: 0 };
  }
}
