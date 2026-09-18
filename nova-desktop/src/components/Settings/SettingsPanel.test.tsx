import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { SettingsPanel } from "./SettingsPanel";
import { useSettingsStore } from "@/stores/useSettingsStore";
import { apiVoiceSpeak, apiVoiceStop } from "@/services/api";

vi.mock("@/services/api", () => ({
  apiGetVoiceRecognition: vi.fn().mockResolvedValue({ enabled: false }),
  apiSetVoiceRecognition: vi.fn().mockResolvedValue({}),
  apiVoiceDeleteAllSpeakers: vi.fn(), apiVoiceDeleteSpeaker: vi.fn(), apiVoiceSetAdmin: vi.fn(),
  apiVoiceSettings: vi.fn().mockResolvedValue({}),
  apiVoiceSpeakers: vi.fn().mockResolvedValue({ speakers: [] }),
  apiVoiceSpeak: vi.fn().mockResolvedValue({}), apiVoiceStop: vi.fn().mockResolvedValue({}),
}));

describe("neural voice controls", () => {
  let container: HTMLDivElement;
  let root: Root;
  const originalVoice = useSettingsStore.getState().voice;
  beforeEach(() => {
    vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
    vi.clearAllMocks();
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
  });
  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    useSettingsStore.getState().setVoice(originalVoice);
    vi.unstubAllGlobals();
  });
  it("selects the female accent and previews the selected settings", async () => {
    await act(async () => root.render(<SettingsPanel />));
    const select = [...container.querySelectorAll("select")].find((item) => item.querySelector('option[value="english_amy"]'))!;
    await act(async () => { select.value = "english_amy"; select.dispatchEvent(new Event("change", { bubbles: true })); });
    expect(useSettingsStore.getState().voice).toMatchObject({ accent: "english_friday", style: "warm", rate: 180 });
    await act(async () => [...container.querySelectorAll<HTMLButtonElement>("button")].find((button) => button.textContent === "Preview voice")!.click());
    expect(apiVoiceSpeak).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ accent: "english_friday", rate: 180 }));
    await act(async () => container.querySelector<HTMLButtonElement>('[aria-label="Stop voice preview"]')!.click());
    expect(apiVoiceStop).toHaveBeenCalledOnce();
  });
  it("reports preview failures", async () => {
    vi.mocked(apiVoiceSpeak).mockRejectedValueOnce(new Error("offline"));
    await act(async () => root.render(<SettingsPanel />));
    await act(async () => [...container.querySelectorAll<HTMLButtonElement>("button")].find((button) => button.textContent === "Preview voice")!.click());
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("Voice preview unavailable");
  });
});