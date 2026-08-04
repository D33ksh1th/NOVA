import { motion, AnimatePresence } from "framer-motion";
import { useRef, useEffect, useMemo, useState } from "react";
import { NOVACore } from "@/components/Avatar/NOVACore";
import { ChatPanel } from "@/components/Chat/ChatPanel";
import { useAvatarStore } from "@/stores/useAvatarStore";
import { useAppStore } from "@/stores/useAppStore";
import { useChatStore } from "@/stores/useChatStore";
import {
  CheckSquare,
  Wifi,
  WifiOff,
  PanelRight,
  PanelRightClose,
  Activity,
  Bot,
  CircleDot,
  Zap,
  Radio,
  MessageSquareText,
  X,
  Bluetooth,
  Cable,
  Headphones,
  Ear,
  Usb,
  HardDrive,
  Smartphone,
  Battery,
  BatteryCharging,
} from "lucide-react";
import type { AvatarState, ConnectedBluetoothDevice, ConnectedExternalDevice } from "@/types";
import { apiConnectedDevices } from "@/services/api";

// ─── Tasks ──────────────────────────────────────────────────────
const MOCK_TASKS = [
  { id: "1", title: "Implement Auth Module", status: "in_progress" as const },
  { id: "2", title: "Database Optimization", status: "pending" as const },
  { id: "3", title: "UI Redesign",           status: "review" as const },
  { id: "4", title: "AI Model Research",     status: "pending" as const },
];

// ─── Agent definitions — loads driven by engine state ───────────
interface AgentDef {
  id: string;
  label: string;
  role: string;
}
const AGENT_DEFS: AgentDef[] = [
  { id: "brain",   label: "Brain Engine",    role: "Orchestration" },
  { id: "chat",    label: "Chat Agent",      role: "NLU / Response" },
  { id: "memory",  label: "Memory Agent",    role: "Context Store" },
  { id: "planner", label: "Task Planner",    role: "Goal Decomp" },
  { id: "voice",   label: "Voice Pipeline",  role: "TTS / STT" },
  { id: "vision",  label: "Vision Agent",    role: "Screen / Cam" },
];

// Load profiles per avatar state — computed from what each agent
// actually does during that phase of the conversation cycle.
const AGENT_LOAD_MAP: Record<string, Partial<Record<AvatarState, number>>> = {
  brain:   { idle: 4,  listening: 28, thinking: 92, speaking: 44, sleeping: 1,  focused: 55, excited: 78 },
  chat:    { idle: 2,  listening: 62, thinking: 18, speaking: 72, sleeping: 0,  focused: 30, excited: 65 },
  memory:  { idle: 8,  listening: 14, thinking: 71, speaking: 22, sleeping: 3,  focused: 48, excited: 20 },
  planner: { idle: 1,  listening: 5,  thinking: 48, speaking: 6,  sleeping: 0,  focused: 80, excited: 40 },
  voice:   { idle: 0,  listening: 88, thinking: 4,  speaking: 95, sleeping: 0,  focused: 5,  excited: 60 },
  vision:  { idle: 0,  listening: 0,  thinking: 0,  speaking: 0,  sleeping: 0,  focused: 22, excited: 0  },
};

function agentLoad(id: string, state: AvatarState): number {
  return AGENT_LOAD_MAP[id]?.[state] ?? 0;
}

function agentStatus(load: number): "active" | "standby" | "idle" {
  if (load >= 15) return "active";
  if (load >= 1)  return "standby";
  return "idle";
}

const AGENT_STATUS_COLOR: Record<string, string> = {
  active:  "text-accent-green",
  standby: "text-nova-amber",
  idle:    "text-text-muted",
};

const STATUS_COLOR: Record<string, string> = {
  in_progress: "text-nova-orange",
  pending:     "text-text-muted",
  review:      "text-accent-blue",
  done:        "text-accent-green",
};
const STATUS_LABEL: Record<string, string> = {
  in_progress: "In Progress",
  pending:     "Pending",
  review:      "Review",
  done:        "Done",
};

