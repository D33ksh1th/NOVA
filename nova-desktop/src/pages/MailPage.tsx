import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { clsx } from "clsx";
import { Loader2, Mail, RefreshCw, Send, ShieldCheck, X } from "lucide-react";
import { apiGmailInbox, apiGmailMarkRead, apiGmailMessage, apiGmailSend, apiGmailStatus } from "@/services/api";
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
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null);
  const [filter, setFilter] = useState<MailFilter>("all");
  const [query, setQuery] = useState("");
  const [markingId, setMarkingId] = useState<string | null>(null);

  const [to, setTo] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [sendStatus, setSendStatus] = useState<string>("");
  const loadInFlightRef = useRef(false);
  const [selectedMessage, setSelectedMessage] = useState<GmailMessage | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [showRawDetail, setShowRawDetail] = useState(false);

  function htmlToText(html: string): string {
    if (!html) return "";
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, "text/html");
    return (doc.body?.textContent || "").trim();
  }

  function dequoteLine(line: string): string {
    return String(line || "").replace(/^\s*>+\s?/, "").trimEnd();
  }

  function looksLikeDisclaimerStart(line: string): boolean {
    const low = line.trim().toLowerCase();
    return (
      low.startsWith("the information contained in this electronic communication") ||
      low.startsWith("this e-mail and any attachments") ||
      low.startsWith("this email and any attachments")
    );
  }

  function fallbackReadableFromRaw(raw: string): string {
    const lines = String(raw || "").replace(/\r\n/g, "\n").split("\n");
    const out: string[] = [];
    for (const line of lines) {
      const cleaned = dequoteLine(line).trim();
      if (!cleaned) {
        if (out.length > 0 && out[out.length - 1] !== "") out.push("");
        continue;
      }
      if (/^on .+wrote:\s*$/i.test(cleaned)) continue;
      if (/^(from|subject|to|date):\s+/i.test(cleaned)) continue;
      if (cleaned === "--" || cleaned === "---" || cleaned === "____") continue;
      if (looksLikeDisclaimerStart(cleaned)) break;
      out.push(cleaned);
      if (out.length >= 30) break;
    }
    return out.join("\n").replace(/\n{3,}/g, "\n\n").trim();
  }

  function extractPrimaryBody(raw: string): { text: string; trimmedQuoted: boolean } {
    const source = String(raw || "").replace(/\r\n/g, "\n").trim();
    if (!source) return { text: "", trimmedQuoted: false };

    const lines = source.split("\n");
    const out: string[] = [];
    let trimmedQuoted = false;

    for (const line of lines) {
      const current = line || "";
      const cleaned = dequoteLine(current);
      const low = cleaned.trim().toLowerCase();

      // Common reply/forward boundary markers.
      if (/^on .+wrote:\s*$/i.test(cleaned.trim())) {
        trimmedQuoted = true;
        break;
      }
      if (/^from:\s+/i.test(cleaned.trim()) && out.length > 0) {
        trimmedQuoted = true;
        break;
      }

      // Quoted lines from prior thread.
      if (current.trim().startsWith(">") && out.length > 0) {
        trimmedQuoted = true;
        break;
      }

      // Separator before quoted/disclaimer blocks in many enterprise emails.
      if ((low === "--" || low === "---" || low === "____") && out.length > 0) {
        trimmedQuoted = true;
        break;
      }

      if (looksLikeDisclaimerStart(cleaned)) {
        trimmedQuoted = true;
        break;
      }

      out.push(cleaned);
    }

    const cleaned = out.join("\n").replace(/\n{3,}/g, "\n\n").trim();
    const fallback = fallbackReadableFromRaw(source);
    return {
      text: cleaned || fallback || (trimmedQuoted ? "" : source),
      trimmedQuoted,
    };
  }

  async function openMessage(message: GmailMessage) {
    setSelectedMessage(message);
    setDetailError(null);
    setDetailLoading(true);
    setShowRawDetail(false);
    try {
      const res = await apiGmailMessage(message.id, true);
      if (!res.ok || !res.message) {
        throw new Error(res.error || "Failed to load full message");
      }
      setSelectedMessage((prev) => ({ ...(prev || message), ...res.message }));
    } catch (ex) {
      setDetailError(ex instanceof Error ? ex.message : "Failed to load full message");
    } finally {
      setDetailLoading(false);
    }
  }

  function closeMessage() {
    setSelectedMessage(null);
    setDetailError(null);
    setDetailLoading(false);
    setShowRawDetail(false);
  }

  const loadAll = useCallback(async () => {
    if (loadInFlightRef.current) return;
    loadInFlightRef.current = true;
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
      setLastSyncedAt(new Date().toISOString());
    } catch (ex) {
      setError(ex instanceof Error ? ex.message : "Failed to load Gmail data");
    } finally {
      setLoading(false);
      loadInFlightRef.current = false;
    }
  }, []);

  useEffect(() => {
    void loadAll();

    const onFocus = () => {
      void loadAll();
    };

    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        void loadAll();
      }
    };

    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void loadAll();
      }
    }, 20000);

    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [loadAll]);

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
          <p className="text-text-muted text-xs mt-2">
            Last sync: {lastSyncedAt ? new Date(lastSyncedAt).toLocaleString() : "Not synced yet"}
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
                className="rounded-xl border border-border bg-bg-card p-3 cursor-pointer hover:border-nova-orange/40 transition"
                onClick={() => void openMessage(m)}
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
                      onClick={(event) => {
                        event.stopPropagation();
                        void markRead(m.id);
                      }}
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

      {selectedMessage && (
        <div className="fixed inset-0 z-50 bg-black/55 backdrop-blur-[2px] flex items-center justify-center p-4" onClick={closeMessage}>
          <div className="w-full max-w-3xl max-h-[85vh] overflow-hidden rounded-2xl border border-border bg-bg-secondary shadow-2xl" onClick={(event) => event.stopPropagation()}>
            <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-border bg-bg-elevated">
              <div className="min-w-0">
                <p className="text-xs text-text-muted truncate">{selectedMessage.from}</p>
                <p className="text-sm font-semibold text-text-primary truncate">{selectedMessage.subject}</p>
              </div>
              <button
                type="button"
                onClick={closeMessage}
                className="inline-flex items-center justify-center rounded-lg border border-border bg-bg-card px-2 py-1 text-text-muted hover:text-text-primary"
                title="Close"
              >
                <X size={14} />
              </button>
            </div>

            <div className="p-4 space-y-3 overflow-auto max-h-[calc(85vh-64px)]">
              <div className="text-xs text-text-muted space-y-1">
                <p><span className="text-text-secondary">From:</span> {selectedMessage.from}</p>
                {!!selectedMessage.to && <p><span className="text-text-secondary">To:</span> {selectedMessage.to}</p>}
                {!!selectedMessage.date && <p><span className="text-text-secondary">Date:</span> {selectedMessage.date}</p>}
                {!!selectedMessage.thread_id && <p><span className="text-text-secondary">Thread:</span> {selectedMessage.thread_id}</p>}
              </div>

              {detailLoading && (
                <div className="rounded-xl border border-border bg-bg-card px-3 py-2 text-xs text-text-muted inline-flex items-center gap-2">
                  <Loader2 size={14} className="animate-spin" />
                  Loading full message...
                </div>
              )}

              {detailError && (
                <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">
                  {detailError}
                </div>
              )}

              <div className="rounded-xl border border-border bg-bg-card p-3">
                {(() => {
                  const rawBody =
                    selectedMessage.body_text ||
                    htmlToText(selectedMessage.body_html || "") ||
                    selectedMessage.snippet ||
                    "";
                  const parsed = extractPrimaryBody(rawBody);
                  const textToShow = showRawDetail ? rawBody : parsed.text;

                  return (
                    <>
                      <div className="flex items-center justify-between gap-2 mb-2">
                        <div className="flex items-center gap-2">
                          <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">Message</p>
                          <span className="text-[10px] px-2 py-0.5 rounded-full border border-border bg-bg-elevated text-text-muted">
                            {showRawDetail ? "Mode: Original" : "Mode: Cleaned"}
                          </span>
                        </div>
                        <button
                          type="button"
                          onClick={() => setShowRawDetail((v) => !v)}
                          className="text-[11px] px-2 py-1 rounded-lg border border-border bg-bg-elevated text-text-secondary hover:text-text-primary"
                        >
                          {showRawDetail ? "Switch to cleaned view" : "Switch to original view"}
                        </button>
                      </div>
                      <div className="whitespace-pre-wrap break-words text-sm text-text-primary leading-relaxed">
                        {textToShow || "No readable body found for this message."}
                      </div>
                      {!showRawDetail && parsed.trimmedQuoted && (
                        <p className="text-[11px] text-text-muted mt-3">Quoted previous-thread content is hidden. Click "Show full" to view entire raw message.</p>
                      )}
                    </>
                  );
                })()}
              </div>
            </div>
          </div>
        </div>
      )}
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
