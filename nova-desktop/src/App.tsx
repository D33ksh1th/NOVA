import { motion, AnimatePresence } from "framer-motion";
import { Sidebar } from "@/components/Sidebar/Sidebar";
import { CompanionPage } from "@/pages/CompanionPage";
import { ChatPage } from "@/pages/ChatPage";
import { MailPage } from "@/pages/MailPage";
import { MemoryPage } from "@/pages/MemoryPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { useAppStore } from "@/stores/useAppStore";
import { useAvatarStream } from "@/hooks/useAvatarStream";
import { useVoiceWakeListener } from "@/hooks/useVoiceWakeListener";
import { useGmailNotifications } from "@/hooks/useGmailNotifications";
import { useEffect } from "react";
import { apiHealth } from "@/services/api";
import type { NavPage } from "@/types";

const PAGE_MAP: Record<NavPage, React.ReactNode> = {
  companion: <CompanionPage />,
  chat: <ChatPage />,
  mail: <MailPage />,
  memory: <MemoryPage />,
  tasks: <TasksPlaceholder />,
  skills: <SkillsPlaceholder />,
  vision: <VisionPlaceholder />,
  // Legacy route fallback: keep persisted "voice" page from older builds usable.
  voice: <SettingsPage />,
  settings: <SettingsPage />,
  developer: <DeveloperPlaceholder />,
};

function TasksPlaceholder() {
  return <PlaceholderPage icon="✅" title="Tasks" desc="Goal decomposition, task planner, and plan executor pipeline." />;
}
function SkillsPlaceholder() {
  return <PlaceholderPage icon="🤖" title="Agents" desc="Active agents, capability registry, and live execution graph." />;
}
function VisionPlaceholder() {
  return <PlaceholderPage icon="🔌" title="Connectors" desc="External integrations: LLMs, APIs, databases, automation bridges." />;
}
function DeveloperPlaceholder() {
  return <PlaceholderPage icon="📡" title="System Monitor" desc="Event bus inspector, latency graph, API logs, and debug console." />;
}

function PlaceholderPage({ icon, title, desc }: { icon: string; title: string; desc: string }) {
  return (
    <div className="flex items-center justify-center h-full p-8">
      <div className="text-center max-w-sm">
        <motion.div
          className="text-5xl mb-5"
          animate={{ y: [0, -6, 0] }}
          transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
        >{icon}</motion.div>
        <h2 className="font-display font-bold text-xl text-text-primary mb-2 tracking-wide">{title}</h2>
        <p className="text-text-muted text-sm leading-relaxed">{desc}</p>
        <motion.span
          className="inline-block mt-5 text-[11px] font-mono font-bold uppercase tracking-[0.2em] text-[#38bdf8] bg-[#38bdf810] border border-[#38bdf830] rounded-full px-4 py-1.5"
          animate={{ opacity: [0.6, 1, 0.6] }}
          transition={{ duration: 2, repeat: Infinity }}
        >
          COMING ONLINE
        </motion.span>
      </div>
    </div>
  );
}

export function App() {
  const currentPage = useAppStore((s) => s.currentPage);
  const setStatus = useAppStore((s) => s.setStatus);

  // Connect to avatar SSE stream
  useAvatarStream();
  // Keep wake-word listening alive globally instead of only on the Voice page.
  useVoiceWakeListener();
  // Gmail new-message notifications (Jarvis mode).
  useGmailNotifications();

  // Check backend health on mount
  useEffect(() => {
    apiHealth()
      .then(() => setStatus({ backendConnected: true }))
      .catch(() => setStatus({ backendConnected: false }));
  }, [setStatus]);

  return (
    <div className="flex h-full bg-bg overflow-hidden">
      {/* Titlebar (Tauri window) */}
      <div
        data-tauri-drag-region
        className="fixed top-0 left-0 right-0 h-8 z-50 flex items-center px-4"
        style={{ WebkitAppRegion: "drag" } as React.CSSProperties}
      />

      {/* Sidebar */}
      <Sidebar />

      {/* Main content area */}
      <main className="flex-1 overflow-hidden relative mt-8">
        <AnimatePresence mode="wait">
          <motion.div
            key={currentPage}
            initial={{ opacity: 0, x: 6 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -6 }}
            transition={{ duration: 0.16 }}
            className="h-full"
          >
            {PAGE_MAP[currentPage]}
          </motion.div>
        </AnimatePresence>
      </main>

    </div>
  );
}
