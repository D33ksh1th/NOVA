import type { AvatarBrainEvent, AvatarBrainEventName } from "./types";

type EmitFn = (event: AvatarBrainEvent) => void;

export class IdleScheduler {
  private timer: ReturnType<typeof setInterval> | null = null;
  private readonly emit: EmitFn;
  private readonly intervalMs: number;

  constructor(emit: EmitFn, intervalMs = 20000) {
    this.emit = emit;
    this.intervalMs = intervalMs;
  }

  start() {
    if (this.timer) {
      return;
    }

    this.timer = setInterval(() => {
      this.emit(this.createEvent("idle_tick"));
    }, this.intervalMs);
  }

  stop() {
    if (!this.timer) {
      return;
    }
    clearInterval(this.timer);
    this.timer = null;
  }

  reset() {
    this.stop();
    this.start();
  }

  private createEvent(name: AvatarBrainEventName): AvatarBrainEvent {
    return {
      name,
      timestamp: Date.now(),
      payload: {},
    };
  }
}
