import { AvatarController } from "./AvatarController";
import { EventBus } from "./EventBus";
import { IdleScheduler } from "./IdleScheduler";
import type { AvatarBrainEvent, AvatarBrainEventName, AvatarEngineSnapshot } from "./types";

type SnapshotListener = (snapshot: AvatarEngineSnapshot) => void;

export class AvatarEngine {
  private readonly bus = new EventBus<AvatarBrainEvent>();
  private readonly controller = new AvatarController();
  private readonly idleScheduler: IdleScheduler;
  private readonly listeners = new Set<SnapshotListener>();

  constructor() {
    this.idleScheduler = new IdleScheduler((event) => this.emit(event));
    this.registerReducers();
  }

  start() {
    this.idleScheduler.start();
  }

  stop() {
    this.idleScheduler.stop();
    this.bus.clear();
    this.listeners.clear();
  }

  onSnapshot(listener: SnapshotListener) {
    this.listeners.add(listener);
    listener(this.controller.getSnapshot());

    return () => {
      this.listeners.delete(listener);
    };
  }

  ingest(eventName: string, payload?: Record<string, unknown>) {
    const name = this.normalizeEventName(eventName);
    this.emit({
      name,
      payload: payload ?? {},
      timestamp: Date.now(),
    });

    if (name !== "idle_tick") {
      this.idleScheduler.reset();
    }
  }

  private emit(event: AvatarBrainEvent) {
    this.bus.emit(event);
  }

  private registerReducers() {
    const names: AvatarBrainEventName[] = [
      "snapshot",
      "thinking_started",
      "thinking_finished",
      "listening_started",
      "listening_finished",
      "response_started",
      "response_finished",
      "speaking_started",
      "speaking_finished",
      "sleep_started",
      "sleep_finished",
      "user_arrived",
      "task_completed",
      "good_morning",
      "good_night",
      "idle_tick",
    ];

    names.forEach((name) => {
      this.bus.on(name, (event) => {
        const snapshot = this.controller.reduce(event);
        this.listeners.forEach((listener) => listener(snapshot));
      });
    });
  }

  private normalizeEventName(value: string): AvatarBrainEventName {
    const key = value.trim().toLowerCase();
    const aliases: Record<string, AvatarBrainEventName> = {
      thinking_completed: "thinking_finished",
      listening_completed: "listening_finished",
      speaking_completed: "speaking_finished",
    };

    const valid = new Set<AvatarBrainEventName>([
      "snapshot",
      "thinking_started",
      "thinking_finished",
      "listening_started",
      "listening_finished",
      "response_started",
      "response_finished",
      "speaking_started",
      "speaking_finished",
      "sleep_started",
      "sleep_finished",
      "user_arrived",
      "task_completed",
      "good_morning",
      "good_night",
      "idle_tick",
    ]);

    const resolved = aliases[key] ?? (key as AvatarBrainEventName);
    return valid.has(resolved) ? resolved : "snapshot";
  }
}
