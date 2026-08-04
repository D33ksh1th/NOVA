import { create } from "zustand";
import type { AvatarState } from "@/types";

interface AvatarStore {
  state: AvatarState;
  emotion: string;
  speechText: string | null;
  streamConnected: boolean;
  animationOverride: string | null;

  setState: (state: AvatarState) => void;
  setEmotion: (emotion: string) => void;
  setSpeechText: (text: string | null) => void;
  setStreamConnected: (val: boolean) => void;
  setAnimationOverride: (name: string | null) => void;
}

export const useAvatarStore = create<AvatarStore>()((set) => ({
  state: "idle",
  emotion: "neutral",
  speechText: null,
  streamConnected: false,
  animationOverride: null,

  setState: (state) => set({ state }),
  setEmotion: (emotion) => set({ emotion }),
  setSpeechText: (text) => set({ speechText: text }),
  setStreamConnected: (val) => set({ streamConnected: val }),
  setAnimationOverride: (name) => set({ animationOverride: name }),
}));
