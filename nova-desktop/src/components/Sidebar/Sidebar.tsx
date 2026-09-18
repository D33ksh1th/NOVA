import { motion, AnimatePresence } from "framer-motion";
import { useEffect, useState } from "react";
import { clsx } from "clsx";
import {
  Cpu,
  MessageSquare,
  Brain,
  CheckSquare,
  Bot,
  Eye,
  Settings,
  Code2,
  ChevronLeft,
  ChevronRight,
  Activity,
} from "lucide-react";
import type { NavPage } from "@/types";
import { useAppStore } from "@/stores/useAppStore";
import { useAvatarStore } from "@/stores/useAvatarStore";

interface NavItem {
  id: NavPage;
  label: string;
  icon: React.ReactNode;
  badge?: number;
}

const NAV_ITEMS: NavItem[] = [
  { id: "companion", label: "Core",       icon: <Cpu size={18} /> },
  { id: "chat",      label: "Chat",       icon: <MessageSquare size={18} /> },
  { id: "skills",   label: "Agents",     icon: <Bot size={18} /> },
  { id: "vision",   label: "Vision",     icon: <Eye size={18} /> },
  { id: "memory",   label: "Memory",     icon: <Brain size={18} /> },
  { id: "tasks",    label: "Tasks",      icon: <CheckSquare size={18} /> },
];

const BOTTOM_NAV: NavItem[] = [
  { id: "settings",  label: "Settings",  icon: <Settings size={18} /> },
  { id: "developer", label: "System",    icon: <Activity size={18} /> },
];

export function Sidebar() {
  const { currentPage, setPage, sidebarCollapsed: preferredCollapsed, setSidebarCollapsed } =
    useAppStore();
  const [compact, setCompact] = useState(() => window.matchMedia("(max-width: 639px)").matches);
  useEffect(() => {
    const query = window.matchMedia("(max-width: 639px)");
    const update = () => setCompact(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  const sidebarCollapsed = compact || preferredCollapsed;
  const avatarState = useAvatarStore((s) => s.state);
  const streamConnected = useAvatarStore((s) => s.streamConnected);

  const stateColor: Record<string, string> = {
    idle:      "bg-nova-orange",
    listening: "bg-accent-green",
    thinking:  "bg-nova-amber",
    speaking:  "bg-nova-orange",
    sleeping:  "bg-text-muted",
  };

  return (
    <motion.aside
      initial={false}
      animate={{ width: sidebarCollapsed ? 64 : 208 }}
      transition={{ type: "spring", stiffness: 380, damping: 38 }}
      className="nova-sidebar relative shrink-0 flex flex-col h-full pt-8 bg-bg-secondary border-r border-border overflow-hidden select-none"
    >
      {/* Brand */}
      <div className="flex items-center gap-3 px-4 py-7 min-h-[92px]">
        <div className="relative flex-shrink-0">
          <div className="w-8 h-8 rounded-md border border-nova-orange/40 bg-nova-orange/10 flex items-center justify-center">
            <Cpu size={19} className="text-nova-orange" />
          </div>
          {/* status dot */}
          <span
            className={clsx(
              "absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-bg-secondary transition-colors duration-300",
              streamConnected ? stateColor[avatarState] || "bg-nova-orange" : "bg-text-muted"
            )}
          />
        </div>

        <AnimatePresence>
          {!sidebarCollapsed && (
            <motion.div
              initial={false}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -8 }}
              transition={{ duration: 0.15 }}
              className="overflow-hidden"
            >
              <p className="font-display font-medium text-text-primary text-xl leading-none">
                NOVA
              </p>
              <p className="text-text-muted text-[10px] mt-0.5 font-mono font-bold uppercase tracking-[0.25em]">
                PERSONAL WORKSPACE
              </p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Divider */}
      <div className="h-px bg-border mx-3 mb-2" />
      {!sidebarCollapsed && <p className="nova-panel-heading px-5 py-3">Workspace</p>}

      {/* Main nav */}
      <nav aria-label="Main navigation" className="flex-1 px-2 space-y-1 overflow-y-auto overflow-x-hidden">
        {NAV_ITEMS.map((item) => (
          <NavButton
            key={item.id}
            item={item}
            active={currentPage === item.id}
            collapsed={sidebarCollapsed}
            onClick={() => setPage(item.id)}
          />
        ))}
      </nav>

      {/* Bottom nav */}
      <div className="px-2 pb-3 space-y-0.5 border-t border-border pt-2">
        {!sidebarCollapsed && <div className="px-3 py-4 mb-2"><div className="flex items-center justify-between text-xs text-text-secondary"><span>Event stream</span><span className={streamConnected ? "text-nova-orange" : "text-nova-amber"}>{streamConnected ? "Connected" : "Offline"}</span></div><div className="mt-3 h-px bg-border"><div className={`h-px transition-[width] duration-700 ${streamConnected ? "w-full bg-nova-orange/60" : "w-0"}`} /></div></div>}
        {BOTTOM_NAV.map((item) => (
          <NavButton
            key={item.id}
            item={item}
            active={currentPage === item.id}
            collapsed={sidebarCollapsed}
            onClick={() => setPage(item.id)}
          />
        ))}

        {/* Collapse toggle */}
        <button
          onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
          disabled={compact}
          className={clsx(
            "w-full flex items-center gap-3 px-3 py-2.5 rounded-xl",
            "text-text-muted hover:text-text-primary hover:bg-bg-elevated",
            "transition-colors duration-150 cursor-pointer"
          )}
          title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <span className="flex-shrink-0">
            {sidebarCollapsed ? (
              <ChevronRight size={16} />
            ) : (
              <ChevronLeft size={16} />
            )}
          </span>
          <AnimatePresence>
            {!sidebarCollapsed && (
              <motion.span
                initial={false}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="text-[13px] font-medium whitespace-nowrap overflow-hidden"
              >
                Collapse
              </motion.span>
            )}
          </AnimatePresence>
        </button>
      </div>
    </motion.aside>
  );
}

interface NavButtonProps {
  item: NavItem;
  active: boolean;
  collapsed: boolean;
  onClick: () => void;
}

function NavButton({ item, active, collapsed, onClick }: NavButtonProps) {
  return (
    <motion.button
      onClick={onClick}
      aria-label={item.label}
      aria-current={active ? "page" : undefined}
      whileTap={{ scale: 0.97 }}
      className={clsx(
        "relative w-full flex items-center gap-3 px-3 h-11 rounded-md transition-colors duration-150 cursor-pointer",
        "text-[13px] font-medium",
        active
          ? "bg-nova-orange/10 text-nova-orange"
          : "text-text-secondary hover:text-text-primary hover:bg-bg-elevated"
      )}
      title={collapsed ? item.label : undefined}
    >
      {active && <motion.span layoutId="navigation-marker" className="absolute left-0 top-3 bottom-3 w-0.5 bg-nova-orange rounded-full" transition={{ type: "spring", stiffness: 400, damping: 32 }} />}
      <span className="flex-shrink-0">{item.icon}</span>

      <AnimatePresence>
        {!collapsed && (
          <motion.span
            initial={false}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="whitespace-nowrap overflow-hidden flex-1 text-left"
          >
            {item.label}
          </motion.span>
        )}
      </AnimatePresence>

      {item.badge && !collapsed ? (
        <span className="bg-nova-orange text-white text-[10px] font-bold rounded-full px-1.5 py-0.5 leading-none">
          {item.badge}
        </span>
      ) : null}
    </motion.button>
  );
}
