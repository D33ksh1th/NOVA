import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Activity, ArrowUp, Bot, FileSearch, RefreshCw, ShieldCheck, Square, Workflow, ScanSearch, Compass, Layers3, Volume2, VolumeX } from "lucide-react";
import { apiAgentRuntimeCommand, apiAgentRuntimeStatus, apiRepositoryReview } from "@/services/api";
import type { AgentRuntimeAction, AgentRuntimeStatus } from "@/services/api";
import { ResearchReports } from "@/components/ResearchReports";
import { useAppStore } from "@/stores/useAppStore";

const toolStyle = "h-9 w-9 shrink-0 inline-flex items-center justify-center rounded-md border border-border text-text-secondary hover:text-text-primary hover:bg-bg-elevated disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline focus-visible:outline-2 focus-visible:outline-nova-orange";
const label = (value: string) => value.replace(/_/g, " ").toLowerCase();
const outcomeColor = (value: string) => ["FAILED", "REFUSED", "CANCELLED", "HALTED"].includes(value)
  ? "text-accent-red" : value === "PARTIAL" ? "text-nova-amber" : ["SUCCESS", "COMPLETED", "READY"].includes(value)
    ? "text-accent-green" : "text-accent-blue";

function TaskAnnouncements({ message, identity }: { message: string; identity: string }) {
  const [enabled, setEnabled] = useState(false);
  const [voice, setVoice] = useState<SpeechSynthesisVoice>();
  const ownedSpeech = useRef(false);

  useEffect(() => {
    const synthesis = window.speechSynthesis;
    if (!synthesis || !window.SpeechSynthesisUtterance) return;
    const updateVoices = () => setVoice(synthesis.getVoices().find((item) => item.localService && /^en(?:-|$)/i.test(item.lang)));
    updateVoices();
    synthesis.addEventListener("voiceschanged", updateVoices);
    return () => synthesis.removeEventListener("voiceschanged", updateVoices);
  }, []);

  useEffect(() => {
    if (!enabled || !voice || !message) return;
    const synthesis = window.speechSynthesis;
    const stop = () => {
      if (ownedSpeech.current) synthesis.cancel();
      ownedSpeech.current = false;
    };
    const speak = () => {
      if (document.hidden) return;
      stop();
      const utterance = new SpeechSynthesisUtterance(message);
      utterance.voice = voice;
      utterance.onend = utterance.onerror = () => { ownedSpeech.current = false; };
      ownedSpeech.current = true;
      synthesis.speak(utterance);
    };
    const visibility = () => { if (document.hidden) stop(); };
    speak();
    document.addEventListener("visibilitychange", visibility);
    return () => { stop(); document.removeEventListener("visibilitychange", visibility); };
  }, [enabled, voice, message, identity]);

  return <>
    <p className="sr-only" role="status" aria-label="Task updates" aria-live="polite" aria-atomic="true">{message}</p>
    <button type="button" className={toolStyle} disabled={!voice} aria-label="Speak task updates"
      aria-pressed={enabled && !!voice} title={voice ? "Speak task updates" : "No local English speech voice available"}
      onClick={() => setEnabled((value) => !value)}>
      {enabled && voice ? <Volume2 size={16} /> : <VolumeX size={16} />}
    </button>
  </>;
}

