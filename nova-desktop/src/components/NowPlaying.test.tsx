import { act, StrictMode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { NowPlaying } from "./NowPlaying";
import { apiMusicControl, apiMusicStatus, type MusicSnapshot } from "@/services/music";

vi.mock("@/services/music", () => ({ apiMusicStatus: vi.fn(), apiMusicControl: vi.fn() }));
const snapshot: MusicSnapshot = {
  available: true, success: true, playback_state: "playing", position: 30,
  track: { id: "abc", title: "A quiet morning", artist: "Test artist", album: "Still", duration: 180, artwork_url: "data:image/png;base64,iVBORw0KGgo=" },
};

describe("Apple Music player", () => {
  let container: HTMLDivElement;
  let root: Root;
  beforeEach(() => {
    vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
    vi.mocked(apiMusicStatus).mockResolvedValue(snapshot);
    container = document.createElement("div"); document.body.append(container); root = createRoot(container);
  });
  afterEach(async () => { await act(async () => root.unmount()); container.remove(); vi.clearAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });
  it("shows actual artwork in a disc with only play/pause", async () => {
    await act(async () => root.render(<NowPlaying />));
    expect(container.textContent).toContain("Test artist");
    expect(container.textContent).toContain("A quiet morning");
    expect(container.querySelector("img")?.alt).toBe("Still artwork");
    expect(container.querySelector("progress")).toBeNull();
    expect(container.querySelectorAll("button")).toHaveLength(1);
    expect(container.querySelector(".nova-music-art")?.getAttribute("data-spinning")).toBe("true");
    expect(apiMusicControl).not.toHaveBeenCalled();
  });

  it("closes without a playback command and stops polling when unmounted", async () => {
    vi.useFakeTimers();
    const onClose = vi.fn();
    await act(async () => root.render(<NowPlaying onClose={onClose} />));
    await act(async () => container.querySelector<HTMLButtonElement>('[aria-label="Close music player"]')!.click());
    expect(onClose).toHaveBeenCalledOnce();
    expect(apiMusicControl).not.toHaveBeenCalled();
    const calls = vi.mocked(apiMusicStatus).mock.calls.length;
    const signal = vi.mocked(apiMusicStatus).mock.calls[0][0];
    await act(async () => root.render(null));
    expect(signal.aborted).toBe(true);
    await act(async () => vi.advanceTimersByTimeAsync(12000));
    expect(apiMusicStatus).toHaveBeenCalledTimes(calls);
  });
  it("confirms pause from the control response", async () => {
    vi.mocked(apiMusicControl).mockResolvedValue({ ...snapshot, playback_state: "paused" });
    await act(async () => root.render(<NowPlaying />));
    await act(async () => container.querySelector<HTMLButtonElement>('[aria-label="Pause music"]')!.click());
    expect(apiMusicControl).toHaveBeenCalledWith("pause", expect.any(AbortSignal));
    expect(container.querySelector('[aria-label="Resume music"]')).not.toBeNull();
  });
  it("shows unavailable state without inventing a track", async () => {
    vi.mocked(apiMusicStatus).mockRejectedValue(new Error("offline"));
    await act(async () => root.render(<NowPlaying />));
    expect(container.textContent).toContain("Music unavailable");
    expect(container.querySelector("img")).toBeNull();
    expect([...container.querySelectorAll("button")].every(button => button.disabled)).toBe(true);
  });
  it("reports a rejected control without pretending to pause", async () => {
    vi.mocked(apiMusicControl).mockRejectedValue(new Error("denied"));
    await act(async () => root.render(<NowPlaying />));
    await act(async () => container.querySelector<HTMLButtonElement>('[aria-label="Pause music"]')!.click());
    expect(container.textContent).toContain("Playback control failed");
    expect(container.querySelector('[aria-label="Pause music"]')).not.toBeNull();
  });

  it("does not start duplicate poll loops after a StrictMode remount", async () => {
    vi.useFakeTimers();
    let resolveOld!: (value: MusicSnapshot) => void;
    vi.mocked(apiMusicStatus).mockReturnValueOnce(new Promise(resolve => { resolveOld = resolve; }));
    await act(async () => root.render(<StrictMode><NowPlaying /></StrictMode>));
    expect(apiMusicStatus).toHaveBeenCalledTimes(2);
    await act(async () => resolveOld({ ...snapshot, playback_state: "paused" }));
    expect(container.querySelector('[aria-label="Pause music"]')).not.toBeNull();
    await act(async () => vi.advanceTimersByTimeAsync(4000));
    expect(apiMusicStatus).toHaveBeenCalledTimes(3);
  });

  it.each(["network", "native"])("retains the last track during a %s failure and recovers", async (failure) => {
    vi.useFakeTimers();
    await act(async () => root.render(<NowPlaying />));
    const artwork = container.querySelector("img");
    if (failure === "network") vi.mocked(apiMusicStatus).mockRejectedValueOnce(new Error("offline"));
    else vi.mocked(apiMusicStatus).mockResolvedValueOnce({ available: false, playback_state: "unknown", track: null });
    await act(async () => vi.advanceTimersByTimeAsync(4000));
    expect(container.textContent).toContain("A quiet morning");
    expect(container.textContent).toContain("Last known track");
    expect(container.querySelector("img")).toBe(artwork);
    expect([...container.querySelectorAll("button")].every(button => button.disabled)).toBe(true);
    await act(async () => vi.advanceTimersByTimeAsync(4000));
    expect(container.textContent).not.toContain("Reconnecting");
    expect(container.querySelector<HTMLButtonElement>('[aria-label="Pause music"]')?.disabled).toBe(false);
  });

  it("stops the disc when paused or disconnected", async () => {
    vi.useFakeTimers();
    await act(async () => root.render(<NowPlaying />));
    vi.mocked(apiMusicStatus).mockResolvedValueOnce({ ...snapshot, playback_state: "paused" });
    await act(async () => vi.advanceTimersByTimeAsync(4000));
    expect(container.querySelector(".nova-music-art")?.getAttribute("data-spinning")).toBe("false");
    await act(async () => vi.advanceTimersByTimeAsync(4000));
    expect(container.querySelector(".nova-music-art")?.getAttribute("data-spinning")).toBe("true");
    vi.mocked(apiMusicStatus).mockRejectedValueOnce(new Error("offline"));
    await act(async () => vi.advanceTimersByTimeAsync(4000));
    expect(container.querySelector(".nova-music-art")?.getAttribute("data-spinning")).toBe("false");
  });

  it("resumes Apple Music even when no current track is reported", async () => {
    vi.mocked(apiMusicStatus).mockResolvedValue({ available: true, playback_state: "stopped", track: null });
    vi.mocked(apiMusicControl).mockResolvedValue(snapshot);
    await act(async () => root.render(<NowPlaying />));
    await act(async () => container.querySelector<HTMLButtonElement>('[aria-label="Resume music"]')!.click());
    expect(apiMusicControl).toHaveBeenCalledWith("resume", expect.any(AbortSignal));
    expect(container.querySelector("img")?.alt).toBe("Still artwork");
  });

  it("clears a track when Music confirms stopped, rather than retaining stale artwork", async () => {
    vi.useFakeTimers();
    await act(async () => root.render(<NowPlaying />));
    vi.mocked(apiMusicStatus).mockResolvedValueOnce({ available: true, playback_state: "stopped", track: null });
    await act(async () => vi.advanceTimersByTimeAsync(4000));
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("Nothing playing");
    expect(container.textContent).not.toContain("Last known track");
  });
});