// ============================================================
// useAvatarStream — connects SSE → AvatarStore
// ============================================================
import { useEffect, useRef } from "react";
import { useAvatarStore } from "@/stores/useAvatarStore";
import { useAppStore } from "@/stores/useAppStore";
import { AvatarSSEClient } from "@/services/sseClient";
import type { AvatarState } from "@/types";
import { AvatarEngine } from "@/avatar/controller";
import { toSubtitleText } from "@/utils/subtitle";

const SSE_URL =
  (import.meta.env.VITE_NOVA_API_URL ?? "http://127.0.0.1:8000") +
  "/avatar/events";

export function useAvatarStream() {
  const setState = useAvatarStore((s) => s.setState);
  const setEmotion = useAvatarStore((s) => s.setEmotion);
  const setSpeechText = useAvatarStore((s) => s.setSpeechText);
  const setAnimationOverride = useAvatarStore((s) => s.setAnimationOverride);
  const setStreamConnected = useAvatarStore((s) => s.setStreamConnected);
  const setStatus = useAppStore((s) => s.setStatus);
  const clientRef = useRef<AvatarSSEClient | null>(null);
  const engineRef = useRef<AvatarEngine | null>(null);

  useEffect(() => {
    const engine = new AvatarEngine();
    engineRef.current = engine;
    engine.start();

    const offSnapshot = engine.onSnapshot((snapshot) => {
      setState(snapshot.state);
      setEmotion(snapshot.emotion);
      if (snapshot.speechText !== null && snapshot.speechText !== undefined) {
        setSpeechText(toSubtitleText(snapshot.speechText));
      } else {
        setSpeechText(null);
      }
      setAnimationOverride(snapshot.animationOverride);
    });

    const client = new AvatarSSEClient(
      SSE_URL,
      (state: AvatarState, eventName: string, payload?: Record<string, unknown>) => {
        const mergedPayload = { ...(payload ?? {}), state };
        engine.ingest(eventName, mergedPayload);
      },
      (connected: boolean) => {
        setStreamConnected(connected);
        setStatus({ avatarStreamConnected: connected });
      }
    );
    clientRef.current = client;
    client.connect();

    return () => {
      offSnapshot();
      client.destroy();
      engine.stop();
    };
  }, [setState, setEmotion, setSpeechText, setAnimationOverride, setStreamConnected, setStatus]);
}