export function AgentsPage() {
  const [snapshot, setSnapshot] = useState<AgentRuntimeStatus | null>(null);
  const [connected, setConnected] = useState(false);
  const [selectedId, setSelectedId] = useState("");
  const [topic, setTopic] = useState("");
  const [mode, setMode] = useState("research");
  const [repositoryFiles, setRepositoryFiles] = useState("");
  const [reply, setReply] = useState("");
  const [pending, setPending] = useState(false);
  const commandLock = useRef(false);
  const [revision, setRevision] = useState(0);
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const stopDialog = useRef<HTMLDialogElement>(null);
  const [view, setView] = useState("Reports");
  const openReport = useAppStore((state) => state.openReport);

  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    let controller: AbortController | undefined;
    let fetching = false;
    async function refresh() {
      if (disposed || document.hidden || fetching) return;
      fetching = true;
      controller = new AbortController();
      const timeout = setTimeout(() => controller?.abort(), 8000);
      try {
        const next = await apiAgentRuntimeStatus(controller.signal);
        if (!Array.isArray(next.graphs) || !Array.isArray(next.agents)) throw new Error("Invalid status");
        if (!disposed) { setSnapshot(next); setConnected(true); }
      } catch {
        if (!disposed) setConnected(false);
      } finally {
        clearTimeout(timeout);
        fetching = false;
        if (!disposed && !document.hidden) timer = setTimeout(refresh, 1500);
      }
    }
    function visibility() {
      clearTimeout(timer);
      if (document.hidden) controller?.abort();
      else void refresh();
    }
    void refresh();
    document.addEventListener("visibilitychange", visibility);
    return () => { disposed = true; clearTimeout(timer); controller?.abort(); document.removeEventListener("visibilitychange", visibility); };
  }, [revision]);

  const graph = snapshot?.graphs.find((item) => item.graph_id === selectedId) ?? snapshot?.graphs[0];
  const ready = connected && snapshot?.state === "READY";
  const busy = !!snapshot?.pending_runs || !!snapshot?.graphs.some((item) => item.status === "RUNNING");
  const readerReady = ready && !!snapshot?.agents.some((agent) => agent.id === "repo_reader" && agent.enabled);
  const filePaths = repositoryFiles.split("\n").map((path) => path.trim()).filter(Boolean);
  const validFiles = filePaths.length > 0 && filePaths.length <= 3 && new Set(filePaths).size === filePaths.length
    && filePaths.every((path) => path.length <= 240 && !path.startsWith("/") && !path.includes("\\")
      && !path.split("/").some((part) => ["", ".", ".."].includes(part)));
  const announcement = !connected ? "Task status unavailable. Waiting for a fresh snapshot."
    : graph ? `${label(graph.status)}. ${graph.finished_tasks} of ${graph.total_tasks} tasks finished; ${graph.successful_tasks} successful. ${graph.nodes.map((node) => `${node.name}: ${label(node.state === "COMPLETED" ? node.result_status || node.state : node.state)}`).join(". ")}.`
    : snapshot?.pending_runs ? "Research queued." : `Runtime ${label(snapshot?.state || "UNKNOWN")}. No recorded runs.`;
  const nodes = graph?.nodes.filter((node) => `${node.name} ${node.agent}`.toLowerCase().includes(search.toLowerCase())
    && (filter === "all" || (filter === "active" ? ["RUNNING", "QUEUED", "PENDING", "READY", "RETRYING"].includes(node.state)
      : ["FAILED", "REFUSED", "CANCELLED", "PARTIAL"].includes(node.result_status || node.state)))) ?? [];

  async function command(action: AgentRuntimeAction) {
    if (commandLock.current) return;
    commandLock.current = true;
    setPending(true);
    try {
      const result = action === "research" && mode === "repository"
        ? await apiRepositoryReview(topic.trim(), filePaths) : await apiAgentRuntimeCommand(action, topic.trim());
      setReply(result.response);
      if (result.data?.report_id) { openReport(result.data.report_id); setView("Reports"); }
      if (["agent_research_started", "agent_repository_started"].includes(result.action)) setTopic("");
    } catch {
      setReply("NOVA did not acknowledge this request. Check agent status before submitting again.");
    } finally {
      commandLock.current = false;
      setPending(false);
      setRevision((value) => value + 1);
    }
  }

  return <div className="h-full overflow-y-auto text-text-primary" style={{ letterSpacing: 0 }}>
    <header className="px-4 sm:px-6 py-5 border-b border-border flex flex-wrap items-center justify-between gap-4">
      <div><p className="nova-panel-heading mb-2">Research workspace</p><div className="flex items-center gap-3"><Bot size={22} className="text-nova-orange" /><h1 className="font-display font-medium text-2xl">Agents</h1></div></div>
      <div className="flex items-center gap-3 text-xs text-text-secondary"><ShieldCheck size={15} />Read only
        <span className={connected ? "text-accent-green" : "text-nova-amber"}>{connected ? "Connected" : "Disconnected"}</span>
        <button className={toolStyle} onClick={() => setRevision((value) => value + 1)} title="Refresh agent status" aria-label="Refresh agent status"><RefreshCw size={16} /></button>
      </div>
    </header>
    <div className="px-4 sm:px-6 max-w-6xl mx-auto">
      {mode === "research" ? <section aria-label="Research team" className="grid grid-cols-1 sm:grid-cols-3 gap-2 sm:gap-3 py-6">
        {[{ id: "scout", name: "Scout", role: "Source discovery", icon: ScanSearch, color: "#d8b142" }, { id: "atlas", name: "Atlas", role: "Independent evidence", icon: Compass, color: "#83b4e8" }, { id: "prism", name: "Prism", role: "Comparison & synthesis", icon: Layers3, color: "#e89582" }].map((agent, index) => {
          const node = graph?.nodes.find(item => item.id === agent.id);
          const outcome = node ? node.state === "COMPLETED" ? node.result_status || node.state : node.state : snapshot?.pending_runs ? "QUEUED" : "NOT_STARTED";
          const active = connected && node?.state === "RUNNING";
          return <motion.div key={agent.id} initial={false} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.06 }} className="relative min-w-0 grid grid-cols-[28px_minmax(0,1fr)_auto] items-center gap-2 sm:block rounded-lg border border-border p-2.5 sm:p-4 overflow-hidden" style={{ background: `linear-gradient(120deg, ${agent.color}18, transparent)`, borderTopColor: agent.color }}>
            <div className="flex justify-between items-center"><agent.icon size={23} strokeWidth={1.4} style={{ color: agent.color }} /><div className="hidden sm:block"><span className="nova-activity-bars" data-active={active} style={{ color: agent.color }} aria-hidden="true">{[0,1,2,3].map(bar => <span key={bar} />)}</span></div></div>
            <h2 className="font-display text-sm sm:text-lg sm:mt-4" style={{ color: agent.color }}>{agent.name}</h2><p className="hidden sm:block text-xs text-text-secondary mt-1">{agent.role}</p><p className="text-[10px] sm:text-[11px] sm:mt-4 flex items-center gap-2 break-words" style={{ color: connected ? agent.color : "#b9bbc5" }}><span className="w-1 h-1 shrink-0 rounded-full bg-current" />{!connected ? "Unavailable" : label(outcome)}</p>
            {active && <motion.div className="absolute bottom-0 left-0 h-0.5 w-1/3" style={{ background: agent.color }} animate={{ x: ["-100%", "400%"] }} transition={{ repeat: Infinity, duration: 2, ease: "linear" }} />}
          </motion.div>;
        })}
      </section> : <section aria-label="Repository worker" className="py-6 flex flex-wrap items-center justify-between gap-3 border-b border-border">
        <div><h2 className="font-display text-lg text-accent-blue">Repo Reader</h2><p className="text-xs text-text-secondary mt-1">nova-desktop / Selected files</p></div>
        <span className="text-xs text-text-secondary">{!readerReady ? "Unavailable" : graph?.nodes.some(node => node.agent === "repo_reader") ? label(graph.status) : "Ready"}</span>
      </section>}
      {!connected && <p role="alert" className="py-4 text-sm text-nova-amber">{snapshot ? "Connection lost. Showing the last received snapshot." : "Agent runtime unavailable. The backend may need a restart to load agent support."}</p>}
      <section aria-label="Agent command" className="pb-6 border-b border-border">
        <div role="group" aria-label="Task mode" className="flex flex-wrap gap-1 mb-4 border-b border-border">
          {[{ id: "research", text: "Web research" }, { id: "repository", text: "Repository review" }].map((item) =>
            <button key={item.id} type="button" aria-pressed={mode === item.id} disabled={pending}
              onClick={() => setMode(item.id)} className={`px-3 py-3 text-sm border-b-2 ${mode === item.id ? "border-nova-orange text-nova-orange" : "border-transparent text-text-secondary"}`}>{item.text}</button>)}
        </div>
        <div className="flex flex-wrap justify-between items-center gap-3 mb-4">
          <h2 className="font-display text-lg font-semibold">{mode === "repository" ? "Repo Reader / nova-desktop" : "NOVA research"}</h2>
          <div className="flex gap-2">
            <TaskAnnouncements message={announcement} identity={graph?.graph_id || ""} />
            <button className={toolStyle} disabled={!connected || pending} onClick={() => void command("status")} title="Ask NOVA for agent status" aria-label="Ask NOVA for agent status"><Activity size={16} /></button>
            <button className={toolStyle} disabled={!connected || pending} onClick={() => void command("results")} title="Ask NOVA for findings" aria-label="Ask NOVA for findings"><FileSearch size={16} /></button>
            <button className={`${toolStyle} !text-accent-red`} disabled={!ready || pending} onClick={() => stopDialog.current?.showModal()} title="Stop all agents" aria-label="Stop all agents"><Square size={15} /></button>
          </div>
        </div>
        {mode === "repository" && <div className="mb-4">
          <label htmlFor="repository-files" className="block text-xs text-text-secondary mb-2">Selected files (1-3 relative paths, one per line)</label>
          <textarea id="repository-files" aria-label="Selected repository files" value={repositoryFiles} disabled={pending}
            onChange={(event) => setRepositoryFiles(event.target.value)} maxLength={722} rows={3}
            className="block w-full resize-y min-h-20 px-3 py-2 bg-bg-secondary border border-border rounded-md text-sm font-mono" />
          <p className="text-xs text-text-secondary mt-2">Read-only / No shell / No file changes</p>
          {!readerReady && <p role="status" className="text-xs text-nova-amber mt-2">Repository reader unavailable in the connected runtime.</p>}
        </div>}
        <form className="flex gap-2" onSubmit={(event) => { event.preventDefault(); if (ready && !busy && !pending && topic.trim() && (mode !== "repository" || readerReady && validFiles)) void command("research"); }}>
          <input aria-label={mode === "repository" ? "Repository question" : "Research topic"} value={topic} onChange={(event) => setTopic(event.target.value)} maxLength={400} required placeholder={mode === "repository" ? "Review question" : "Research topic"} className="min-w-0 flex-1 h-11 px-3 bg-bg-secondary border border-border rounded-md text-sm focus:outline-none focus:border-nova-orange" />
          <button type="submit" disabled={!ready || busy || pending || !topic.trim() || mode === "repository" && (!readerReady || !validFiles)} className={`${toolStyle} !h-11 !w-11 !text-nova-orange`} title={mode === "repository" ? "Start repository review" : "Start read-only research"} aria-label={mode === "repository" ? "Start repository review" : "Start read-only research"}><ArrowUp size={18} /></button>
        </form>
        <p role="status" className="mt-4 text-sm text-text-secondary whitespace-pre-wrap break-words leading-relaxed">{reply || (mode === "repository" ? readerReady ? "Repo Reader is ready." : "Waiting for the scoped repository reader." : snapshot?.state === "READY" ? "Scout, Atlas and Prism are ready." : snapshot ? `Runtime ${label(snapshot.state)}${snapshot.reason_code ? `: ${snapshot.reason_code}` : "."}` : "Waiting for runtime status.")}</p>
      </section>
      <section aria-label="Runtime" className="py-4 border-b border-border flex flex-wrap gap-x-6 gap-y-2 text-xs text-text-secondary">
        <span>Runtime <strong className={outcomeColor(snapshot?.state || "UNKNOWN")}>{label(snapshot?.state || "UNKNOWN")}</strong></span>
        {snapshot?.agents.map((agent) => <span key={agent.id}>{label(agent.id)} / {agent.concurrency_limit} concurrent / {agent.capabilities.join(", ")}</span>)}
        {!!snapshot?.pending_runs && <span className="text-nova-amber">Research queued</span>}
      </section>
      <nav aria-label="Agent views" className="flex gap-4 border-b border-border">{["Reports", "Live activity"].map((item) => <button key={item} aria-pressed={view === item} onClick={() => setView(item)} className={`py-4 text-sm border-b-2 ${view === item ? "border-nova-orange text-nova-orange" : "border-transparent text-text-secondary"}`}>{item}</button>)}</nav>
      {view === "Reports" && <ResearchReports revision={revision} />}
      {view === "Live activity" && <section aria-label="Agent runs" className="py-6">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-5"><h2 className="font-display text-lg font-semibold">Runs <span className="text-text-secondary text-sm">{snapshot?.graphs.length ?? 0}</span></h2>
          {!!snapshot?.graphs.length && <select aria-label="Select run" value={graph?.graph_id || ""} onChange={(event) => setSelectedId(event.target.value)} className="min-w-0 max-w-full bg-bg-secondary border border-border rounded-md p-2 text-xs">{snapshot.graphs.map((item) => <option key={item.graph_id} value={item.graph_id}>{item.graph_id.slice(-10)} / {label(item.status)}</option>)}</select>}
        </div>
        {graph ? <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pb-5 text-xs text-text-secondary">
            <div>Tasks finished<strong className="block mt-2 text-xl text-text-primary">{graph.finished_tasks} / {graph.total_tasks}</strong></div>
            <div>Successful<strong className="block mt-2 text-xl text-accent-green">{graph.successful_tasks}</strong></div>
            <div>Elapsed<strong className="block mt-2 text-xl text-text-primary">{Math.floor(graph.elapsed_ms / 1000)}s</strong></div>
            <div>Outcome<strong className={`block mt-2 text-sm ${outcomeColor(graph.status)}`}>{label(graph.status)}</strong></div>
          </div>
          <progress aria-label="Tasks finished" max={100} value={graph.finished_percent ?? 0} className="w-full h-1.5 accent-nova-orange" />
          <div className="flex flex-wrap gap-3 my-5"><input aria-label="Find a task" placeholder="Find a task" value={search} onChange={(event) => setSearch(event.target.value)} className="min-w-0 flex-1 bg-bg-secondary border border-border rounded-md p-2 text-sm" /><select aria-label="Task filter" value={filter} onChange={(event) => setFilter(event.target.value)} className="bg-bg-secondary border border-border rounded-md p-2 text-sm"><option value="all">All tasks</option><option value="active">In progress</option><option value="issues">Needs attention</option></select></div>
          <div className="divide-y divide-border">{nodes.map((node) => <details key={node.id} className="py-4 text-sm">
            <summary className="cursor-pointer"><span className="inline-flex flex-wrap justify-between gap-2 w-[90%] align-top"><span className="break-all">{node.name}</span><span className={outcomeColor(node.state === "COMPLETED" ? node.result_status || node.state : node.state)}>{label(node.state === "COMPLETED" ? node.result_status || node.state : node.state)}</span></span></summary>
            <dl className="mt-3 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-xs text-text-secondary"><dt>Agent</dt><dd className="break-all">{node.agent}</dd><dt>Attempts</dt><dd>{node.attempts}</dd><dt>Depends on</dt><dd className="break-words">{node.depends_on.map((id) => graph.nodes.find((item) => item.id === id)?.name || id).join(", ") || "None"}</dd></dl>
          </details>)}</div>
          {!nodes.length && <p className="py-8 text-sm text-text-secondary">No matching tasks.</p>}
        </> : <div className="py-14 text-center text-text-secondary"><Workflow className="mx-auto mb-4 text-accent-blue" size={28} /><h3 className="font-display text-base text-text-primary">{snapshot?.pending_runs ? "Research queued" : "No recorded runs"}</h3></div>}
      </section>}
      <footer className="py-4 border-t border-border text-xs text-text-secondary">{snapshot ? `Last snapshot ${new Date(snapshot.observed_at).toLocaleTimeString()}` : "No snapshot received"}</footer>
    </div>
    <dialog ref={stopDialog} className="max-w-[calc(100%-32px)] w-96 p-6 rounded-lg border border-border bg-bg-secondary text-text-primary backdrop:bg-black/60">
      <h2 className="font-display text-lg font-semibold">Stop all agents?</h2><p className="mt-3 text-sm text-text-secondary">Active work will be cancelled. New runs stay blocked until the backend restarts.</p>
      <div className="flex flex-wrap justify-end gap-3 mt-6"><button className="px-3 py-2 text-sm" onClick={() => stopDialog.current?.close()}>Keep running</button><button className="px-3 py-2 text-sm border border-accent-red rounded-md text-accent-red" onClick={() => { stopDialog.current?.close(); void command("stop"); }}>Stop agents</button></div>
    </dialog>
  </div>;
}