// ─── Live event log ──────────────────────────────────────────────
interface EventEntry { id: number; label: string; ts: string; color: string }
const EVENT_LABELS: Partial<Record<string, { label: string; color: string }>> = {
  idle:                { label: "System standby",           color: "#38bdf8" },
  thinking:            { label: "Neural processing active", color: "#a78bfa" },
  listening:           { label: "Audio input captured",     color: "#34d399" },
  speaking:            { label: "Audio output rendering",   color: "#fb923c" },
  sleeping:            { label: "Low-power mode engaged",   color: "#64748b" },
  focused:             { label: "Focus mode — deep task",   color: "#38bdf8" },
  happy:               { label: "Positive feedback loop",   color: "#fbbf24" },
  concerned:           { label: "Anomaly signal raised",    color: "#f87171" },
  excited:             { label: "High-priority trigger",    color: "#f472b6" },
  curious:             { label: "Curiosity probe sent",     color: "#22d3ee" },
};

function useEventLog(state: AvatarState) {
  const [log, setLog] = useState<EventEntry[]>([]);
  const counter = useRef(0);
  const prevState = useRef<AvatarState | null>(null);

  useEffect(() => {
    if (state === prevState.current) return;
    prevState.current = state;

    const entry = EVENT_LABELS[state];
    if (!entry) return;

    const now = new Date();
    const ts = `${String(now.getHours()).padStart(2,"0")}:${String(now.getMinutes()).padStart(2,"0")}:${String(now.getSeconds()).padStart(2,"0")}`;

    setLog((prev) => [
      { id: counter.current++, label: entry.label, ts, color: entry.color },
      ...prev,
    ].slice(0, 10));
  }, [state]);

  return log;
}

