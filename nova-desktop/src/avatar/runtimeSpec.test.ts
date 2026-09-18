import {
  missingRequiredClips,
  resolveClipForState,
} from "@/avatar/runtimeSpec";

describe("runtimeSpec clip resolver", () => {
  it("prefers state-mapped clip names", () => {
    const available = ["NOVA_Idle_01", "NOVA_Thinking", "NOVA_Talking"];
    expect(resolveClipForState("thinking", available)).toBe("NOVA_Thinking");
    expect(resolveClipForState("speaking", available)).toBe("NOVA_Talking");
  });

  it("falls back to first clip when state clip is unavailable", () => {
    const available = ["FallbackLoop", "NOVA_Walk"];
    expect(resolveClipForState("sleeping", available)).toBe("FallbackLoop");
  });

  it("reports missing required clips", () => {
    const available = ["NOVA_Idle_01", "NOVA_Thinking", "NOVA_Talking"];
    const missing = missingRequiredClips(available);
    expect(missing.length).toBeGreaterThan(0);
    expect(missing).toContain("NOVA_Walk");
  });
});
