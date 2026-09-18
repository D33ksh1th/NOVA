import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Activity, ArrowUpRight, Battery, Bluetooth, Bot, Headphones, History, MessageSquare, PanelRight, PanelRightClose, Radio, Usb, Wifi } from "lucide-react";
import { CoreSignal } from "@/components/Avatar/CoreSignal";
import { ChatPanel } from "@/components/Chat/ChatPanel";
import { useAvatarStore } from "@/stores/useAvatarStore";
import { useAppStore } from "@/stores/useAppStore";
import { useChatStore } from "@/stores/useChatStore";
import { useSettingsStore } from "@/stores/useSettingsStore";
import { apiConnectedDevices } from "@/services/api";
import { NowPlaying } from "@/components/NowPlaying";

export function CompanionPage() {
  const state = useAvatarStore((store) => store.state);
  const connected = useAvatarStore((store) => store.streamConnected);
  const speechText = useAvatarStore((store) => store.speechText);
  const messages = useChatStore((store) => store.messages);
  const voice = useSettingsStore((store) => store.voice);
  const { rightPanelOpen, setRightPanelOpen, setPage, musicPlayerOpen, setMusicPlayerOpen } = useAppStore();
  const [devices, setDevices] = useState<Awaited<ReturnType<typeof apiConnectedDevices>> | null>(null);
  const [devicesAvailable, setDevicesAvailable] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const snapshot = await apiConnectedDevices();
        if (!disposed) { setDevices(snapshot); setDevicesAvailable(true); }
      } catch { if (!disposed) setDevicesAvailable(false); }
      finally { if (!disposed) timer = setTimeout(refresh, 10000); }
    }
    void refresh();
    return () => { disposed = true; clearTimeout(timer); };
  }, []);
  const recent = messages.filter(message => message.content?.trim() && !message.streaming).slice(-6).reverse();
  const activity = connected ? ({ idle: "Ready when you are.", listening: "I'm listening.", thinking: "Working through it.", speaking: "Here's what I found.", sleeping: "Standing by." } as Record<string, string>)[state] || "Right here with you." : "Waiting for a connection.";
  return <div className="h-full flex flex-col xl:flex-row overflow-y-auto xl:overflow-hidden">
    <section className="shrink-0 xl:flex-1 min-w-0 flex flex-col min-h-[640px] xl:min-h-0">
      <header className="px-5 sm:px-8 pt-7 pb-5 flex items-start justify-between gap-4">
        <div><p className="nova-panel-heading mb-2">Personal intelligence</p><h1 className="text-4xl sm:text-5xl font-display font-medium text-text-primary">NOVA<span className="text-nova-orange">.</span></h1></div>
        <button title={rightPanelOpen ? "Hide overview" : "Show overview"} aria-label={rightPanelOpen ? "Hide overview" : "Show overview"} onClick={() => setRightPanelOpen(!rightPanelOpen)} className="h-9 w-9 grid place-items-center border border-border rounded-md text-text-secondary hover:text-nova-orange">{rightPanelOpen ? <PanelRightClose size={17} /> : <PanelRight size={17} />}</button>
      </header>
      <div className="relative flex-1 min-h-[230px] flex flex-col justify-center">
        <div className="h-[240px] sm:h-[300px] xl:h-[min(34vh,380px)] w-full"><CoreSignal /></div>
        <div className="px-5 sm:px-8 text-center"><motion.p key={activity} initial={false} animate={{ opacity: 1, y: 0 }} className="text-xl sm:text-2xl font-display text-text-primary">{activity}</motion.p><p className="mt-3 text-xs text-text-muted">{connected ? `Event stream connected / ${state}` : "Backend event stream unavailable"}</p></div>
      </div>
      {musicPlayerOpen && <NowPlaying onClose={() => setMusicPlayerOpen(false)} />}
      <div className="px-5 sm:px-8 pt-5 pb-2">
        {speechText && <div className="border-l-2 border-nova-orange/50 pl-4 mb-5 max-h-32 overflow-y-auto"><p className="nova-panel-heading mb-2">Latest response</p><p className="text-sm leading-6 text-text-secondary whitespace-pre-wrap break-words">{speechText}</p></div>}
        <div className="flex flex-wrap gap-2 justify-center">
          <button onClick={() => setPage("skills")} className="nova-quick-action"><Bot size={15} className="text-nova-orange" />Research<ArrowUpRight size={13} /></button>
          <button onClick={() => setMusicPlayerOpen(true)} aria-expanded={musicPlayerOpen} title="Show music player" className="nova-quick-action"><Headphones size={15} className="text-accent-blue" />Music<ArrowUpRight size={13} /></button>
          <button onClick={() => setHistoryOpen(!historyOpen)} aria-expanded={historyOpen} className="nova-quick-action"><History size={15} className="text-accent-red" />History<span className="text-text-muted">{messages.length}</span></button>
        </div>
        {historyOpen && <div className="mt-4 max-h-48 overflow-y-auto divide-y divide-border">{recent.length ? recent.map(message => <button key={message.id} onClick={() => setPage("chat")} className="block w-full text-left py-3"><span className="nova-panel-heading">{message.role === "user" ? "You" : "NOVA"}</span><p className="text-sm text-text-secondary line-clamp-2 break-words mt-1">{message.content}</p></button>) : <p className="text-center text-sm text-text-muted py-4">No conversations yet.</p>}</div>}
      </div>
      <div className="shrink-0"><ChatPanel showHistory={false} showEmptyState={false} helperText="" /></div>
    </section>
    {rightPanelOpen && <aside aria-label="Core overview" className="xl:w-[300px] shrink-0 border-t xl:border-t-0 xl:border-l border-border px-5 sm:px-7 py-7 xl:overflow-y-auto">
      <div className="flex items-center justify-between mb-7"><h2 className="text-lg font-display">Overview</h2><Activity size={17} className="text-nova-orange" /></div>
      <section className="pb-6 border-b border-border"><h3 className="nova-panel-heading mb-4">Conversation</h3><div className="flex items-baseline gap-2"><span className="font-display text-4xl text-text-primary">{messages.filter(message => message.role === "user").length}</span><span className="text-sm text-text-muted">messages from you</span></div><button onClick={() => setPage("chat")} className="text-sm text-nova-orange flex items-center gap-2 mt-4">Open conversation<ArrowUpRight size={14} /></button></section>
      <section className="py-6 border-b border-border"><h3 className="nova-panel-heading mb-4">Voice</h3><div className="flex items-center gap-3"><Radio size={20} className="text-accent-blue" /><div><p className="text-sm text-text-primary">{voice.accent === "english_friday" || voice.accent === "english_clear" ? "Emma" : "George"}</p><p className="text-xs text-text-muted mt-1">{voice.style} / {voice.speakBack ? "Speak back on" : "Speak back off"}</p></div></div><button onClick={() => setPage("settings")} className="text-xs text-text-secondary hover:text-nova-orange mt-4">Voice settings</button></section>
      <section className="py-6 border-b border-border"><h3 className="nova-panel-heading mb-4">Connected devices</h3>{!devicesAvailable ? <p className="text-sm text-text-muted">Device snapshot unavailable.</p> : <div className="space-y-4">
        <div className="flex items-center gap-3 text-sm"><Wifi size={16} className="text-accent-blue shrink-0" /><span className="min-w-0 break-words">{devices?.wifi?.connected ? devices.wifi.ssid || "Wi-Fi connected" : "Wi-Fi disconnected"}</span></div>
        {devices?.power?.available && <div className="flex items-center gap-3 text-sm"><Battery size={16} className="text-nova-amber shrink-0" /><span>{typeof devices.power.percentage === "number" ? `${devices.power.percentage}%` : "Battery"} / {devices.power.charging ? "Charging" : devices.power.source || "Not charging"}</span></div>}
        {devices?.bluetooth?.connected?.map((device, index) => <div key={`${device.name}-${index}`} className="flex items-center gap-3 text-sm"><Bluetooth size={16} className="text-accent-blue shrink-0" /><span className="break-words min-w-0">{device.name}</span></div>)}
        {devices?.wired_external?.map((device, index) => <div key={`${device.name}-${index}`} className="flex items-center gap-3 text-sm"><Usb size={16} className="text-text-muted shrink-0" /><span className="break-words min-w-0">{device.name}</span></div>)}
      </div>}</section>
      <section className="pt-6"><div className="flex justify-between items-center mb-4"><h3 className="nova-panel-heading">Recent exchange</h3><MessageSquare size={14} className="text-text-muted" /></div>{recent[0] ? <p className="text-sm text-text-secondary leading-6 break-words line-clamp-5">{recent[0].content}</p> : <p className="text-sm text-text-muted">No messages yet.</p>}</section>
    </aside>}
  </div>;
}