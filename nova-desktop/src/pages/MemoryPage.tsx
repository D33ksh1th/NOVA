import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Brain, Plus, Search, RefreshCw, Pencil, Save, X, Database } from "lucide-react";
import { apiMemories, apiSaveMemory } from "@/services/api";

export function MemoryPage() {
  const [memories, setMemories] = useState<Record<string, unknown>>({});
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [editing, setEditing] = useState(false);
  const [key, setKey] = useState("");
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);
  const lock = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    let disposed = false;
    const timeout = setTimeout(() => controller.abort(), 8000);
    setLoading(true);
    apiMemories(controller.signal).then(data => {
      if (!data || Array.isArray(data) || typeof data !== "object") throw new Error("Invalid memory response");
      if (!disposed) { setMemories(data); setError(""); }
    }).catch(() => { if (!disposed) setError("Saved memory is unavailable. Check the backend connection."); })
      .finally(() => { clearTimeout(timeout); if (!disposed) setLoading(false); });
    return () => { disposed = true; controller.abort(); clearTimeout(timeout); };
  }, [revision]);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (lock.current || !key.trim() || !value.trim()) return;
    if (Object.prototype.hasOwnProperty.call(memories, key.trim()) && !window.confirm(`Replace the saved value for "${key.trim()}"?`)) return;
    lock.current = true; setSaving(true);
    try {
      await apiSaveMemory(key.trim(), value.trim());
      setEditing(false); setKey(""); setValue(""); setRevision(current => current + 1);
    } catch { setError("Memory was not confirmed saved. Your draft is still available."); }
    finally { lock.current = false; setSaving(false); }
  }
  const entries = Object.entries(memories).filter(([identity, content]) => `${identity} ${typeof content === "string" ? content : JSON.stringify(content)}`.toLowerCase().includes(query.toLowerCase()));
  return (
    <div className="flex flex-col h-full">
      <header className="px-5 sm:px-8 py-6 border-b border-border flex flex-wrap items-center justify-between gap-4"><div><p className="nova-panel-heading mb-2">Retained context</p><h1 className="flex items-center gap-3 text-2xl font-display"><Brain size={23} className="text-nova-orange" />Memory</h1></div><div className="flex gap-2"><button title="Refresh memory" aria-label="Refresh memory" onClick={() => setRevision(current => current + 1)} className="nova-quick-action"><RefreshCw size={16} /></button><button onClick={() => { setEditing(true); setKey(""); setValue(""); }} className="nova-quick-action"><Plus size={16} />Add memory</button></div></header>
      <div className="flex-1 min-h-0 overflow-y-auto px-5 sm:px-8 py-6">
        <div className="flex flex-wrap gap-4 justify-between items-center mb-6"><span className="text-sm text-text-secondary">{Object.keys(memories).length} saved entries</span><label className="flex items-center gap-2 border border-border rounded-md px-3 w-full sm:w-72"><Search size={15} className="text-text-muted shrink-0" /><input aria-label="Search memories" value={query} onChange={event => setQuery(event.target.value)} placeholder="Search memory" className="bg-transparent h-10 text-sm w-full min-w-0 outline-none" /></label></div>
        {error && <p role="alert" className="mb-5 text-sm text-nova-amber">{error}</p>}
        {editing && <form onSubmit={save} className="border-y border-border py-5 mb-6 space-y-3"><div className="flex items-center justify-between"><h2 className="text-lg">Memory entry</h2><button type="button" disabled={saving} title="Close memory editor" aria-label="Close memory editor" onClick={() => setEditing(false)} className="p-2 text-text-muted"><X size={17} /></button></div><input aria-label="Memory key" placeholder="Name" value={key} onChange={event => setKey(event.target.value)} required maxLength={200} className="block w-full bg-bg-secondary border border-border rounded-md px-3 py-2 text-sm" /><textarea aria-label="Memory value" placeholder="What should NOVA remember?" value={value} onChange={event => setValue(event.target.value)} required maxLength={8000} rows={4} className="block w-full bg-bg-secondary border border-border rounded-md px-3 py-2 text-sm resize-y" /><button disabled={saving || !key.trim() || !value.trim()} className="nova-quick-action disabled:opacity-40"><Save size={15} />{saving ? "Saving..." : "Save memory"}</button></form>}
        {loading ? <p className="py-12 text-text-muted text-sm">Loading saved memory...</p> : entries.length ? <div className="divide-y divide-border">{entries.map(([identity, content], index) => <motion.article initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(index * 0.04, 0.3) }} key={identity} className="py-5 grid sm:grid-cols-[180px_minmax(0,1fr)_36px] gap-3"><h2 className="text-sm text-nova-orange break-words">{identity}</h2><p className="text-sm text-text-secondary whitespace-pre-wrap break-words leading-6">{typeof content === "string" ? content : JSON.stringify(content, null, 2)}</p>{typeof content === "string" && <button title={`Edit ${identity}`} aria-label={`Edit ${identity}`} onClick={() => { setKey(identity); setValue(content); setEditing(true); }} className="h-8 w-8 grid place-items-center text-text-muted hover:text-nova-orange"><Pencil size={15} /></button>}</motion.article>)}</div> : !error && <div className="py-16 text-center"><Database size={30} strokeWidth={1.3} className="mx-auto mb-4 text-nova-orange" /><h2 className="text-xl font-display">{query ? "No matching memories" : "A little context goes a long way."}</h2><p className="text-sm text-text-muted mt-2">{query ? "No saved entry matches this search." : "No saved entries yet."}</p></div>}
      </div>
    </div>
  );
}
