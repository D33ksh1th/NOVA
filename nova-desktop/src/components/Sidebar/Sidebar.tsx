import { motion, AnimatePresence } from "framer-motion";
import { clsx } from "clsx";
import {
  Cpu,
  MessageSquare,
  Mail,
  Brain,
  CheckSquare,
  Bot,
  Plug,
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
  { id: "mail",      label: "Mail",       icon: <Mail size={18} /> },
  { id: "skills",   label: "Agents",     icon: <Bot size={18} /> },
  { id: "vision",   label: "Connectors", icon: <Plug size={18} /> },
  { id: "memory",   label: "Memory",     icon: <Brain size={18} /> },
  { id: "tasks",    label: "Tasks",      icon: <CheckSquare size={18} /> },
];

const BOTTOM_NAV: NavItem[] = [
  { id: "settings",  label: "Settings",  icon: <Settings size={18} /> },
  { id: "developer", label: "System",    icon: <Activity size={18} /> },
];

export function Sidebar() {
  const { currentPage, setPage, sidebarCollapsed, setSidebarCollapsed } =
    useAppStore();
  const avatarState = useAvatarStore((s) => s.state);
  const streamConnected = useAvatarStore((s) => s.streamConnected);

  const stateColor: Record<string, string> = {
    idle:      "bg-[#38bdf8]",
    listening: "bg-accent-green",
    thinking:  "bg-[#a78bfa]",
    speaking:  "bg-nova-orange",
    sleeping:  "bg-text-muted",
  };

  return (
    <motion.aside
      initial={false}
      animate={{ width: sidebarCollapsed ? 64 : 220 }}
      transition={{ type: "spring", stiffness: 380, damping: 38 }}
      className="relative flex flex-col h-full bg-bg-secondary border-r border-border overflow-hidden select-none"
    >
      {/* Brand */}
      <div className="flex items-center gap-3 px-4 py-5 min-h-[72px]">
        <div className="relative flex-shrink-0">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-[#0ea5e9] to-[#6366f1] flex items-center justify-center shadow-glow">
            <Cpu size={18} className="text-white" />
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
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -8 }}
              transition={{ duration: 0.15 }}
              className="overflow-hidden"
            >
              <p className="font-display font-bold text-text-primary text-base leading-none tracking-wide">
                NOVA
              </p>
              <p className="text-text-muted text-[10px] mt-0.5 font-mono font-bold uppercase tracking-[0.25em]">
                AI SYSTEM
              </p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Divider */}
      <div className="h-px bg-border mx-3 mb-2" />

      {/* Main nav */}
      <nav className="flex-1 px-2 space-y-0.5 overflow-y-auto overflow-x-hidden">
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
                initial={{ opacity: 0 }}
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
      whileTap={{ scale: 0.97 }}
      className={clsx(
        "w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-150 cursor-pointer",
        "text-[13px] font-medium",
        active
          ? "bg-gradient-to-r from-nova-orange/20 to-nova-amber/10 text-nova-orange border border-nova-orange/20"
          : "text-text-secondary hover:text-text-primary hover:bg-bg-elevated"
      )}
      title={collapsed ? item.label : undefined}
    >
      <span className="flex-shrink-0">{item.icon}</span>

      <AnimatePresence>
        {!collapsed && (
          <motion.span
            initial={{ opacity: 0 }}
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
