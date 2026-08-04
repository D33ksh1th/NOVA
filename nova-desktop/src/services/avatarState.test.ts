import {
  AVATAR_EVENT_TO_STATE,
  normalizeAvatarState,
  stateFromAvatarEvent,
} from "@/services/avatarState";

describe("avatarState mapping", () => {
  it("maps known events to states", () => {
    expect(stateFromAvatarEvent("listening_started")).toBe("listening");
    expect(stateFromAvatarEvent("thinking_started")).toBe("thinking");
    expect(stateFromAvatarEvent("speaking_completed")).toBe("idle");
  });

  it("normalizes known states and falls back for unknown", () => {
    expect(normalizeAvatarState("Speaking")).toBe("speaking");
    expect(normalizeAvatarState("curious")).toBe("curious");
    expect(normalizeAvatarState("unknown_state")).toBe("idle");
  });

  it("exports non-empty event map", () => {
    expect(Object.keys(AVATAR_EVENT_TO_STATE).length).toBeGreaterThan(0);
  });
});
