import { create } from "zustand";
import { persist } from "zustand/middleware";
import type {
  VoiceSettings,
  VoiceMode,
  VoiceStyle,
  AccentProfile,
} from "@/types";

interface SettingsStore {
  voice: VoiceSettings;
  avatarVisible: boolean;
  avatarScale: number;
  avatarTheme: "orange" | "grey" | "black";
  notifications: boolean;
  developerMode: boolean;
  voiceRecognitionEnabled: boolean;
  gmailEnabled: boolean;
  gmailSpeakAlerts: boolean;
  gmailNotifyLevel: "all" | "high" | "critical";

  setVoice: (partial: Partial<VoiceSettings>) => void;
  setAvatarVisible: (val: boolean) => void;
  setAvatarScale: (val: number) => void;
  setAvatarTheme: (theme: "orange" | "grey" | "black") => void;
  setDeveloperMode: (val: boolean) => void;
  setVoiceRecognitionEnabled: (val: boolean) => void;
  setGmailEnabled: (val: boolean) => void;
  setGmailSpeakAlerts: (val: boolean) => void;
  setGmailNotifyLevel: (level: "all" | "high" | "critical") => void;
}

export const useSettingsStore = create<SettingsStore>()(
  persist(
    (set) => ({
      voice: {
        enabled: true,
        speakBack: true,
        mode: "human" as VoiceMode,
        style: "calm" as VoiceStyle,
        accent: "english_jarvis" as AccentProfile,
        rate: 166,
        pitch: 44,
        model: "english_lessac",
        handsFreeWake: false,
        micEnabled: false,
      },
      avatarVisible: true,
      avatarScale: 1.0,
      avatarTheme: "orange",
      notifications: true,
      developerMode: false,
      voiceRecognitionEnabled: true,
      gmailEnabled: false,
      gmailSpeakAlerts: true,
      gmailNotifyLevel: "high" as const,

      setVoice: (partial) =>
        set((s) => ({ voice: { ...s.voice, ...partial } })),
      setAvatarVisible: (val) => set({ avatarVisible: val }),
      setAvatarScale: (val) => set({ avatarScale: val }),
      setAvatarTheme: (theme) => set({ avatarTheme: theme }),
      setDeveloperMode: (val) => set({ developerMode: val }),
      setVoiceRecognitionEnabled: (val) => set({ voiceRecognitionEnabled: val }),
      setGmailEnabled: (val) => set({ gmailEnabled: val }),
      setGmailSpeakAlerts: (val) => set({ gmailSpeakAlerts: val }),
      setGmailNotifyLevel: (level) => set({ gmailNotifyLevel: level }),
    }),
    {
      name: "nova-settings-store",
      version: 3,
      migrate: (persisted, _version) => {
        const state = (persisted ?? {}) as Partial<SettingsStore>;
        const voice = state.voice;
        if (!voice) return persisted as SettingsStore;

        // Force any Indian preset or old defaults to Jarvis English.
        const isIndian =
          ["indian_clear", "indian_natural", "indian_warm"].includes(voice.accent ?? "") ||
          ["indian_priyamvada", "indian_pratham", "indian_rohan"].includes(voice.model ?? "");

        if (isIndian) {
          return {
            ...(state as SettingsStore),
            voice: {
              ...voice,
              style: "calm" as VoiceStyle,
              accent: "english_jarvis" as AccentProfile,
              rate: 166,
              pitch: 44,
              model: "english_lessac",
            },
          };
        }

        return persisted as SettingsStore;
      },
    }
  )
);
