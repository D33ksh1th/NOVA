import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { clsx } from "clsx";
import { Loader2, Mail, RefreshCw, Send, ShieldCheck } from "lucide-react";
import { apiGmailInbox, apiGmailMarkRead, apiGmailSend, apiGmailStatus } from "@/services/api";
import type { GmailMessage, GmailUrgency } from "@/types";

type MailFilter = "all" | GmailUrgency;

const URGENCY_ORDER: Record<GmailUrgency, number> = {
  critical: 0,
  high: 1,
  normal: 2,
  low: 3,
};

export function MailPage() {
  const [status, setStatus] = useState<{
    enabled: boolean;
    authenticated: boolean;
    credentials_present: boolean;
    poll_interval: number;
  } | null>(null);
  const [messages, setMessages] = useState<GmailMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<MailFilter>("all");
  const [query, setQuery] = useState("");
  const [markingId, setMarkingId] = useState<string | null>(null);

  const [to, setTo] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [sendStatus, setSendStatus] = useState<string>("");

  async function loadAll() {
    setLoading(true);
    setError(null);
    try {
      const [s, inbox] = await Promise.all([apiGmailStatus(), apiGmailInbox(30)]);
      setStatus(s);
      const sorted = [...(inbox.messages || [])].sort((a, b) => {
        const urgencyCmp = URGENCY_ORDER[a.urgency] - URGENCY_ORDER[b.urgency];
        if (urgencyCmp !== 0) return urgencyCmp;
        return new Date(b.date || "").getTime() - new Date(a.date || "").getTime();
      });
      setMessages(sorted);
    } catch (ex) {
      setError(ex instanceof Error ? ex.message : "Failed to load Gmail data");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  const visible = useMemo(() => {
    return messages.filter((m) => {
      if (filter !== "all" && m.urgency !== filter) return false;
      if (!query.trim()) return true;
      const q = query.toLowerCase();
      return (
        m.from.toLowerCase().includes(q) ||
        m.subject.toLowerCase().includes(q) ||
        (m.snippet || "").toLowerCase().includes(q)
      );
    });
  }, [messages, filter, query]);

  async function markRead(messageId: string) {
    setMarkingId(messageId);
    try {
      await apiGmailMarkRead(messageId);
      setMessages((prev) => prev.filter((m) => m.id !== messageId));
    } finally {
      setMarkingId(null);
    }
  }

  async function sendMail() {
    if (!to.trim() || !subject.trim() || !body.trim()) {
      setSendStatus("Please fill To, Subject, and Body.");
      return;
    }
    setSending(true);
    setSendStatus("");
    try {
      const res = await apiGmailSend({ to, subject, body });
      if (res.success) {
        setSendStatus("Mail sent successfully.");
        setTo("");
        setSubject("");
        setBody("");
      } else {
        setSendStatus(res.error || "Failed to send mail");
      }
    } catch (ex) {
      setSendStatus(ex instanceof Error ? ex.message : "Failed to send mail");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[11px] font-mono font-bold uppercase tracking-[0.2em] text-[#38bdf8]">
            Mail Command Center
          </p>
          <h2 className="font-display text-2xl font-bold text-text-primary mt-1">Inbox + Dispatch</h2>
          <p className="text-text-muted text-sm mt-1">
            Monitor unread messages, prioritize by urgency, and send replies from NOVA.
          </p>
        </div>
        <button
          onClick={loadAll}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-semibold border border-border bg-bg-elevated hover:bg-bg-card transition"
        >
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Card className="xl:col-span-2">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-text-primary font-semibold">
              <Mail size={16} /> Inbox
            </div>
            {status && (
              <div className="text-xs text-text-muted">
                Poll interval: {status.poll_interval}s
              </div>
            )}
          </div>

          {status && (
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
              <Pill ok={status.enabled} label={status.enabled ? "Monitor enabled" : "Monitor disabled"} />
              <Pill ok={status.authenticated} label={status.authenticated ? "Authenticated" : "Not authenticated"} />
              <Pill ok={status.credentials_present} label={status.credentials_present ? "Credentials found" : "Credentials missing"} />
            </div>
          )}

          <div className="mt-4 flex flex-wrap gap-2">
            {(["all", "critical", "high", "normal", "low"] as MailFilter[]).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={clsx(
                  "px-3 py-1.5 rounded-full text-xs font-semibold border transition",
                  filter === f
                    ? "bg-nova-orange/20 border-nova-orange/40 text-nova-orange"
                    : "bg-bg-elevated border-border text-text-muted hover:text-text-primary"
                )}
              >
                {f.toUpperCase()}
              </button>
            ))}
            <input
              className="ml-auto min-w-[220px] bg-bg-elevated border border-border rounded-lg px-3 py-1.5 text-xs text-text-primary"
              placeholder="Search sender / subject"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>

          <div className="mt-4 space-y-3 max-h-[560px] overflow-auto pr-1">
            {loading && <RowInfo text="Loading inbox..." icon={<Loader2 size={14} className="animate-spin" />} />}
            {!loading && error && <RowInfo text={error} icon={<span>⚠️</span>} />}
            {!loading && !error && visible.length === 0 && (
              <RowInfo text="No messages for this filter." icon={<span>📭</span>} />
            )}

            {!loading && !error && visible.map((m) => (
              <motion.div
                key={m.id}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                className="rounded-xl border border-border bg-bg-card p-3"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-xs text-text-muted truncate">{m.from}</p>
                    <p className="text-sm font-semibold text-text-primary mt-0.5 truncate">{m.subject}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={clsx(
                      "text-[11px] px-2 py-1 rounded-full font-semibold",
                      m.urgency === "critical" && "bg-red-500/15 text-red-300",
                      m.urgency === "high" && "bg-amber-500/15 text-amber-300",
                      m.urgency === "normal" && "bg-sky-500/15 text-sky-300",
                      m.urgency === "low" && "bg-zinc-500/15 text-zinc-300"
                    )}>
                      {m.urgency_emoji} {m.urgency}
                    </span>
                    <button
                      onClick={() => markRead(m.id)}
                      disabled={markingId === m.id}
                      className="text-[11px] px-2 py-1 rounded-lg border border-border bg-bg-elevated hover:bg-bg transition"
                    >
                      {markingId === m.id ? "..." : "Mark read"}
                    </button>
                  </div>
                </div>
                {!!m.snippet && <p className="text-xs text-text-muted mt-2 line-clamp-2">{m.snippet}</p>}
                <p className="text-[11px] text-text-muted mt-2">{m.date || ""}</p>
              </motion.div>
            ))}
          </div>
        </Card>

        <Card>
          <div className="flex items-center gap-2 text-text-primary font-semibold">
            <Send size={16} /> Quick Compose
          </div>
          <div className="mt-3 space-y-2">
            <input
              className="w-full bg-bg-elevated border border-border rounded-lg px-3 py-2 text-sm"
              placeholder="To"
              value={to}
              onChange={(e) => setTo(e.target.value)}
            />
            <input
              className="w-full bg-bg-elevated border border-border rounded-lg px-3 py-2 text-sm"
              placeholder="Subject"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
            />
            <textarea
              className="w-full bg-bg-elevated border border-border rounded-lg px-3 py-2 text-sm min-h-[180px]"
              placeholder="Body"
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
            <button
              onClick={sendMail}
              disabled={sending}
              className="w-full inline-flex items-center justify-center gap-2 px-3 py-2 rounded-xl text-sm font-semibold bg-nova-orange text-white hover:bg-nova-glow transition disabled:opacity-60"
            >
              {sending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
              {sending ? "Sending..." : "Send Mail"}
            </button>
            {!!sendStatus && (
              <p className="text-xs text-text-muted">{sendStatus}</p>
            )}
          </div>

          <div className="mt-4 rounded-xl border border-border bg-bg-elevated p-3 text-xs text-text-muted">
            <p className="font-semibold text-text-primary inline-flex items-center gap-1">
              <ShieldCheck size={13} /> Important
            </p>
            <ul className="mt-2 space-y-1">
              <li>Sent mail appears in Gmail Sent folder.</li>
              <li>Notifications fire for new unread mail while UI + backend are running.</li>
              <li>Alert level is controlled in Settings {">"} System {">"} Gmail Integration.</li>
            </ul>
          </div>
        </Card>
      </div>
    </div>
  );
}

function Card({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div className={clsx("rounded-2xl border border-border bg-bg-secondary p-4", className)}>
      {children}
    </div>
  );
}

function Pill({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={clsx(
        "px-2.5 py-1 rounded-full border text-[11px] font-semibold",
        ok
          ? "bg-accent-green/15 text-accent-green border-accent-green/30"
          : "bg-red-500/15 text-red-300 border-red-500/30"
      )}
    >
      {label}
    </span>
  );
}

function RowInfo({ text, icon }: { text: string; icon: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-border bg-bg-card px-3 py-2 text-xs text-text-muted inline-flex items-center gap-2">
      {icon}
      {text}
    </div>
  );
}
