import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { NavPage, NovaStatus } from "@/types";

interface AppState {
  currentPage: NavPage;
  status: NovaStatus;
  sidebarCollapsed: boolean;
  rightPanelOpen: boolean;
  theme: "dark";
  voiceWakeActive: boolean;
  voiceWakeSignal: number;
  voiceListenSignal: number;
  activeSpeakerHint: string | null;

  // actions
  setPage: (page: NavPage) => void;
  setStatus: (partial: Partial<NovaStatus>) => void;
  setSidebarCollapsed: (val: boolean) => void;
  setRightPanelOpen: (val: boolean) => void;
  setVoiceWakeActive: (val: boolean) => void;
  setActiveSpeakerHint: (name: string | null) => void;
  requestVoiceWakeListening: () => void;
  requestVoiceListening: () => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      currentPage: "companion",
      sidebarCollapsed: false,
      rightPanelOpen: true,
      theme: "dark",
      voiceWakeActive: false,
      voiceWakeSignal: 0,
      voiceListenSignal: 0,
      activeSpeakerHint: null,
      status: {
        backendConnected: false,
        avatarStreamConnected: false,
        voiceEnabled: false,
        micPermission: "unknown",
      },

      setPage: (page) => set({ currentPage: page }),
      setStatus: (partial) =>
        set((s) => ({ status: { ...s.status, ...partial } })),
      setSidebarCollapsed: (val) => set({ sidebarCollapsed: val }),
      setRightPanelOpen: (val) => set({ rightPanelOpen: val }),
      setVoiceWakeActive: (val) => set({ voiceWakeActive: val }),
      setActiveSpeakerHint: (name) => set({ activeSpeakerHint: name }),
      requestVoiceWakeListening: () =>
        set((s) => ({ voiceWakeSignal: s.voiceWakeSignal + 1 })),
      requestVoiceListening: () =>
        set((s) => ({ voiceListenSignal: s.voiceListenSignal + 1 })),
    }),
    {
      name: "nova-app-store",
      partialize: (s) => ({
        currentPage: s.currentPage,
        sidebarCollapsed: s.sidebarCollapsed,
        rightPanelOpen: s.rightPanelOpen,
        activeSpeakerHint: s.activeSpeakerHint,
      }),
    }
  )
);
