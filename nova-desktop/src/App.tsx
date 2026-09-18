import { motion, MotionConfig, useReducedMotion } from "framer-motion";
import { Activity, ArrowUpRight, CheckSquare, Settings2, Command } from "lucide-react";
import { Sidebar } from "@/components/Sidebar/Sidebar";
import { CompanionPage } from "@/pages/CompanionPage";
import { ChatPage } from "@/pages/ChatPage";
import { AgentsPage } from "@/pages/AgentsPage";
import { MemoryPage } from "@/pages/MemoryPage";
import { VisionPage } from "@/pages/VisionPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { useAppStore } from "@/stores/useAppStore";
import { useAvatarStore } from "@/stores/useAvatarStore";
import { useAvatarStream } from "@/hooks/useAvatarStream";
import { useVoiceWakeListener } from "@/hooks/useVoiceWakeListener";
import { ResearchNotification } from "@/components/ResearchNotification";
import { useEffect } from "react";
import { apiHealth } from "@/services/api";
import type { NavPage } from "@/types";

const PAGE_MAP: Record<NavPage, React.ReactNode> = {
  companion: <CompanionPage />,
  chat: <ChatPage />,
  memory: <MemoryPage />,
  tasks: <TasksPlaceholder />,
  skills: <AgentsPage />,
  vision: <VisionPage />,
  // Legacy route fallback: keep persisted "voice" page from older builds usable.
  voice: <SettingsPage />,
  settings: <SettingsPage />,
  developer: <DeveloperPlaceholder />,
};

function TasksPlaceholder() {
  return <PlaceholderPage icon={<CheckSquare size={28} />} title="Task workspace" desc="No task feed is connected to this view." target="skills" action="Open agent activity" />;
}
function DeveloperPlaceholder() {
  return <PlaceholderPage icon={<Activity size={28} />} title="System monitor" desc="Detailed system telemetry is not connected to this view." target="companion" action="Open Core" />;
}

function PlaceholderPage({ icon, title, desc, target, action }: { icon: React.ReactNode; title: string; desc: string; target: NavPage; action: string }) {
  const setPage = useAppStore((state) => state.setPage);
  return (
    <div className="flex items-center justify-center h-full p-8">
      <div className="text-center max-w-sm">
        <div className="inline-flex text-nova-orange mb-5">{icon}</div>
        <h2 className="font-display font-medium text-2xl text-text-primary mb-2">{title}</h2>
        <p className="text-text-muted text-sm leading-relaxed">{desc}</p>
        <button onClick={() => setPage(target)} className="inline-flex items-center gap-2 mt-6 text-nova-orange text-sm">{action}<ArrowUpRight size={16} /></button>
      </div>
    </div>
  );
}

export function App() {
  const currentPage = useAppStore((s) => s.currentPage);
  const setStatus = useAppStore((s) => s.setStatus);
  const setPage = useAppStore((s) => s.setPage);
  const connected = useAvatarStore((s) => s.streamConnected);
  const avatarState = useAvatarStore((s) => s.state);
  const reducedMotion = useReducedMotion();
  const pageNames: Record<NavPage, string> = { companion: "Core", chat: "Conversation", skills: "Research", memory: "Memory", vision: "Vision", tasks: "Tasks", settings: "Settings", voice: "Voice", developer: "System" };

  // Connect to avatar SSE stream
  useAvatarStream();
  // Keep wake-word listening alive globally instead of only on the Voice page.
  useVoiceWakeListener();

  // Check backend health on mount
  useEffect(() => {
    apiHealth()
      .then(() => setStatus({ backendConnected: true }))
      .catch(() => setStatus({ backendConnected: false }));
  }, [setStatus]);

  return (
    <MotionConfig reducedMotion="user"><div className="nova-shell flex h-full overflow-hidden">
      {/* Titlebar (Tauri window) */}
      <div
        data-tauri-drag-region
        className="fixed top-0 left-0 right-0 h-8 z-50 flex items-center justify-center px-4 border-b border-border-subtle bg-bg-secondary text-[10px] text-text-muted font-mono"
        style={{ WebkitAppRegion: "drag" } as React.CSSProperties}
      >NOVA / DESKTOP</div>

      {/* Sidebar */}
      <Sidebar />

      {/* Main content area */}
      <main className="nova-workspace flex-1 min-w-0 overflow-hidden relative mt-8 flex flex-col">
        <div className="h-12 shrink-0 px-4 sm:px-6 border-b border-border flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3 text-xs"><Command size={14} className="text-text-muted" /><span className="hidden sm:inline text-text-muted">Workspace</span><span className="hidden sm:inline text-text-muted">/</span><span className="text-text-primary truncate">{pageNames[currentPage]}</span></div>
          <div className="flex items-center gap-3 sm:gap-5"><span className={`flex items-center gap-2 text-[11px] ${connected ? "text-nova-orange" : "text-nova-amber"}`}><span className="nova-activity-bars" data-active={connected && ["listening", "thinking", "speaking"].includes(avatarState)} aria-hidden="true">{[0,1,2,3].map(index => <span key={index} />)}</span>{connected ? avatarState : "Disconnected"}</span><button onClick={() => setPage("settings")} title="Workspace settings" aria-label="Workspace settings" className="h-8 w-8 grid place-items-center rounded-md text-text-muted hover:bg-bg-elevated hover:text-text-primary"><Settings2 size={16} /></button></div>
        </div>
          <ResearchNotification />
          <motion.div
            key={currentPage}
            initial={{ opacity: reducedMotion ? 1 : 0, y: reducedMotion ? 0 : 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.24, ease: [0.2, 0.8, 0.2, 1] }}
            className="nova-view flex-1 min-h-0"
          >
            {PAGE_MAP[currentPage]}
          </motion.div>
      </main>

    </div></MotionConfig>
  );
}
