import type { AvatarBrainEvent } from "./types";

export class SpeechBubbleController {
  private speechText: string | null = null;

  get text() {
    return this.speechText;
  }

  reset() {
    this.speechText = null;
  }

  update(event: AvatarBrainEvent) {
    const value = event.payload?.text;

    if (event.name === "response_started" || event.name === "speaking_started") {
      this.speechText = typeof value === "string" ? value : "";
      return this.speechText;
    }

    if (event.name === "response_finished" || event.name === "speaking_finished") {
      this.speechText = null;
      return this.speechText;
    }

    if (event.name === "snapshot" && typeof value === "string") {
      this.speechText = value;
      return this.speechText;
    }

    return this.speechText;
  }
}
