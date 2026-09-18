import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { NavPage, NovaStatus } from "@/types";

interface AppState {
  currentPage: NavPage;
  status: NovaStatus;
  sidebarCollapsed: boolean;
  rightPanelOpen: boolean;
  musicPlayerOpen: boolean;
  theme: "dark";
  voiceWakeActive: boolean;
  voiceWakeSignal: number;
  voiceListenSignal: number;
  activeSpeakerHint: string | null;
  activeReportId: string | null;
  openReport: (identity: string) => void;

  // actions
  setPage: (page: NavPage) => void;
  setStatus: (partial: Partial<NovaStatus>) => void;
  setSidebarCollapsed: (val: boolean) => void;
  setRightPanelOpen: (val: boolean) => void;
  setMusicPlayerOpen: (val: boolean) => void;
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
      musicPlayerOpen: true,
      theme: "dark",
      voiceWakeActive: false,
      voiceWakeSignal: 0,
      voiceListenSignal: 0,
      activeSpeakerHint: null,
      activeReportId: null,
      openReport: (identity) => set({ activeReportId: identity, currentPage: "skills" }),
      status: {
        backendConnected: false,
        avatarStreamConnected: false,
        voiceEnabled: false,
        musicPlaying: false,
        micPermission: "unknown",
      },

      setPage: (page) => set({ currentPage: page }),
      setStatus: (partial) =>
        set((s) => ({ status: { ...s.status, ...partial } })),
      setSidebarCollapsed: (val) => set({ sidebarCollapsed: val }),
      setRightPanelOpen: (val) => set({ rightPanelOpen: val }),
      setMusicPlayerOpen: (val) => set({ musicPlayerOpen: val }),
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
        activeReportId: s.activeReportId,
        sidebarCollapsed: s.sidebarCollapsed,
        rightPanelOpen: s.rightPanelOpen,
        musicPlayerOpen: s.musicPlayerOpen,
        activeSpeakerHint: s.activeSpeakerHint,
      }),
    }
  )
);