export function CompanionPage() {
  const avatarState = useAvatarStore((s) => s.state);
  const streamConnected = useAvatarStore((s) => s.streamConnected);
  const messages = useChatStore((s) => s.messages);
  const { rightPanelOpen, setRightPanelOpen } = useAppStore();
  const [historyOpen, setHistoryOpen] = useState(false);
  const [btDevices, setBtDevices] = useState<ConnectedBluetoothDevice[]>([]);
  const [wiredDevices, setWiredDevices] = useState<ConnectedExternalDevice[]>([]);
  const [wifiSSID, setWifiSSID] = useState<string | null>(null);
  const [wifiInterface, setWifiInterface] = useState<string | null>(null);
  const [wifiSsidHidden, setWifiSsidHidden] = useState(false);
  const [powerSource, setPowerSource] = useState<string | null>(null);
  const [powerCharging, setPowerCharging] = useState<boolean | null>(null);
  const [powerPercentage, setPowerPercentage] = useState<number | null>(null);
  const [powerAvailable, setPowerAvailable] = useState(false);
  const [browserOnline, setBrowserOnline] = useState<boolean>(() => (typeof navigator !== "undefined" ? navigator.onLine : false));
  const eventLog = useEventLog(avatarState);

  const todayMessages = useMemo(() => {
    const now = new Date();
    return messages.filter((m) => {
      const ts = new Date(m.timestamp);
      return (
        ts.getFullYear() === now.getFullYear() &&
        ts.getMonth() === now.getMonth() &&
        ts.getDate() === now.getDate() &&
        !m.streaming &&
        !!m.content?.trim()
      );
    });
  }, [messages]);

  useEffect(() => {
    let disposed = false;
    let timer: number | null = null;

    const pull = async () => {
      try {
        const snapshot = await apiConnectedDevices();
        if (disposed) return;
        setBtDevices(Array.isArray(snapshot.bluetooth?.connected) ? snapshot.bluetooth.connected : []);
        setWiredDevices(Array.isArray(snapshot.wired_external) ? snapshot.wired_external : []);
        setWifiSSID(snapshot.wifi?.connected ? (snapshot.wifi?.ssid ?? null) : null);
        setWifiInterface(snapshot.wifi?.interface ?? null);
        setWifiSsidHidden(Boolean(snapshot.wifi?.ssid_hidden));
        setPowerAvailable(Boolean(snapshot.power?.available));
        setPowerSource(snapshot.power?.source ?? null);
        setPowerCharging(snapshot.power?.charging ?? null);
        setPowerPercentage(typeof snapshot.power?.percentage === "number" ? snapshot.power.percentage : null);
      } catch (err) {
        if (disposed) return;
        if (err instanceof Error && err.message.includes("404")) {
          // Endpoint not available on current backend process; stop polling to avoid log spam.
          if (timer !== null) {
            window.clearInterval(timer);
            timer = null;
          }
          return;
        }
        setBtDevices([]);
        setWiredDevices([]);
        setWifiSSID(null);
        setWifiInterface(null);
        setWifiSsidHidden(false);
        setPowerAvailable(false);
        setPowerSource(null);
        setPowerCharging(null);
        setPowerPercentage(null);
      }
    };

    pull();
    timer = window.setInterval(pull, 5000);

    return () => {
      disposed = true;
      if (timer !== null) {
        window.clearInterval(timer);
      }
    };
  }, []);

  useEffect(() => {
    const onOnline = () => setBrowserOnline(true);
    const onOffline = () => setBrowserOnline(false);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, []);

  useEffect(() => {
    // Browser fallback when backend power data is unavailable.
    if (powerAvailable || typeof navigator === "undefined" || !("getBattery" in navigator)) {
      return;
    }

    let detached = false;
    type BatteryLike = {
      charging: boolean;
      level: number;
      addEventListener: (type: string, listener: () => void) => void;
      removeEventListener: (type: string, listener: () => void) => void;
    };
    let batteryObj: BatteryLike | null = null;

    const update = () => {
      if (detached || !batteryObj) return;
      setPowerAvailable(true);
      setPowerSource(batteryObj.charging ? "AC Power" : "Battery Power");
      setPowerCharging(batteryObj.charging);
      setPowerPercentage(Math.round((batteryObj.level ?? 0) * 100));
    };

    (navigator as Navigator & { getBattery?: () => Promise<BatteryLike> })
      .getBattery?.()
      .then((batt) => {
        if (detached) return;
        batteryObj = batt;
        update();
        batt.addEventListener("chargingchange", update);
        batt.addEventListener("levelchange", update);
      })
      .catch(() => {
        // ignore fallback failure
      });

    return () => {
      detached = true;
      if (!batteryObj) return;
      batteryObj.removeEventListener("chargingchange", update);
      batteryObj.removeEventListener("levelchange", update);
    };
  }, [powerAvailable]);

  const hasConnectedDevices = btDevices.length > 0 || wiredDevices.length > 0;
  const isLowBattery = powerPercentage !== null && powerPercentage < 30;
  const shouldWarnCharger = isLowBattery && powerCharging !== true;

  return (
    <div className="flex h-full gap-0 overflow-hidden">
      {/* ── CENTER ─── */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">

        {/* Top bar */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-border flex-shrink-0">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-widest text-nova-orange font-mono">
              NOVA · AI SYSTEM
            </p>
            <h2 className="font-display font-bold text-text-primary text-base">
              Good evening, Deekshith
            </h2>
          </div>
          <div className="flex items-center gap-3">
            <AnimatePresence mode="wait">
              <motion.div
                key={avatarState}
                initial={{ opacity: 0, x: 6 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -6 }}
                className="flex items-center gap-1.5 text-[11px] font-mono font-bold uppercase tracking-widest"
              >
                <motion.span
                  className="w-1.5 h-1.5 rounded-full"
                  style={{ background: avatarState === "sleeping" ? "#64748b" : avatarState === "thinking" ? "#a78bfa" : avatarState === "listening" ? "#34d399" : avatarState === "speaking" ? "#fb923c" : "#38bdf8" }}
                  animate={{ opacity: [1, 0.3, 1] }}
                  transition={{ duration: 1.2, repeat: Infinity }}
                />
                <span className="text-text-muted">{avatarState.toUpperCase()}</span>
              </motion.div>
            </AnimatePresence>

            <div className="flex items-center gap-1.5" title="Backend">
              {streamConnected ? <Wifi size={14} className="text-accent-green" /> : <WifiOff size={14} className="text-text-muted" />}
              <span className={`text-[12px] font-medium ${streamConnected ? "text-accent-green" : "text-text-muted"}`}>
                {streamConnected ? "ONLINE" : "CONNECTING"}
              </span>
            </div>

            <button
              onClick={() => setRightPanelOpen(!rightPanelOpen)}
              className="p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-elevated transition-colors"
            >
              {rightPanelOpen ? <PanelRightClose size={16} /> : <PanelRight size={16} />}
            </button>
          </div>
        </div>

        <div className="flex-1 min-h-0 flex overflow-hidden">
          <motion.aside
            initial={false}
            animate={{ width: historyOpen ? 320 : 0, opacity: historyOpen ? 1 : 0 }}
            transition={{ type: "spring", stiffness: 330, damping: 34 }}
            className="border-r border-border overflow-hidden flex-shrink-0"
          >
            <div className="h-full w-[320px] p-3.5">
              <div className="bg-bg-card border border-border rounded-2xl h-full flex flex-col overflow-hidden">
                <div className="px-3.5 py-3 border-b border-border flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-text-muted font-mono">
                    <MessageSquareText size={13} />
                    <span>Today History</span>
                  </div>
                  <button
                    onClick={() => setHistoryOpen(false)}
                    className="p-1 rounded-md text-text-muted hover:text-text-primary hover:bg-bg-elevated transition-colors"
                    title="Close history"
                  >
                    <X size={13} />
                  </button>
                </div>

                <div className="flex-1 overflow-y-auto px-3 py-2 space-y-2">
                  {todayMessages.length === 0 ? (
                    <div className="h-full flex items-center justify-center px-4 text-center text-[12px] text-text-muted">
                      No history yet for today.
                    </div>
                  ) : (
                    todayMessages.map((msg) => {
                      const ts = new Date(msg.timestamp);
                      const hh = String(ts.getHours()).padStart(2, "0");
                      const mm = String(ts.getMinutes()).padStart(2, "0");
                      const roleTone =
                        msg.role === "user"
                          ? "border-accent-purple/30 bg-accent-purple/10"
                          : msg.role === "error"
                          ? "border-accent-red/30 bg-accent-red/10"
                          : "border-nova-orange/30 bg-nova-orange/10";

                      return (
                        <div key={msg.id} className={`rounded-xl border px-2.5 py-2 ${roleTone}`}>
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-[10px] font-mono uppercase tracking-wider text-text-muted">
                              {msg.role === "user" ? "You" : msg.role === "error" ? "Error" : "NOVA"}
                            </span>
                            <span className="text-[10px] font-mono text-text-muted">{hh}:{mm}</span>
                          </div>
                          <p className="text-[12px] leading-snug text-text-secondary line-clamp-4 whitespace-pre-wrap break-words">
                            {msg.content}
                          </p>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            </div>
          </motion.aside>

          <div className="flex-1 grid grid-rows-[1fr_132px] overflow-hidden">
          <div className="relative overflow-hidden bg-bg">
            <NOVACore />

              <motion.button
                type="button"
                onClick={() => setHistoryOpen((v) => !v)}
                whileHover={{ scale: 1.04 }}
                whileTap={{ scale: 0.97 }}
                className="absolute bottom-4 right-4 z-20 flex items-center gap-2 px-3 py-2 rounded-full border border-[#38bdf850] bg-[#0f1a2a]/90 text-[#7dd3fc] text-[11px] font-mono uppercase tracking-wider shadow-[0_6px_28px_rgba(8,47,73,0.45)]"
                title="Toggle chat history"
              >
                <MessageSquareText size={13} />
                <span>{historyOpen ? "Hide History" : "Show History"}</span>
                <span className="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-[#38bdf820] text-[10px] font-bold">
                  {todayMessages.length}
                </span>
              </motion.button>
          </div>
          <div className="border-t border-border overflow-hidden">
            <ChatPanel
              showHistory={false}
              showEmptyState={false}
              helperText="Response is pinned in the core until your next question · Enter to send · Shift+Enter for newline"
            />
          </div>
          </div>
        </div>
      </div>

      {/* ── RIGHT PANEL ─── */}
      <motion.aside
        initial={false}
        animate={{ width: rightPanelOpen ? 288 : 0, opacity: rightPanelOpen ? 1 : 0 }}
        transition={{ type: "spring", stiffness: 350, damping: 36 }}
        className="flex flex-col border-l border-border overflow-hidden flex-shrink-0"
      >
        <div className="overflow-y-auto h-full p-4 space-y-3 w-[288px]">

          {/* Agent Status — loads are computed from live engine state */}
          <RightCard title="Agent Activity" icon={<Bot size={14} />} tooltip="Load % reflects actual workload per engine state">
            <div className="space-y-1.5">
              {AGENT_DEFS.map((agent) => {
                const load = agentLoad(agent.id, avatarState);
                const status = agentStatus(load);
                const barColor =
                  status === "active"  ? "#34d399" :
                  status === "standby" ? "#fbbf24" : "#334155";

                return (
                  <motion.div
                    key={agent.id}
                    className="group flex flex-col gap-1 px-2.5 py-2 rounded-lg bg-bg-elevated border border-border"
                    whileHover={{ borderColor: `${barColor}30` }}
                  >
                    <div className="flex items-center gap-2">
                      <motion.span
                        className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                        style={{ background: barColor }}
                        animate={status === "active" ? { opacity: [1, 0.3, 1] } : {}}
                        transition={{ duration: 1.4, repeat: Infinity }}
                      />
                      <span className="text-[12px] text-text-secondary flex-1 font-medium">{agent.label}</span>
                      <span className="text-[10px] font-mono font-bold" style={{ color: barColor }}>
                        {load > 0 ? `${load}%` : "—"}
                      </span>
                      <span className={`text-[9px] font-bold uppercase tracking-wide ${AGENT_STATUS_COLOR[status]}`}>
                        {status}
                      </span>
                    </div>
                    {/* Load bar */}
                    <div className="h-0.5 rounded-full bg-bg-card overflow-hidden">
                      <motion.div
                        className="h-full rounded-full"
                        style={{ background: barColor }}
                        animate={{ width: `${load}%` }}
                        transition={{ duration: 0.55, ease: "easeOut" }}
                      />
                    </div>
                    {/* Role sub-label */}
                    <span className="text-[9.5px] text-text-muted font-mono tracking-wide opacity-0 group-hover:opacity-100 transition-opacity">
                      {agent.role}
                    </span>
                  </motion.div>
                );
              })}
            </div>
            <p className="text-[10px] text-text-muted font-mono mt-2 opacity-50 tracking-wide">
              DRIVEN BY ENGINE STATE · UPDATES WITH EVERY EVENT
            </p>
          </RightCard>

          {/* Dynamic connected devices */}
          <RightCard title="Connections" icon={<Cable size={14} />}>
            <div className="space-y-2">
              <div className="rounded-lg border border-border bg-bg-elevated px-2.5 py-2">
                <div className="flex items-center gap-2">
                  {powerCharging ? (
                    <BatteryCharging size={12} className="text-accent-green flex-shrink-0" />
                  ) : (
                    <Battery size={12} className={`${isLowBattery ? "text-accent-red" : "text-text-muted"} flex-shrink-0`} />
                  )}
                  <span className="text-[12px] text-text-primary font-medium truncate flex-1">Power</span>
                  <span className={`text-[10px] font-mono ${powerCharging ? "text-accent-green" : isLowBattery ? "text-accent-red" : "text-text-muted"}`}>
                    {powerCharging ? "charging" : powerAvailable ? "on battery" : "unknown"}
                  </span>
                </div>
                <p className={`text-[10px] font-mono mt-1 truncate ${isLowBattery ? "text-accent-red" : "text-text-muted"}`}>
                  {powerPercentage !== null ? `Battery ${powerPercentage}%` : "Battery percentage unavailable"}
                  {powerSource ? ` · ${powerSource}` : ""}
                </p>
                {shouldWarnCharger && (
                  <p className="text-[9px] text-accent-red/90 font-mono mt-1 tracking-wide">
                    Battery low. Connect charger.
                  </p>
                )}
              </div>

              {wifiSSID && (
                <div className="rounded-lg border border-border bg-bg-elevated px-2.5 py-2">
                  <div className="flex items-center gap-2">
                    <Wifi size={12} className="text-[#22d3ee] flex-shrink-0" />
                    <span className="text-[12px] text-text-primary font-medium truncate flex-1">{wifiSSID}</span>
                    <span className="text-[10px] font-mono text-accent-green">connected</span>
                  </div>
                  {wifiInterface && <p className="text-[10px] text-text-muted font-mono mt-1 truncate">{wifiInterface}</p>}
                </div>
              )}

              {!wifiSSID && wifiInterface && (
                <div className="rounded-lg border border-border bg-bg-elevated px-2.5 py-2">
                  <div className="flex items-center gap-2">
                    <Wifi size={12} className="text-text-muted flex-shrink-0" />
                    <span className="text-[12px] text-text-secondary font-medium truncate flex-1">Wi-Fi</span>
                    <span className={`text-[10px] font-mono ${wifiSsidHidden ? "text-nova-amber" : "text-text-muted"}`}>{wifiSsidHidden ? "ssid hidden" : "disconnected"}</span>
                  </div>
                  <p className="text-[10px] text-text-muted font-mono mt-1 truncate">{wifiSsidHidden ? "Connected, but macOS hides SSID in CLI output" : wifiInterface}</p>
                </div>
              )}

              {!wifiSSID && !wifiInterface && (
                <div className="rounded-lg border border-border bg-bg-elevated px-2.5 py-2">
                  <div className="flex items-center gap-2">
                    <Wifi size={12} className={`${browserOnline ? "text-[#22d3ee]" : "text-text-muted"} flex-shrink-0`} />
                    <span className={`text-[12px] ${browserOnline ? "text-text-primary" : "text-text-secondary"} font-medium truncate flex-1`}>Wi-Fi</span>
                    <span className={`text-[10px] font-mono ${browserOnline ? "text-accent-green" : "text-text-muted"}`}>{browserOnline ? "connected" : "unavailable"}</span>
                  </div>
                  <p className="text-[10px] text-text-muted font-mono mt-1 truncate">{browserOnline ? "Network online · SSID needs backend" : "Backend offline or no network data"}</p>
                </div>
              )}

              {btDevices.map((d, idx) => {
                  const BatteryIcon = pickDeviceIcon(d.name, "bluetooth");
                  const batteryTone = batteryColorClass(d.battery ?? null);
                  return (
                    <div key={`${d.name}-${idx}`} className="rounded-lg border border-border bg-bg-elevated px-2.5 py-2">
                      <div className="flex items-center gap-2">
                        <BatteryIcon size={12} className="text-[#60a5fa] flex-shrink-0" />
                        <span className="text-[12px] text-text-primary font-medium truncate flex-1">{d.name}</span>
                        {d.battery && <span className={`text-[10px] font-mono ${batteryTone}`}>{d.battery}</span>}
                      </div>
                      {d.address && <p className="text-[10px] text-text-muted font-mono mt-1 truncate">{d.address}</p>}
                    </div>
                  );
                })}

              {wiredDevices.map((d, idx) => {
                  const DeviceIcon = pickDeviceIcon(d.name, d.type);
                  return (
                    <div key={`${d.name}-${idx}`} className="rounded-lg border border-border bg-bg-elevated px-2.5 py-2">
                      <div className="flex items-center gap-2">
                        <DeviceIcon size={12} className="text-[#f59e0b] flex-shrink-0" />
                        <span className="text-[12px] text-text-primary font-medium truncate flex-1">{d.name}</span>
                        <span className="text-[10px] font-mono text-text-muted uppercase">{d.type ?? "wired"}</span>
                      </div>
                      {(d.transport || d.manufacturer) && (
                        <p className="text-[10px] text-text-muted font-mono mt-1 truncate">
                          {[d.transport, d.manufacturer].filter(Boolean).join(" · ")}
                        </p>
                      )}
                    </div>
                  );
                })}
              {!hasConnectedDevices && (
                <p className="text-[10px] text-text-muted font-mono opacity-70">No active external devices</p>
              )}
            </div>
          </RightCard>

          {/* Live Event Log */}
          <RightCard title="Event Stream" icon={<Radio size={14} />}>
            <div className="space-y-1">
              {eventLog.length === 0 ? (
                <div className="flex items-center gap-2 py-2">
                  <motion.span
                    className="w-1 h-1 rounded-full bg-[#334155]"
                    animate={{ opacity: [0.3, 1, 0.3] }}
                    transition={{ duration: 1.5, repeat: Infinity }}
                  />
                  <span className="text-[11px] text-text-muted font-mono">Awaiting events…</span>
                </div>
              ) : (
                <AnimatePresence initial={false}>
                  {eventLog.map((entry) => (
                    <motion.div
                      key={entry.id}
                      initial={{ opacity: 0, x: -8, height: 0 }}
                      animate={{ opacity: 1, x: 0, height: "auto" }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="flex items-center gap-2 py-1"
                    >
                      <span className="w-1 h-1 rounded-full flex-shrink-0" style={{ background: entry.color }} />
                      <span className="text-[11px] text-text-secondary flex-1 leading-snug">{entry.label}</span>
                      <span className="text-[9px] font-mono text-text-muted flex-shrink-0">{entry.ts}</span>
                    </motion.div>
                  ))}
                </AnimatePresence>
              )}
            </div>
          </RightCard>

          {/* Neural Activity — bars animate with state */}
          <RightCard title="Neural Activity" icon={<Activity size={14} />}>
            {(() => {
              const vitals = [
                { label: "Inference",    value: agentLoad("brain",   avatarState), color: "#a78bfa" },
                { label: "Context",      value: agentLoad("memory",  avatarState), color: "#38bdf8" },
                { label: "Voice I/O",    value: agentLoad("voice",   avatarState), color: "#34d399" },
                { label: "Task Queue",   value: agentLoad("planner", avatarState), color: "#fb923c" },
              ];
              return (
                <div className="space-y-2">
                  {vitals.map((v) => (
                    <div key={v.label} className="flex items-center gap-2">
                      <span className="text-[11px] text-text-muted w-20 flex-shrink-0 font-mono">{v.label}</span>
                      <div className="flex-1 h-1 rounded-full bg-bg-elevated overflow-hidden">
                        <motion.div
                          className="h-full rounded-full"
                          style={{ background: v.color }}
                          animate={{ width: `${v.value}%` }}
                          transition={{ duration: 0.55, ease: "easeOut" }}
                        />
                      </div>
                      <span className="text-[10px] font-mono w-8 text-right" style={{ color: v.value > 0 ? v.color : "#334155" }}>
                        {v.value > 0 ? `${v.value}%` : "—"}
                      </span>
                    </div>
                  ))}
                </div>
              );
            })()}
          </RightCard>

          {/* Active Tasks */}
          <RightCard title="Active Tasks" icon={<CheckSquare size={14} />} actionLabel="View All">
            <div className="space-y-1.5">
              {MOCK_TASKS.map((t) => (
                <motion.div
                  key={t.id}
                  className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-bg-elevated transition-colors"
                  whileHover={{ x: 2 }}
                >
                  <CircleDot size={10} className={`flex-shrink-0 ${STATUS_COLOR[t.status]}`} />
                  <p className="text-[12px] text-text-secondary flex-1 leading-snug">{t.title}</p>
                  <span className={`text-[10px] font-bold ${STATUS_COLOR[t.status]}`}>
                    {STATUS_LABEL[t.status]}
                  </span>
                </motion.div>
              ))}
            </div>
          </RightCard>

          {/* Quick Actions */}
          <RightCard title="Quick Actions" icon={<Zap size={14} />}>
            <div className="grid grid-cols-2 gap-1.5">
              {[
                { icon: "💻", label: "VS Code" },
                { icon: "🔍", label: "Search" },
                { icon: "🧠", label: "Memory" },
                { icon: "✅", label: "Tasks" },
                { icon: "🤖", label: "Agents" },
                { icon: "📡", label: "Monitor" },
              ].map((a) => (
                <motion.button
                  key={a.label}
                  whileHover={{ scale: 1.03, borderColor: "#38bdf840" }}
                  whileTap={{ scale: 0.97 }}
                  className="flex items-center gap-2 px-3 py-2 rounded-xl border border-border bg-bg-elevated text-[12px] font-medium text-text-secondary hover:text-text-primary transition-all"
                >
                  <span>{a.icon}</span>
                  <span>{a.label}</span>
                </motion.button>
              ))}
            </div>
          </RightCard>

        </div>
      </motion.aside>
    </div>
  );
}

function pickDeviceIcon(name: string, type?: string) {
  const text = `${name} ${type ?? ""}`.toLowerCase();
  if (text.includes("airpods") || text.includes("earbud") || text.includes("buds")) {
    return Ear;
  }
  if (text.includes("headphone") || text.includes("headset")) {
    return Headphones;
  }
  if (text.includes("phone") || text.includes("iphone") || text.includes("android")) {
    return Smartphone;
  }
  if (text.includes("usb") || text.includes("dongle")) {
    return Usb;
  }
  if (text.includes("disk") || text.includes("ssd") || text.includes("drive")) {
    return HardDrive;
  }
  if (text.includes("bluetooth")) {
    return Bluetooth;
  }
  return Cable;
}

function batteryColorClass(raw: string | null) {
  if (!raw) return "text-text-muted";
  const match = raw.match(/\d{1,3}/);
  if (!match) return "text-text-muted";
  const level = Number(match[0]);
  if (level >= 60) return "text-accent-green";
  if (level >= 30) return "text-nova-amber";
  return "text-accent-red";
}

function RightCard({
  title, icon, actionLabel, tooltip, children,
}: {
  title: string; icon: React.ReactNode; actionLabel?: string; tooltip?: string; children: React.ReactNode;
}) {
  return (
    <motion.div
      className="bg-bg-card border border-border rounded-2xl p-3.5"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      title={tooltip}
    >
      <div className="flex items-center justify-between mb-2.5">
        <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-text-muted font-mono">
          {icon}
          <span>{title}</span>
        </div>
        {actionLabel && (
          <button className="text-[11px] text-nova-orange hover:text-nova-glow font-medium">
            {actionLabel} →
          </button>
        )}
      </div>
      {children}
    </motion.div>
  );
}
