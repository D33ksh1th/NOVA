import { useEffect, useRef, useState } from "react";
import { LoaderCircle, Music2, Pause, Play, X } from "lucide-react";
import { apiMusicControl, apiMusicStatus, type MusicOperation, type MusicSnapshot } from "@/services/music";
import { useAppStore } from "@/stores/useAppStore";
import "./NowPlaying.css";

export function NowPlaying({ onClose }: { onClose?: () => void } = {}) {
  const [snapshot, setSnapshot] = useState<MusicSnapshot | null>(null);
  const [error, setError] = useState("");
  const [stale, setStale] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failedArtwork, setFailedArtwork] = useState<string | null>(null);
  const generation = useRef(0);
  const active = useRef(true);
  const control = useRef<AbortController | null>(null);

  function applySnapshot(value: MusicSnapshot) {
    if (!value.available) {
      setStale(true);
      setError(value.response || "Apple Music status unavailable.");
      return;
    }
    setStale(false);
    setSnapshot(value);
    if (value.available && ["playing", "paused", "stopped"].includes(value.playback_state)) {
      useAppStore.getState().setStatus({ musicPlaying: value.playback_state === "playing" });
    }
  }

  useEffect(() => {
    active.current = true;
    let disposed = false;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      const current = generation.current;
      try {
        const value = await apiMusicStatus(controller.signal);
        if (!disposed && current === generation.current && !control.current) {
          applySnapshot(value);
          setError(value.available ? "" : value.response || "Apple Music unavailable.");
        }
      } catch (failure) {
        if (!disposed && current === generation.current && !control.current) {
          setStale(true);
          setError(failure instanceof Error ? failure.message : "Connection interrupted. Retrying Apple Music status.");
        }
      } finally {
        if (!disposed) timer = setTimeout(refresh, 4000);
      }
    }
    void refresh();
    return () => { disposed = true; active.current = false; generation.current += 1; clearTimeout(timer); controller.abort(); control.current?.abort(); };
  }, []);

  async function changePlayback(operation: MusicOperation) {
    if (control.current) return;
    const controller = new AbortController();
    control.current = controller;
    const current = ++generation.current;
    setBusy(true);
    try {
      const value = await apiMusicControl(operation, controller.signal);
      if (active.current && current === generation.current) {
        applySnapshot(value);
        setError(value.success ? "" : value.response || "Playback was not confirmed.");
      }
    } catch {
      if (active.current) setError("Playback control failed. Please try again.");
    } finally {
      control.current = null;
      if (active.current) setBusy(false);
    }
  }

  const track = snapshot?.available ? snapshot.track : null;
  const playing = snapshot?.playback_state === "playing";
  const artwork = track?.artwork_url;
  const disabled = busy || stale || !snapshot?.available;

  return <section aria-label="Apple Music player" aria-busy={busy} className="nova-music mx-5 sm:mx-8 mt-4 pt-3 border-t border-border">
    <div className="nova-music-layout">
      <div className="nova-music-art bg-bg-tertiary" data-spinning={Boolean(playing && !stale && track)}>
        {artwork && artwork !== failedArtwork && /^data:image\/(jpeg|png);base64,/.test(artwork)
          ? <img src={artwork} alt={`${track?.album || track?.title} artwork`} onError={() => setFailedArtwork(artwork)} className="h-full w-full object-cover" />
          : <Music2 size={22} className="text-accent-blue" aria-label="Album artwork unavailable" />}
      </div>
      <div className="nova-music-details min-w-0">
        <div className="nova-music-eyebrow text-text-muted"><span>Apple Music</span><span className={stale ? "text-nova-orange" : "text-accent-blue"}>{stale ? "Reconnecting" : track ? playing ? "Playing" : "Paused" : "Now Playing"}</span></div>
        <p className="nova-music-title font-display text-text-primary" title={track?.title}>{track?.title || (error ? "Music unavailable" : snapshot ? "Nothing playing" : "Connecting...")}</p>
        <p className="nova-music-artist text-text-secondary" title={track?.artist}>{track?.artist || (track ? "Unknown artist" : "Apple Music")}</p>
      </div>
      <div className="nova-music-controls">
        <button title={playing ? "Pause music" : "Resume music"} aria-label={playing ? "Pause music" : "Resume music"} disabled={disabled} onClick={() => void changePlayback(playing ? "pause" : "resume")} className="nova-music-button nova-music-primary bg-text-primary text-bg-primary disabled:opacity-30">{busy ? <LoaderCircle size={20} className="animate-spin" /> : playing ? <Pause size={20} fill="currentColor" /> : <Play size={20} fill="currentColor" />}</button>
        {onClose && <button type="button" title="Close music player" aria-label="Close music player" onClick={onClose} className="nova-music-close text-text-muted hover:text-text-primary"><X size={15} /></button>}
      </div>
    </div>
    <div className="nova-music-message text-text-muted" role="status">
      {stale && track && <span className="text-nova-orange">Last known track. </span>}{error}
    </div>
  </section>;
}