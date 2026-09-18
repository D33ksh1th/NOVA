import { apiMusicStatus } from "./music";

describe("music request diagnostics", () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });
  it.each([
    [404, "Restart the NOVA backend"],
    [403, "Music access denied"],
    [503, "503"],
  ])("explains HTTP %s", async (status, message) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status }));
    await expect(apiMusicStatus(new AbortController().signal)).rejects.toThrow(String(message));
  });
  it("identifies an unreachable backend", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(apiMusicStatus(new AbortController().signal)).rejects.toThrow("backend is unreachable");
  });
  it("identifies timeouts and cleans up cancellation", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn((_url, options: RequestInit) => new Promise((_resolve, reject) => {
      options.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")), { once: true });
    })));
    const check = expect(apiMusicStatus(new AbortController().signal)).rejects.toThrow("timed out");
    await vi.advanceTimersByTimeAsync(20000);
    await check;
    expect(vi.getTimerCount()).toBe(0);
  });
});