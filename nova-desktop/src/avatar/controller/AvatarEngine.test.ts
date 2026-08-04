import { describe, expect, it } from "vitest";
import { AvatarEngine } from "./AvatarEngine";

describe("AvatarEngine", () => {
  it("maps listening and speaking lifecycle into snapshot state", () => {
    const engine = new AvatarEngine();
    const snapshots: Array<{ state: string; emotion: string; speechText: string | null }> = [];

    const off = engine.onSnapshot((s) => {
      snapshots.push({ state: s.state, emotion: s.emotion, speechText: s.speechText });
    });

    engine.ingest("listening_started", {});
    engine.ingest("response_started", { text: "hello" });
    engine.ingest("response_finished", {});

    const latest = snapshots[snapshots.length - 1];

    expect(snapshots.some((s) => s.state === "listening")).toBe(true);
    expect(snapshots.some((s) => s.state === "speaking")).toBe(true);
    expect(latest.state).toBe("idle");
    expect(latest.speechText).toBeNull();

    off();
    engine.stop();
  });

  it("normalizes legacy completed events", () => {
    const engine = new AvatarEngine();
    let latestState = "idle";

    const off = engine.onSnapshot((s) => {
      latestState = s.state;
    });

    engine.ingest("thinking_started", {});
    expect(latestState).toBe("thinking");

    engine.ingest("thinking_completed", {});
    expect(latestState).toBe("idle");

    off();
    engine.stop();
  });
});
