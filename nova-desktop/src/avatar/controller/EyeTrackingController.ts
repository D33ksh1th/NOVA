import type { AvatarBrainEvent, EyeTarget } from "./types";

export class EyeTrackingController {
  private target: EyeTarget = "ambient";

  get current() {
    return this.target;
  }

  reset() {
    this.target = "ambient";
  }

  update(event: AvatarBrainEvent) {
    switch (event.name) {
      case "listening_started":
        this.target = "microphone";
        break;
      case "thinking_started":
        this.target = "speech_bubble";
        break;
      case "response_started":
      case "speaking_started":
        this.target = "speech_bubble";
        break;
      case "user_arrived":
        this.target = "user_face";
        break;
      case "task_completed":
        this.target = "notification";
        break;
      default:
        this.target = "cursor";
        break;
    }

    return this.target;
  }
}
