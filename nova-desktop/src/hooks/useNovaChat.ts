// ============================================================
// useNovaChat — sends messages, handles streaming response
// ============================================================
import { useCallback, useEffect, useRef } from "react";
import { useChatStore } from "@/stores/useChatStore";
import { useAvatarStore } from "@/stores/useAvatarStore";
import { useAppStore } from "@/stores/useAppStore";
import { useSettingsStore } from "@/stores/useSettingsStore";
import {
  apiChat,
  apiVoiceEnrollmentAnswer,
  apiVoiceEnrollmentStart,
  apiVoiceStop,
  apiVoiceText,
  apiVoiceSpeak,
} from "@/services/api";
import { toSubtitleText } from "@/utils/subtitle";
import { startKaraoke } from "@/utils/karaoke";

export function useNovaChat() {
  const { addMessage, updateMessage, setStreaming } = useChatStore();
  const setAvatarState = useAvatarStore((s) => s.setState);
  const setSpeechText = useAvatarStore((s) => s.setSpeechText);
  const setAppStatus = useAppStore((s) => s.setStatus);
  const voice = useSettingsStore((s) => s.voice);
  const settleTimerRef = useRef<number | null>(null);
  const karaokeRef = useRef<(() => void) | null>(null);
  const enrollmentSessionIdRef = useRef<string | null>(null);
  const turnRef = useRef(0);

  useEffect(() => {
    const interrupt = () => {
      turnRef.current += 1;
      clearSettleTimer();
      cancelKaraoke();
      setStreaming(false);
    };
    window.addEventListener("nova-speech-interrupted", interrupt);
    return () => {
      window.removeEventListener("nova-speech-interrupted", interrupt);
      interrupt();
    };
  }, []);

  const isVoiceEnrollmentTrigger = (text: string) => {
    const n = text.toLowerCase();
    return (
      n.includes("recognize voice") ||
      n.includes("enroll voice") ||
      n.includes("register voice") ||
      n.includes("train voice") ||
      n.includes("enroll me") ||
      n.includes("quick enroll")
    );
  };

  const isSimpleGreeting = (text: string) => {
    const n = text.trim().toLowerCase();
    return /^(hi|hey|hello|hola|yo|good\s*(morning|afternoon|evening)|howdy|sup|what'?s\s*up)\s*!?\??$/.test(n);
  };

  const extractEnrollmentName = (text: string): string | undefined => {
    const match = text.match(/(?:for|name is|this is)\s+([a-zA-Z][a-zA-Z\s]{1,40})$/i);
    return match?.[1]?.trim();
  };

  const clearSettleTimer = () => {
    if (settleTimerRef.current !== null) {
      window.clearTimeout(settleTimerRef.current);
      settleTimerRef.current = null;
    }
  };

  const cancelKaraoke = () => {
    if (karaokeRef.current !== null) {
      karaokeRef.current();
      karaokeRef.current = null;
    }
  };

  const stopSpeaking = useCallback(async () => {
    clearSettleTimer();
    cancelKaraoke();
    window.speechSynthesis?.cancel();
    try {
      await apiVoiceStop();
    } catch {
      // Non-fatal: UI still returns to idle even if stop endpoint fails.
    }
    setAvatarState("idle");
  }, [setAvatarState]);

  const sendMessage = useCallback(
    async (text: string, source: "chat" | "voice" = "chat") => {
      if (!text.trim()) return;

      // New prompt starts a new cycle; cancel any active karaoke, clear previous text.
      clearSettleTimer();
      cancelKaraoke();
      setSpeechText(null);

      addMessage({ role: "user", content: text, meta: { source } });
      setStreaming(true);
      setAvatarState("thinking");

      const loaderId = addMessage({
        role: "nova",
        content: "",
        streaming: true,
      });

      const turn = ++turnRef.current;
      try {
        let response = "";
        let meta: Record<string, string> = {};

        const applyMusicPlaybackStatus = (candidate: unknown) => {
          const payload = candidate as Record<string, unknown>;
          if (String(payload.action ?? "") !== "music_playback") return;
          if (payload.success === false) return;
          const playbackState = String(
            (payload.data as Record<string, unknown> | undefined)?.playback_state ??
            payload.playback_state ??
            ""
          ).toLowerCase();
          if (playbackState === "paused") {
            setAppStatus({ musicPlaying: false });
          } else if (playbackState === "playing") {
            setAppStatus({ musicPlaying: true });
          }
        };

        if (source === "voice") {
          const payload = await apiVoiceText({
            text: `Nova, ${text}`,
            speak: false,
            voice_mode: voice.mode,
            voice_style: voice.style,
            voice_rate: voice.rate,
            voice_pitch: voice.pitch,
            voice_name: voice.model,
            accent_profile: voice.accent,
          });
          response = payload.response ?? "";
          if (payload.intent) meta.intent = payload.intent;
          if (payload.action) meta.action = payload.action;
          applyMusicPlaybackStatus(payload);

          const details = {
            ...(Array.isArray(payload.steps) ? { steps: payload.steps } : {}),
            ...(payload.data ? payload.data : {}),
          };

          updateMessage(loaderId.id, {
            content: response,
            streaming: false,
            details: Object.keys(details).length > 0 ? details : undefined,
            meta,
          });

        } else {
          const isEnrollmentReply = enrollmentSessionIdRef.current !== null;
          const isEnrollmentStart = !isEnrollmentReply && isVoiceEnrollmentTrigger(text);
          const isGreeting = !isEnrollmentReply && !isEnrollmentStart && isSimpleGreeting(text);

          if (isGreeting) {
            response = "Hi! How can I help you today?";
            meta.intent = "greeting";
            updateMessage(loaderId.id, {
              content: response,
              streaming: false,
              meta,
            });
          } else

          if (isEnrollmentReply || isEnrollmentStart) {
            const payload = isEnrollmentReply
              ? await apiVoiceEnrollmentAnswer(text, enrollmentSessionIdRef.current ?? undefined)
              : await apiVoiceEnrollmentStart(extractEnrollmentName(text));

            response = payload.response ?? "";
            meta.action = payload.action ?? "voice_enrollment";

            const sid = payload.data?.session_id ?? null;
            if (sid) {
              enrollmentSessionIdRef.current = sid;
            }
            if (payload.data?.completed) {
              enrollmentSessionIdRef.current = null;
            }

            const details = {
              ...(payload.data ? payload.data : {}),
            };
            updateMessage(loaderId.id, {
              content: response,
              streaming: false,
              details: Object.keys(details).length > 0 ? details : undefined,
              meta,
            });
          } else {
            const payload = await apiChat({ message: text });
            response = payload.response ?? "";
            if (payload.intent) meta.intent = payload.intent;
            if (payload.action) meta.action = payload.action;
            applyMusicPlaybackStatus(payload);

            if (payload.initiative?.message) {
              addMessage({
                role: "nova",
                content: payload.initiative.message,
                meta: { source: "initiative" },
              });
            }

            const details = {
              ...(Array.isArray(payload.steps) ? { steps: payload.steps } : {}),
              ...(payload.data ? payload.data : {}),
            };

            updateMessage(loaderId.id, {
              content: response,
              streaming: false,
              details: Object.keys(details).length > 0 ? details : undefined,
              meta,
            });
          }

        }

        if (turn !== turnRef.current) return;
        setStreaming(false);
        const subtitleForTimer = toSubtitleText(response);
        if (voice.speakBack && subtitleForTimer) {
          setAvatarState("speaking");
          karaokeRef.current = startKaraoke(subtitleForTimer, voice.rate, setSpeechText);
          try {
            await apiVoiceSpeak(subtitleForTimer, voice);
          } finally {
            if (turn === turnRef.current) {
              cancelKaraoke();
              setSpeechText(null);
              setAvatarState("idle");
            }
          }
          return;
        }
        if (!voice.speakBack) {
          // No speak-back: show full text immediately.
          if (subtitleForTimer) setSpeechText(subtitleForTimer);
          setAvatarState("speaking");
        }

        // Settle avatar to idle after estimated TTS playback duration.
        const wordCount = subtitleForTimer.trim().split(/\s+/).filter(Boolean).length;
        const estimatedMs = Math.max(2500, Math.min((wordCount / 2.8) * 1000, 30000));
        settleTimerRef.current = window.setTimeout(() => {
          if (turn !== turnRef.current) return;
          cancelKaraoke();
          setAvatarState("idle");
          settleTimerRef.current = null;
        }, estimatedMs);
      } catch (err) {
        updateMessage(loaderId.id, {
          role: "error",
          content: err instanceof Error ? err.message : "Request failed",
          streaming: false,
        });
        if (turn === turnRef.current) setAvatarState("idle");
      } finally {
        if (turn === turnRef.current) setStreaming(false);
      }
    },
    [addMessage, updateMessage, setStreaming, setAvatarState, setSpeechText, setAppStatus, voice]
  );

  return { sendMessage, stopSpeaking };
}
