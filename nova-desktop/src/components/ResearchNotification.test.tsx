import { act, StrictMode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { ResearchNotification } from "./ResearchNotification";
import { apiResearchReports, apiVoiceSpeak } from "@/services/api";
import { useChatStore } from "@/stores/useChatStore";
import { useAvatarStore } from "@/stores/useAvatarStore";
import { useSettingsStore } from "@/stores/useSettingsStore";
import { useAppStore } from "@/stores/useAppStore";

vi.mock("@/services/api", () => ({ apiResearchReports: vi.fn(), apiVoiceSpeak: vi.fn() }));
const report = { id: "report-test", topic: "Local speech models", status: "RUNNING", created_at: "2025-01-01T00:00:00Z" };

describe("Research completion notifications", () => {
  let root: Root;
  let container: HTMLDivElement;
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
    vi.mocked(apiResearchReports).mockResolvedValue({ items: [report], total: 1 });
    vi.mocked(apiVoiceSpeak).mockResolvedValue();
    useChatStore.setState({ messages: [], isStreaming: false });
    useAvatarStore.setState({ state: "idle" });
    useSettingsStore.setState({ voice: { ...useSettingsStore.getState().voice, speakBack: true } });
    container = document.createElement("div"); document.body.append(container); root = createRoot(container);
  });
  afterEach(async () => { await act(async () => root.unmount()); container.remove(); vi.clearAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });

  async function finish(status = "COMPLETED") {
    vi.mocked(apiResearchReports).mockResolvedValue({ items: [{ ...report, status }], total: 1 });
    await act(async () => vi.advanceTimersByTimeAsync(4000));
  }

  it("speaks once and opens the exact completed report", async () => {
    await act(async () => root.render(<StrictMode><ResearchNotification /></StrictMode>));
    expect(apiVoiceSpeak).not.toHaveBeenCalled();
    await finish();
    expect(apiVoiceSpeak).toHaveBeenCalledWith("Your research report is ready.", expect.any(Object));
    expect(useChatStore.getState().messages[0].details?.report_id).toBe(report.id);
    await act(async () => container.querySelector<HTMLButtonElement>("button")!.click());
    expect(useAppStore.getState().activeReportId).toBe(report.id);
    expect(useAppStore.getState().currentPage).toBe("skills");
    await act(async () => vi.advanceTimersByTimeAsync(12000));
    expect(apiVoiceSpeak).toHaveBeenCalledTimes(1);
    expect(useChatStore.getState().messages).toHaveLength(1);
    await act(async () => container.querySelector<HTMLButtonElement>('[aria-label="Dismiss research notification"]')!.click());
    expect(container.textContent).toBe("");
  });

  it("does not announce historical completed reports on startup", async () => {
    vi.mocked(apiResearchReports).mockResolvedValue({ items: [{ ...report, status: "COMPLETED" }], total: 1 });
    await act(async () => root.render(<ResearchNotification />));
    expect(container.textContent).toBe("");
    expect(apiVoiceSpeak).not.toHaveBeenCalled();
  });

  it("handles requests that finish before the first poll", async () => {
    useChatStore.getState().addMessage({ role: "nova", content: "On it.", meta: { action: "agent_research_started" }, details: { report_id: report.id } });
    vi.mocked(apiResearchReports).mockResolvedValue({ items: [{ ...report, status: "COMPLETED" }], total: 1 });
    await act(async () => root.render(<ResearchNotification />));
    expect(apiVoiceSpeak).toHaveBeenCalledTimes(1);
  });

  it.each(["PARTIAL", "FAILED", "CANCELLED", "INTERRUPTED"])("reports %s honestly", async status => {
    await act(async () => root.render(<ResearchNotification />));
    await finish(status);
    expect(container.textContent).not.toContain("Your research report is ready.");
    expect(container.textContent).toContain(status === "PARTIAL" ? "gaps" : status === "FAILED" ? "couldn't" : status.toLowerCase());
    expect(container.querySelector("button")).not.toBeNull();
  });

  it("defers speech while a conversation is active", async () => {
    await act(async () => root.render(<ResearchNotification />));
    useAvatarStore.setState({ state: "listening" });
    await finish();
    expect(container.textContent).toContain("report is ready");
    expect(apiVoiceSpeak).not.toHaveBeenCalled();
    useAvatarStore.setState({ state: "idle" });
    await act(async () => vi.advanceTimersByTimeAsync(1000));
    expect(apiVoiceSpeak).toHaveBeenCalledTimes(1);
  });

  it("respects speak-back being off and recovers after a polling failure", async () => {
    await act(async () => root.render(<ResearchNotification />));
    useSettingsStore.setState({ voice: { ...useSettingsStore.getState().voice, speakBack: false } });
    vi.mocked(apiResearchReports).mockRejectedValueOnce(new Error("offline"));
    await finish();
    expect(container.textContent).toBe("");
    await act(async () => vi.advanceTimersByTimeAsync(4000));
    expect(container.textContent).toContain("report is ready");
    expect(apiVoiceSpeak).not.toHaveBeenCalled();
  });

  it("aborts polling on unmount", async () => {
    await act(async () => root.render(<ResearchNotification />));
    const signal = vi.mocked(apiResearchReports).mock.calls[0][2];
    await act(async () => root.render(null));
    expect(signal?.aborted).toBe(true);
    await act(async () => vi.advanceTimersByTimeAsync(12000));
    expect(apiResearchReports).toHaveBeenCalledTimes(1);
  });
});