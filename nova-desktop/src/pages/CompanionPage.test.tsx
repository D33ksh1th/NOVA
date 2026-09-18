import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { CompanionPage } from "./CompanionPage";
import { useAppStore } from "@/stores/useAppStore";
import { useAvatarStore } from "@/stores/useAvatarStore";
import { apiConnectedDevices } from "@/services/api";
import { useNovaChat } from "@/hooks/useNovaChat";

vi.mock("@/components/Avatar/CoreSignal", () => ({ CoreSignal: () => <canvas aria-label="NOVA signal" /> }));
vi.mock("@/components/NowPlaying", () => ({ NowPlaying: ({ onClose }: { onClose: () => void }) => <section aria-label="Apple Music player"><button aria-label="Close music player" onClick={onClose}>Close</button></section> }));
vi.mock("@/components/Chat/ChatPanel", () => ({ ChatPanel: () => <textarea aria-label="Message NOVA" /> }));
vi.mock("@/services/api", () => ({ apiConnectedDevices: vi.fn() }));
vi.mock("@/hooks/useNovaChat", () => ({ useNovaChat: vi.fn(() => ({ sendMessage: vi.fn() })) }));

describe("Core workspace", () => {
  let container: HTMLDivElement;
  let root: Root;
  beforeEach(() => {
    vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
    useAppStore.setState({ rightPanelOpen: true, musicPlayerOpen: true });
    useAvatarStore.setState({ streamConnected: false });
    vi.mocked(apiConnectedDevices).mockRejectedValue(new Error("offline"));
    container = document.createElement("div"); document.body.append(container); root = createRoot(container);
  });
  afterEach(async () => { await act(async () => root.unmount()); container.remove(); useAppStore.persist.clearStorage(); vi.unstubAllGlobals(); });
  it("does not invent device health or tasks when disconnected", async () => {
    await act(async () => root.render(<CompanionPage />));
    expect(container.textContent).toContain("Waiting for a connection.");
    expect(container.textContent).toContain("Device snapshot unavailable.");
    expect(container.textContent).not.toContain("Implement Auth Module");
    expect(container.textContent).not.toContain("92%");
  });
  it("keeps research navigation and overview toggle functional", async () => {
    await act(async () => root.render(<CompanionPage />));
    await act(async () => [...container.querySelectorAll<HTMLButtonElement>("button")].find(button => button.textContent === "Research")!.click());
    expect(useAppStore.getState().currentPage).toBe("skills");
    await act(async () => container.querySelector<HTMLButtonElement>('[aria-label="Hide overview"]')!.click());
    expect(container.querySelector('[aria-label="Core overview"]')).toBeNull();
  });
  it("closes and reopens the music player without requesting playback", async () => {
    const sendMessage = vi.fn();
    vi.mocked(useNovaChat).mockReturnValue({ sendMessage, stopSpeaking: vi.fn() });
    await act(async () => root.render(<CompanionPage />));
    expect(sendMessage).not.toHaveBeenCalled();
    expect(container.querySelector('[aria-label="Apple Music player"]')).not.toBeNull();
    await act(async () => container.querySelector<HTMLButtonElement>('[aria-label="Close music player"]')!.click());
    expect(container.querySelector('[aria-label="Apple Music player"]')).toBeNull();
    expect(container.querySelector('[title="Show music player"]')?.getAttribute("aria-expanded")).toBe("false");
    await act(async () => [...container.querySelectorAll<HTMLButtonElement>("button")].find(button => button.textContent === "Music")!.click());
    expect(container.querySelector('[aria-label="Apple Music player"]')).not.toBeNull();
    expect(sendMessage).not.toHaveBeenCalled();
  });

  it("keeps the player closed after rehydration and remembers explicitly reopening it", async () => {
    await act(async () => root.render(<CompanionPage />));
    await act(async () => container.querySelector<HTMLButtonElement>('[aria-label="Close music player"]')!.click());
    const saved = localStorage.getItem("nova-app-store")!;
    expect(JSON.parse(saved).state.musicPlayerOpen).toBe(false);
    await act(async () => root.render(null));
    useAppStore.setState({ musicPlayerOpen: true });
    localStorage.setItem("nova-app-store", saved);
    await act(async () => { await useAppStore.persist.rehydrate(); root.render(<CompanionPage />); });
    expect(container.querySelector('[aria-label="Apple Music player"]')).toBeNull();
    expect(container.querySelector('[title="Show music player"]')?.getAttribute("aria-expanded")).toBe("false");
    await act(async () => container.querySelector<HTMLButtonElement>('[title="Show music player"]')!.click());
    expect(container.querySelector('[aria-label="Apple Music player"]')).not.toBeNull();
    expect(JSON.parse(localStorage.getItem("nova-app-store")!).state.musicPlayerOpen).toBe(true);
  });
});