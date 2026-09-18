export interface MusicSnapshot {
  available: boolean;
  success?: boolean;
  playback_state: string;
  response?: string;
  position?: number;
  track: {
    id: string;
    title: string;
    artist: string;
    album: string;
    duration: number;
    artwork_url?: string | null;
  } | null;
}

export type MusicOperation = "pause" | "resume" | "next" | "previous";
const BASE = import.meta.env.VITE_NOVA_API_URL ?? "http://127.0.0.1:8000";

async function musicRequest(path: string, options: RequestInit): Promise<MusicSnapshot> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (options.signal?.aborted) abort();
  options.signal?.addEventListener("abort", abort, { once: true });
  const timer = setTimeout(abort, 20000);
  try {
    const response = await fetch(`${BASE}/api/music/${path}`, { cache: "no-store", ...options, signal: controller.signal });
    if (response.status === 404) throw new Error("Restart the NOVA backend to load the music connection.");
    if (response.status === 403) throw new Error("Music access denied. Open Core from localhost:1420 on this Mac.");
    if (!response.ok) throw new Error(`Music status request failed (${response.status}). Retrying shortly.`);
    return await response.json() as MusicSnapshot;
  } catch (error) {
    if (controller.signal.aborted && !options.signal?.aborted) {
      throw new Error("Music status timed out. The backend may be busy; retrying shortly.");
    }
    if (error instanceof TypeError) throw new Error("NOVA backend is unreachable. Reconnecting to music.");
    throw error;
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener("abort", abort);
  }
}

export const apiMusicStatus = (signal: AbortSignal) => musicRequest("status", { signal });
export const apiMusicControl = (operation: MusicOperation, signal: AbortSignal) => musicRequest("control", {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ operation }), signal,
});