/**
 * useVoiceWakeListener — Real-time voice wake word + conversation via WebSocket.
 *
 * Uses getUserMedia (works in Tauri/WKWebView) to capture audio, streams PCM16
 * to the backend WebSocket at /voice/stream. Backend handles VAD + STT + wake word.
 *
 * Flow:
 *   1. Opens WebSocket to backend /voice/stream
 *   2. Captures mic audio via getUserMedia + ScriptProcessor
 *   3. Streams PCM16 chunks at 16kHz to backend
 *   4. Backend detects wake word → sends "wake_detected" event
 *   5. Subsequent transcripts are sent as conversation turns
 *   6. 10s silence → auto session end
 *   7. "exit"/"stop listening" → manual session end
 *   8. Barge-in: if avatar speaking and user speaks, interrupt + listen
 */

import { useEffect, useRef, useState } from "react";
import { useAppStore } from "@/stores/useAppStore";
import { useChatStore } from "@/stores/useChatStore";
import { useAvatarStore } from "@/stores/useAvatarStore";
import { useSettingsStore } from "@/stores/useSettingsStore";
import { apiVoiceSpeak, apiVoiceStop, apiVoiceText } from "@/services/api";
import { toSubtitleText } from "@/utils/subtitle";
import { startKaraoke } from "@/utils/karaoke";

const WS_BASE = (
  import.meta.env.VITE_NOVA_API_URL ?? "http://127.0.0.1:8000"
).replace(/^http/, "ws");
const WS_URL = `${WS_BASE}/voice/stream`;

// Desired sample rate for backend STT
const TARGET_SAMPLE_RATE = 16000;

type TranscriptPayload = {
  text: string;
  audioBase64?: string;
  audioMimeType?: string;
};

/**
 * Downsample a Float32Array from sourceSampleRate to targetSampleRate.
 */
function downsample(
  buffer: Float32Array,
  sourceSampleRate: number,
  targetSampleRate: number
): Float32Array {
  if (sourceSampleRate === targetSampleRate) return buffer;
  const ratio = sourceSampleRate / targetSampleRate;
  const newLength = Math.round(buffer.length / ratio);
  const result = new Float32Array(newLength);
  for (let i = 0; i < newLength; i++) {
    const srcIndex = Math.round(i * ratio);
    result[i] = buffer[Math.min(srcIndex, buffer.length - 1)];
  }
  return result;
}

/**
 * Convert Float32Array to PCM16 ArrayBuffer.
 */
function floatToPCM16(input: Float32Array): ArrayBuffer {
  const buffer = new ArrayBuffer(input.length * 2);
  const view = new DataView(buffer);
  for (let i = 0; i < input.length; i++) {
    const sample = Math.max(-1, Math.min(1, input[i]));
    view.setInt16(
      i * 2,
      sample < 0 ? sample * 0x8000 : sample * 0x7fff,
      true
    );
  }
  return buffer;
}

export function useVoiceWakeListener() {
  const voice = useSettingsStore((s) => s.voice);
  const voiceListenSignal = useAppStore((s) => s.voiceListenSignal);
  const setVoiceWakeActive = useAppStore((s) => s.setVoiceWakeActive);
  const setStatus = useAppStore((s) => s.setStatus);
  const addMessage = useChatStore((s) => s.addMessage);
  const updateMessage = useChatStore((s) => s.updateMessage);
  const setAvatarState = useAvatarStore((s) => s.setState);
  const setSpeechText = useAvatarStore((s) => s.setSpeechText);

  const voiceRef = useRef(voice);
  voiceRef.current = voice;

  const wsRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const conversationActiveRef = useRef(false);
  const speakingRef = useRef(false);
  const processingTranscriptRef = useRef(false);
  const karaokeRef = useRef<(() => void) | null>(null);
  const handledListenSignalRef = useRef(0);
  const reconnectTimerRef = useRef<number | null>(null);
  const disposedRef = useRef(false);
  const subtitleTimerRef = useRef<number | null>(null);
  const wakeAckInProgressRef = useRef(false);
  const pendingWakeTranscriptRef = useRef<TranscriptPayload | null>(null);
  // Manual mic tap → direct capture (skip wake word)
  const manualCaptureRef = useRef(false);
  const startingPipelineRef = useRef(false);
  const turnRef = useRef(0);
  const queuedTranscriptsRef = useRef<TranscriptPayload[]>([]);
  const playbackRef = useRef(false);
  const playbackTextRef = useRef("");
  const requestRef = useRef(0);

  useEffect(() => {
    const onPlayback = (event: Event) => {
      const detail = (event as CustomEvent<{ active: boolean; text?: string }>).detail;
      playbackRef.current = detail.active;
      if (detail.active) playbackTextRef.current = detail.text ?? "";
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        if (detail.active && !conversationActiveRef.current) {
          conversationActiveRef.current = true;
          setVoiceWakeActive(false);
          wsRef.current.send(JSON.stringify({ type: "start_conversation" }));
        }
        wsRef.current.send(JSON.stringify({ type: detail.active ? "playback_started" : "playback_finished", text: detail.text }));
      }
    };
    window.addEventListener("nova-playback", onPlayback);
    return () => window.removeEventListener("nova-playback", onPlayback);
  }, []);

  const cancelKaraoke = () => {
    if (karaokeRef.current) {
      karaokeRef.current();
      karaokeRef.current = null;
    }
  };

  const clearSubtitleTimer = () => {
    if (subtitleTimerRef.current !== null) {
      window.clearTimeout(subtitleTimerRef.current);
      subtitleTimerRef.current = null;
    }
  };

  const showSpeechTextSmooth = (text: string | null, delayMs = 220) => {
    clearSubtitleTimer();
    if (!text) {
      setSpeechText(null);
      return;
    }
    subtitleTimerRef.current = window.setTimeout(() => {
      subtitleTimerRef.current = null;
      if (disposedRef.current || !speakingRef.current) return;
      setSpeechText(text);
    }, delayMs);
  };

  async function speakWakeAck(text: string) {
    const ack = text.trim();
    if (!ack) return;
    const turn = ++turnRef.current;

    wakeAckInProgressRef.current = true;
    pendingWakeTranscriptRef.current = null;

    addMessage({ role: "nova", content: ack, meta: { source: "voice" } });

    const cv = voiceRef.current;
    if (!cv.speakBack) {
      wakeAckInProgressRef.current = false;
      if (conversationActiveRef.current) setAvatarState("listening");
      return;
    }

    speakingRef.current = true;
    setAvatarState("speaking");
    showSpeechTextSmooth(toSubtitleText(ack));

    try {
      await apiVoiceSpeak(ack, cv);
    } catch {
      // Ignore wake-ack TTS failures and continue listening.
    } finally {
      if (turn === turnRef.current) wakeAckInProgressRef.current = false;
    }

    if (disposedRef.current || turn !== turnRef.current) return;

    speakingRef.current = false;
    showSpeechTextSmooth(null, 0);

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "resume" }));
    }

    if (conversationActiveRef.current) {
      setAvatarState("listening");
    } else {
      setAvatarState("idle");
    }

    const queued = pendingWakeTranscriptRef.current as TranscriptPayload | null;
    pendingWakeTranscriptRef.current = null;
    if (queued && queued.text.trim().length >= 3) {
      void handleTranscript(queued.text, queued.audioBase64, queued.audioMimeType);
    }
  }

  // Check mic permission on mount (non-invasive query)
  useEffect(() => {
    if (navigator.permissions?.query) {
      navigator.permissions.query({ name: "microphone" as PermissionName }).then((result) => {
        console.log("[voice-stream] mic permission state:", result.state);
        setStatus({ micPermission: result.state as "granted" | "denied" | "unknown" });
        result.onchange = () => {
          console.log("[voice-stream] mic permission changed:", result.state);
          setStatus({ micPermission: result.state as "granted" | "denied" | "unknown" });
        };
      }).catch(() => {
        // permissions.query not supported for microphone in this browser
        console.log("[voice-stream] permissions.query not available for mic");
      });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Wait for zustand persist to finish rehydrating before starting the pipeline
  const [hydrated, setHydrated] = useState(
    useSettingsStore.persist.hasHydrated()
  );
  useEffect(() => {
    if (hydrated) return;
    const unsub = useSettingsStore.persist.onFinishHydration(() => {
      console.log("[voice-stream] settings store rehydrated");
      setHydrated(true);
    });
    return unsub;
  }, [hydrated]);

  // Stable references to avoid unnecessary effect re-runs
  const enabled = voice.enabled;
  const handsFreeWake = voice.handsFreeWake;

  // ─── Main effect ──────────────────────────────────────────────────
  useEffect(() => {
    disposedRef.current = false;

    // Don't start until zustand has loaded persisted state
    if (!hydrated) {
      console.log("[voice-stream] waiting for store hydration...");
      return;
    }

    const manualListenRequested =
      voiceListenSignal !== handledListenSignalRef.current;

    console.log("[voice-stream] effect fired", {
      enabled,
      handsFreeWake,
      manualListenRequested,
      voiceListenSignal,
    });

    if (!enabled) {
      console.log("[voice-stream] disabled — cleaning up");
      cleanupAll();
      return;
    }

    if (!manualListenRequested && !handsFreeWake) {
      console.log("[voice-stream] no wake + no manual — cleaning up");
      cleanupAll();
      return;
    }

    if (manualListenRequested) {
      handledListenSignalRef.current = voiceListenSignal;
      manualCaptureRef.current = true;
      // If NOVA is speaking, interrupt
      if (speakingRef.current) {
        speakingRef.current = false;
        cancelKaraoke();
        setSpeechText(null);
        apiVoiceStop().catch(() => {});
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: "interrupt" }));
        }
      }
      conversationActiveRef.current = true;
      // Manual request always tries pipeline (user gesture already handled mic)
      startPipeline();
    } else {
      // Auto-start (handsFreeWake) — check permission first to avoid locking denial
      if (navigator.permissions?.query) {
        navigator.permissions.query({ name: "microphone" as PermissionName }).then((result) => {
          if (disposedRef.current) return;
          if (result.state === "denied") {
            console.log("[voice-stream] mic permanently denied, skipping auto-start");
            setStatus({ micPermission: "denied" });
            return;
          }
          startPipeline();
        }).catch(() => {
          // permissions.query not available — try anyway
          if (!disposedRef.current) startPipeline();
        });
      } else {
        startPipeline();
      }
    }

    return () => {
      disposedRef.current = true;
      cleanupAll();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hydrated, enabled, handsFreeWake, voiceListenSignal]);

  // ─── Cleanup ──────────────────────────────────────────────────────
  function cleanupAll() {
    turnRef.current += 1;
    requestRef.current += 1;
    queuedTranscriptsRef.current = [];
    processingTranscriptRef.current = false;
    startingPipelineRef.current = false;
    if (reconnectTimerRef.current !== null) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }
    if (audioCtxRef.current) {
      audioCtxRef.current.close().catch(() => {});
      audioCtxRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.onmessage = null;
      wsRef.current.close();
      wsRef.current = null;
    }
    conversationActiveRef.current = false;
    speakingRef.current = false;
    cancelKaraoke();
    showSpeechTextSmooth(null, 0);
    clearSubtitleTimer();
    setVoiceWakeActive(false);
    setAvatarState("idle");
  }

  // ─── Start audio + WebSocket pipeline ─────────────────────────────
  async function startPipeline() {
    // Already running or connecting
    if (wsRef.current && (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING)) {
      console.log("[voice-stream] pipeline already running/connecting");
      if (manualCaptureRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        // Already connected — just tell backend to start conversation
        manualCaptureRef.current = false;
        conversationActiveRef.current = true;
        wsRef.current.send(JSON.stringify({ type: "start_conversation" }));
        setAvatarState("listening");
        setVoiceWakeActive(false);
      }
      return;
    }

    console.log("[voice-stream] starting pipeline...");

    // Prevent concurrent startPipeline calls (StrictMode / async races)
    if (startingPipelineRef.current) {
      console.log("[voice-stream] pipeline start already in progress");
      return;
    }
    startingPipelineRef.current = true;

    // Check if mediaDevices API is available
    if (!navigator.mediaDevices?.getUserMedia) {
      console.error("[voice-stream] navigator.mediaDevices.getUserMedia not available!");
      console.error("[voice-stream] This usually means: not HTTPS, or blocked by browser policy");
      setStatus({ micPermission: "denied" });
      setVoiceWakeActive(false);
      setAvatarState("idle");
      return;
    }

    try {
      // 1. Get microphone access
      console.log("[voice-stream] requesting mic permission...");
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          noiseSuppression: true,
          echoCancellation: true,
          autoGainControl: true,
        },
      });

      if (disposedRef.current) {
        console.log("[voice-stream] disposed after getUserMedia");
        stream.getTracks().forEach((t) => t.stop());
        return;
      }
      streamRef.current = stream;
      setStatus({ micPermission: "granted" });
      console.log("[voice-stream] mic access granted, tracks:", stream.getAudioTracks().length);

      // 2. Audio processing
      const AudioCtxCtor =
        window.AudioContext ||
        (window as Window & { webkitAudioContext?: typeof AudioContext })
          .webkitAudioContext;
      if (!AudioCtxCtor) {
        console.error("[voice-stream] AudioContext not available");
        return;
      }

      const audioCtx = new AudioCtxCtor();
      audioCtxRef.current = audioCtx;
      const source = audioCtx.createMediaStreamSource(stream);
      sourceRef.current = source;
      const processor = audioCtx.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;

      // 3. WebSocket connection
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.binaryType = "arraybuffer";

      ws.onopen = () => {
        startingPipelineRef.current = false;
        if (disposedRef.current) return;
        console.log("[voice-stream] connected");
        ws.send(JSON.stringify({ type: "config", sample_rate: TARGET_SAMPLE_RATE, duplex: true }));

        if (manualCaptureRef.current || playbackRef.current) {
          conversationActiveRef.current = true;
          // Tell backend to skip wake word — direct conversation mode
          ws.send(JSON.stringify({ type: "start_conversation" }));
          setAvatarState("listening");
          setVoiceWakeActive(false);
          manualCaptureRef.current = false;
        } else {
          setVoiceWakeActive(true);
          setAvatarState("idle");
        }

        if (playbackRef.current) {
          ws.send(JSON.stringify({ type: "playback_started", text: playbackTextRef.current }));
        }

        // Wire up audio → WebSocket
        source.connect(processor);
        processor.connect(audioCtx.destination);
      };

      // Stream audio chunks to backend
      processor.onaudioprocess = (event) => {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;

        const inputData = event.inputBuffer.getChannelData(0);
        const resampled = downsample(
          inputData,
          audioCtx.sampleRate,
          TARGET_SAMPLE_RATE
        );
        const pcm16 = floatToPCM16(resampled);
        ws.send(pcm16);
      };

      // Handle backend events
      ws.onmessage = (event) => {
        if (disposedRef.current) return;
        try {
          const data = JSON.parse(
            typeof event.data === "string" ? event.data : ""
          );
          handleBackendEvent(data);
        } catch {
          // Non-JSON
        }
      };

      ws.onclose = () => {
        if (disposedRef.current) return;
        console.log("[voice-stream] disconnected");
        wsRef.current = null;
        // Auto-reconnect if still enabled
        const v = voiceRef.current;
        if (v.enabled && (v.handsFreeWake || conversationActiveRef.current)) {
          reconnectTimerRef.current = window.setTimeout(() => {
            if (!disposedRef.current) startPipeline();
          }, 2000);
        }
      };

      ws.onerror = () => {
        startingPipelineRef.current = false;
        ws.close();
      };
    } catch (err) {
      startingPipelineRef.current = false;
      console.error("[voice-stream] pipeline start failed:", err);
      // If getUserMedia was denied, update the app store
      if (err instanceof DOMException && err.name === "NotAllowedError") {
        console.error("[voice-stream] Microphone permission DENIED. Check browser/system settings.");
        setStatus({ micPermission: "denied" });
      } else if (err instanceof DOMException && err.name === "NotFoundError") {
        console.error("[voice-stream] No microphone found.");
        setStatus({ micPermission: "denied" });
      } else {
        setStatus({ micPermission: "unknown" });
      }
      setVoiceWakeActive(false);
      setAvatarState("idle");
    }
  }

  // ─── Handle events from backend ───────────────────────────────────
  function handleBackendEvent(data: {
    type: string;
    text?: string;
    is_wake?: boolean;
    audio_base64?: string;
    audio_mime_type?: string;
    reason?: string;
    message?: string;
  }) {
    switch (data.type) {
      case "barge_in":
        turnRef.current += 1;
        speakingRef.current = false;
        playbackRef.current = false;
        wakeAckInProgressRef.current = false;
        cancelKaraoke();
        showSpeechTextSmooth(null, 0);
        window.dispatchEvent(new Event("nova-speech-interrupted"));
        conversationActiveRef.current = true;
        setAvatarState("listening");
        break;
      case "listening":
        if (speakingRef.current || playbackRef.current) break;
        if (processingTranscriptRef.current || wakeAckInProgressRef.current) {
          break;
        }
        if (conversationActiveRef.current) {
          setAvatarState("listening");
        } else {
          setVoiceWakeActive(true);
          setAvatarState("idle");
        }
        break;

      case "wake_detected":
        conversationActiveRef.current = true;
        setVoiceWakeActive(false);
        if (data.text) {
          void speakWakeAck(data.text);
        } else {
          setAvatarState("listening");
        }
        break;

      case "processing":
        if (conversationActiveRef.current && !speakingRef.current && !processingTranscriptRef.current && !wakeAckInProgressRef.current) {
          setAvatarState("thinking");
        }
        break;

      case "transcript":
        if (data.text) {
          // During wake ack, queue wake-transcript follow-ups and process after ack completes.
          if (wakeAckInProgressRef.current) {
            const candidate = data.text.trim();
            if (candidate.length >= 3) {
              pendingWakeTranscriptRef.current = {
                text: candidate,
                audioBase64: data.audio_base64,
                audioMimeType: data.audio_mime_type,
              };
            }
            break;
          }
          void handleTranscript(data.text, data.audio_base64, data.audio_mime_type);
        }
        break;

      case "session_end":
        turnRef.current += 1;
        requestRef.current += 1;
        queuedTranscriptsRef.current = [];
        conversationActiveRef.current = false;
        speakingRef.current = false;
        processingTranscriptRef.current = false;
        cancelKaraoke();
        showSpeechTextSmooth(null, 0);
        setVoiceWakeActive(voiceRef.current.handsFreeWake);
        setAvatarState("idle");

        if (data.reason === "exit_command" && data.text) {
          addMessage({
            role: "user",
            content: data.text,
            meta: { source: "voice" },
          });
          addMessage({
            role: "nova",
            content:
              'Voice session ended. Say "Hey Nova" or tap the microphone to return.',
            meta: { source: "voice" },
          });
        }
        break;

      case "error":
        console.error("[voice-stream] backend:", data.message);
        break;
    }
  }

  // ─── Process a transcript ─────────────────────────────────────────
  async function handleTranscript(
    text: string,
    audioBase64?: string,
    audioMimeType?: string
  ) {
    if (!text.trim()) return;

    if (processingTranscriptRef.current) {
      queuedTranscriptsRef.current.push({ text, audioBase64, audioMimeType });
      return;
    }
    const turn = ++turnRef.current;
    const requestId = ++requestRef.current;
    processingTranscriptRef.current = true;

    conversationActiveRef.current = true;

    const needsStop = speakingRef.current || playbackRef.current || useAvatarStore.getState().state === "speaking";
    speakingRef.current = false;
    cancelKaraoke();
    showSpeechTextSmooth(null, 0);
    setAvatarState("thinking");

    addMessage({ role: "user", content: text, meta: { source: "voice" } });
    const loaderId = addMessage({
      role: "nova",
      content: "",
      streaming: true,
    });

    const cv = voiceRef.current;

    try {
      if (needsStop) {
        await apiVoiceStop();
        playbackRef.current = false;
      }
      if (disposedRef.current || requestId !== requestRef.current) return;
      const payload = await apiVoiceText({
        text,
        speak: false,
        audio_base64: audioBase64,
        audio_mime_type: audioMimeType,
        voice_mode: cv.mode,
        voice_style: cv.style,
        voice_rate: cv.rate,
        voice_pitch: cv.pitch,
        voice_name: cv.model,
        accent_profile: cv.accent,
      });

      const response = payload.response ?? "";
      const isMusicPlaybackAction = payload.action === "music_playback";
      const playbackState = String(payload.data?.playback_state ?? payload.playback_state ?? "").toLowerCase();
      const musicStarted = isMusicPlaybackAction && payload.success !== false && playbackState === "playing";
      const musicPaused = isMusicPlaybackAction && payload.success !== false && playbackState === "paused";
      updateMessage(loaderId.id, {
        content: response,
        streaming: false,
        details: payload.data,
        meta: {
          intent: payload.intent,
          action: payload.action,
          source: "voice",
        },
      });

      if (disposedRef.current || requestId !== requestRef.current) return;
      processingTranscriptRef.current = false;
      const queued = queuedTranscriptsRef.current.shift();
      if (queued) {
        void handleTranscript(queued.text, queued.audioBase64, queued.audioMimeType);
        return;
      }
      if (turn !== turnRef.current) return;

      // Prevent feedback loop with external audio: once music starts, end this voice session.
      if (isMusicPlaybackAction && payload.success !== false) {
        conversationActiveRef.current = false;
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: "exit" }));
        }
        if (musicStarted) {
          setStatus({ musicPlaying: true });
        } else if (musicPaused) {
          setStatus({ musicPlaying: false });
        }
        setVoiceWakeActive(voiceRef.current.handsFreeWake);
      }

      const subtitle = toSubtitleText(response);
      if (cv.speakBack && subtitle) {
        speakingRef.current = true;
        setAvatarState("speaking");
        showSpeechTextSmooth(subtitle);

        cancelKaraoke();
        karaokeRef.current = startKaraoke(subtitle, cv.rate, (next) => {
          if (!speakingRef.current) return;
          setSpeechText(next);
        });

        // Await actual TTS completion instead of guessing duration
        try {
          await apiVoiceSpeak(subtitle, cv);
        } catch {
          // TTS failed, continue anyway
        }

        if (disposedRef.current || turn !== turnRef.current || !speakingRef.current) return;
        speakingRef.current = false;
        cancelKaraoke();
        showSpeechTextSmooth(null, 0);

        if (conversationActiveRef.current) {
          setAvatarState("listening");
        } else {
          setAvatarState("idle");
        }
        processingTranscriptRef.current = false;
      } else if (subtitle) {
        setSpeechText(subtitle);
        window.setTimeout(() => {
          if (disposedRef.current || turn !== turnRef.current) return;
          speakingRef.current = false;
          showSpeechTextSmooth(null, 0);
          if (conversationActiveRef.current) {
            setAvatarState("listening");
          }
          processingTranscriptRef.current = false;
        }, 3000);
      } else {
        speakingRef.current = false;
        if (conversationActiveRef.current) {
          setAvatarState("listening");
        }
        processingTranscriptRef.current = false;
      }
    } catch (error) {
      if (disposedRef.current || requestId !== requestRef.current) return;
      speakingRef.current = false;
      processingTranscriptRef.current = false;
      updateMessage(loaderId.id, {
        role: "error",
        content:
          error instanceof Error ? error.message : "Voice request failed",
        streaming: false,
      });
      if (!disposedRef.current) setAvatarState("idle");
      const queued = queuedTranscriptsRef.current.shift();
      if (queued) {
        void handleTranscript(queued.text, queued.audioBase64, queued.audioMimeType);
        return;
      }
      if (conversationActiveRef.current) {
        window.setTimeout(() => {
          if (!disposedRef.current && turn === turnRef.current && conversationActiveRef.current) {
            setAvatarState("listening");
          }
        }, 500);
      }
    }
  }
}
