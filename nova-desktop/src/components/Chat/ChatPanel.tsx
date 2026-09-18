import { memo, useRef, useEffect, useCallback, KeyboardEvent, useMemo, useState } from "react";
import { motion, AnimatePresence, useAnimationFrame } from "framer-motion";
import { Send, Mic, MicOff, Loader2, X, Bot, UserRound, AlertCircle, ArrowUpRight } from "lucide-react";
import { clsx } from "clsx";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useChatStore } from "@/stores/useChatStore";
import { useNovaChat } from "@/hooks/useNovaChat";
import { useAvatarStore } from "@/stores/useAvatarStore";
import { useAppStore } from "@/stores/useAppStore";
import { useSettingsStore } from "@/stores/useSettingsStore";
import type { ChatMessage } from "@/types";
import { OpenResearchReport } from "@/components/OpenResearchReport";

interface ChatPanelProps {
  showHistory?: boolean;
  showEmptyState?: boolean;
  helperText?: string;
}

export function ChatPanel({
  showHistory = true,
  showEmptyState = true,
  helperText = "",
}: ChatPanelProps) {
  const messages = useChatStore((s) => s.messages);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const inputValue = useChatStore((s) => s.inputValue);
  const setInputValue = useChatStore((s) => s.setInputValue);
  const avatarState = useAvatarStore((s) => s.state);
  const requestVoiceListening = useAppStore((s) => s.requestVoiceListening);
  const setStatus = useAppStore((s) => s.setStatus);
  const voiceEnabled = useSettingsStore((s) => s.voice.enabled);
  const setVoice = useSettingsStore((s) => s.setVoice);
  const logRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const { sendMessage, stopSpeaking } = useNovaChat();
  const [compactEmpty, setCompactEmpty] = useState(false);
  const [showNameModal, setShowNameModal] = useState(false);
  const [enrollmentName, setEnrollmentName] = useState("");
  const [messageHistory, setMessageHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState<number>(-1);
  const promptedEnrollmentMessageIdRef = useRef<string | null>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    if (!showHistory) return;
    if (!logRef.current) return;

    if (messages.length === 0) {
      // Keep empty-state panel fully visible at the top.
      logRef.current.scrollTop = 0;
      return;
    }

    logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [messages, showHistory]);

  // Auto-adjust empty state density based on available height.
  useEffect(() => {
    if (!showHistory) return;
    const el = logRef.current;
    if (!el) return;

    const update = () => {
      setCompactEmpty(el.clientHeight < 390);
    };

    update();

    const observer = new ResizeObserver(update);
    observer.observe(el);

    return () => {
      observer.disconnect();
    };
  }, [showHistory]);

  useEffect(() => {
    const last = messages[messages.length - 1];
    if (!last || last.role !== "nova" || !last.details) return;
    if (last.meta?.action !== "voice_enrollment") return;
    const stage = String((last.details as Record<string, unknown>).stage ?? "").toLowerCase();
    if (stage !== "await_name") return;
    if (promptedEnrollmentMessageIdRef.current === last.id) return;
    promptedEnrollmentMessageIdRef.current = last.id;
    setEnrollmentName("");
    setShowNameModal(true);
  }, [messages]);

  const handleSubmit = useCallback(async () => {
    const text = inputValue.trim();
    if (!text || isStreaming) return;
    
    // Add to history
    setMessageHistory((prev) => [...prev, text]);
    setHistoryIndex(-1);
    
    setInputValue("");
    await sendMessage(text);
    inputRef.current?.focus();
  }, [inputValue, isStreaming, setInputValue, sendMessage]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Handle Enter to submit
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
      return;
    }

    // Handle arrow keys for history
    if (e.key === "ArrowUp") {
      e.preventDefault();
      const nextIndex = Math.min(historyIndex + 1, messageHistory.length - 1);
      if (nextIndex >= 0 && nextIndex < messageHistory.length) {
        setHistoryIndex(nextIndex);
        setInputValue(messageHistory[messageHistory.length - 1 - nextIndex]);
      }
      return;
    }

    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (historyIndex > 0) {
        const nextIndex = historyIndex - 1;
        setHistoryIndex(nextIndex);
        setInputValue(messageHistory[messageHistory.length - 1 - nextIndex]);
      } else if (historyIndex === 0) {
        setHistoryIndex(-1);
        setInputValue("");
      }
      return;
    }
  };

  const isListening = avatarState === "listening";

  const submitEnrollmentName = useCallback(async () => {
    const name = enrollmentName.trim();
    if (!name || isStreaming) return;
    setShowNameModal(false);
    setEnrollmentName("");
    await sendMessage(name);
    inputRef.current?.focus();
  }, [enrollmentName, isStreaming, sendMessage]);

  return (
    <div className="flex flex-col h-full relative">
      {/* Message log */}
      {showHistory && (
        <div
          ref={logRef}
          className="flex-1 min-h-0 overflow-y-auto px-4 sm:px-8 py-6 space-y-6 scroll-smooth"
        >
          <AnimatePresence initial={false}>
            {showEmptyState && messages.length === 0 && (
              <ChatEmptyState
                compact={compactEmpty}
                onPrompt={(text) => {
                  setInputValue(text);
                  inputRef.current?.focus();
                }}
              />
            )}

            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
          </AnimatePresence>
        </div>
      )}

      {/* Composer */}
      <div className="p-4 sm:px-8 sm:pb-6 pt-3">
        <div
          className={clsx(
            "flex items-end gap-2 sm:gap-3 bg-bg-secondary rounded-lg border transition-all duration-200 px-3 sm:px-4 py-3",
            isListening
              ? "border-accent-green shadow-[0_0_0_2px_rgba(16,185,129,0.2)]"
              : "border-border focus-within:border-nova-orange/50 focus-within:shadow-[0_0_0_3px_rgba(137,229,179,0.06)]"
          )}
        >
          <textarea
            ref={inputRef}
            aria-label="Message NOVA"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isStreaming}
            rows={1}
            placeholder={
              isListening ? "Listening..." : "Message NOVA..."
            }
            className={clsx(
              "flex-1 min-w-0 bg-transparent resize-none outline-none",
              "text-text-primary text-[14px] placeholder:text-text-muted",
              "max-h-32 min-h-[24px] leading-6",
              "disabled:opacity-50 disabled:cursor-not-allowed"
            )}
            style={{ height: "auto" }}
            onInput={(e) => {
              const el = e.currentTarget;
              el.style.height = "auto";
              el.style.height = `${el.scrollHeight}px`;
            }}
          />

          {/* Mic toggle */}
          <button
            type="button"
            onClick={async () => {
              // Ensure voice is enabled
              if (!voiceEnabled) {
                setVoice({ enabled: true, handsFreeWake: true });
              }
              // Request mic with user gesture to force Chrome permission prompt
              try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                stream.getTracks().forEach((t) => t.stop());
                setStatus({ micPermission: "granted" });
                // Now trigger the voice pipeline
                requestVoiceListening();
              } catch (err) {
                console.error("[chat-mic] Permission denied:", err);
                setStatus({ micPermission: "denied" });
                alert(
                  "Microphone is blocked by your browser.\n\n" +
                  "To fix: Click the lock/tune icon in the address bar → " +
                  "Site settings → Microphone → Allow → Reload the page."
                );
              }
            }}
            className={clsx(
              "flex-shrink-0 p-1.5 rounded-lg transition-all duration-150",
              isListening
                ? "text-accent-green bg-accent-green/10 animate-pulse-glow"
                : "text-text-muted hover:text-text-primary hover:bg-bg-elevated"
            )}
            title="Push to talk"
          >
            {isListening ? <MicOff size={18} /> : <Mic size={18} />}
          </button>

          {/* Stop speaking button */}
          {avatarState === "speaking" && (
            <button
              type="button"
              onClick={() => stopSpeaking()}
              className={clsx(
                "flex-shrink-0 p-1.5 rounded-lg transition-all duration-150",
                "text-accent-red bg-accent-red/10 hover:bg-accent-red/20"
              )}
              title="Stop speaking"
            >
              <X size={18} />
            </button>
          )}

          {/* Send / stop */}
          <button
            type="button"
            onClick={isStreaming ? undefined : handleSubmit}
            aria-label={isStreaming ? "Waiting for response" : "Send message"}
            title={isStreaming ? "Waiting for response" : "Send message"}
            disabled={!inputValue.trim() && !isStreaming}
            className={clsx(
              "flex-shrink-0 flex items-center justify-center w-9 h-9 rounded-md transition-all duration-150",
              isStreaming
                ? "bg-accent-red/20 text-accent-red cursor-not-allowed"
                : "bg-nova-orange hover:bg-nova-glow text-white disabled:opacity-30 disabled:cursor-not-allowed",
              "shadow-glow-sm"
            )}
          >
            {isStreaming ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Send size={16} />
            )}
          </button>
        </div>

        {helperText && <p className="text-text-muted text-[11px] mt-2 text-center">{helperText}</p>}
      </div>

      <AnimatePresence>
        {showNameModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-black/50 backdrop-blur-[3px] flex items-start justify-center pt-24 px-4"
          >
            <motion.div
              initial={{ opacity: 0, y: -20, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -20, scale: 0.98 }}
              transition={{ duration: 0.16 }}
              className="w-full max-w-md rounded-2xl border border-border bg-bg-card p-4 shadow-2xl"
            >
              <p className="text-[11px] font-mono uppercase tracking-[0.18em] text-nova-orange mb-2">
                Voice Enrollment
              </p>
              <h3 className="text-text-primary font-semibold text-lg mb-1">
                Type The Person Name
              </h3>
              <p className="text-[12px] text-text-muted mb-3">
                Enter the name you want NOVA to recognize, then enrollment questions will continue.
              </p>

              <input
                autoFocus
                value={enrollmentName}
                onChange={(e) => setEnrollmentName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void submitEnrollmentName();
                  }
                }}
                placeholder="Deekshith"
                className="w-full rounded-xl border border-border bg-bg-elevated px-3 py-2 text-[14px] text-text-primary outline-none focus:border-nova-orange/40"
              />

              <div className="mt-3 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowNameModal(false)}
                  className="px-3 py-1.5 rounded-lg border border-border text-[12px] text-text-muted hover:text-text-primary hover:bg-bg-elevated"
                >
                  Later
                </button>
                <button
                  type="button"
                  onClick={() => void submitEnrollmentName()}
                  disabled={!enrollmentName.trim() || isStreaming}
                  className="px-3 py-1.5 rounded-lg bg-nova-orange text-white text-[12px] font-semibold disabled:opacity-40"
                >
                  Continue
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ── Message Bubble ────────────────────────────────────────────────
const MessageBubble = memo(function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const isError = message.role === "error";
  const isSystem = message.role === "system";
  const reportId = !isUser && message.meta?.intent === "agent_runtime" && typeof message.details?.report_id === "string" ? message.details.report_id : null;
  const renderedContent = useMemo(() => formatDialogContent(message), [message.content, message.details, message.role]);
  const renderStructuredDetails = Boolean(message.details && !message.streaming && !hasBluetoothPayload(message.details));

  if (isSystem) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex justify-center"
      >
        <span className="text-text-muted text-[12px] bg-bg-elevated border border-border rounded-full px-3 py-1">
          {message.content}
        </span>
      </motion.div>
    );
  }

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
      className={clsx("flex gap-3", isUser ? "flex-row-reverse" : "flex-row")}
    >
      {/* Avatar icon */}
      <div
        className={clsx(
          "flex-shrink-0 w-8 h-8 rounded-md flex items-center justify-center text-base border",
          isUser
            ? "bg-accent-blue/10 border-accent-blue/25 text-accent-blue"
            : "bg-nova-orange/15 border-nova-orange/30"
        )}
      >
        {isUser ? <UserRound size={16} /> : isError ? <AlertCircle size={16} /> : <Bot size={17} className="text-nova-orange" />}
      </div>

      {/* Bubble */}
      <div
        className={clsx(
          "min-w-0 max-w-[calc(100%-44px)] sm:max-w-[85%] rounded-lg px-4 py-3 border",
          isUser
            ? "bg-accent-blue/10 border-accent-blue/20 text-text-primary"
            : isError
            ? "rounded-tl-md bg-accent-red/10 border-accent-red/25 text-accent-red"
            : "bg-transparent border-transparent text-text-primary"
        )}
      >
        <p className="text-[11px] font-bold uppercase tracking-wider text-text-muted mb-1">
          {isUser ? "You" : isError ? "Error" : "NOVA"}
        </p>

        {message.streaming && !message.content ? (
          <div className="flex gap-1.5 items-center h-5">
            {[0, 1, 2].map((i) => (
              <motion.span
                key={i}
                className="w-1 h-3 rounded-full bg-nova-orange"
                animate={{ scaleY: [1, 2.2, 1], opacity: [0.4, 1, 0.4] }}
                transition={{ duration: 0.7, repeat: Infinity, delay: i * 0.15, ease: "easeInOut" }}
              />
            ))}
          </div>
        ) : (
          <div className="prose prose-invert prose-sm max-w-none text-[13.5px] leading-relaxed break-words prose-ul:list-disc prose-ul:pl-5 prose-ol:list-decimal prose-ol:pl-5 prose-li:my-1">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {renderedContent}
            </ReactMarkdown>
          </div>
        )}

        {reportId && !message.streaming && <OpenResearchReport identity={reportId} />}
        {renderStructuredDetails && !reportId && (
          <StructuredDetails details={message.details as Record<string, unknown>} />
        )}

        {/* Meta */}
        {message.meta && Object.keys(message.meta).length > 0 && !message.streaming && (
          <div className="flex flex-wrap gap-1.5 mt-2 pt-2 border-t border-border/50">
            {Object.entries(message.meta)
              .filter(([, v]) => v)
              .map(([k, v]) => (
                <span
                  key={k}
                  className="text-[10px] text-text-muted bg-bg-elevated rounded-md px-1.5 py-0.5"
                >
                  {k}: {v as string}
                </span>
              ))}
          </div>
        )}
      </div>
    </motion.div>
  );
});

function hasBluetoothPayload(details?: Record<string, unknown>): boolean {
  if (!details) return false;
  return Boolean(details.bluetooth) || Array.isArray(details.nearby_scan);
}

function toDeviceNames(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => {
      const dev = item as Record<string, unknown>;
      return String(dev.name ?? dev.id ?? "").trim();
    })
    .filter(Boolean);
}

function buildBluetoothMarkdown(details?: Record<string, unknown>): string | null {
  if (!details) return null;

  const bluetooth = (details.bluetooth as Record<string, unknown> | undefined) ?? undefined;
  const nearby = toDeviceNames(details.nearby_scan);
  if (!bluetooth && nearby.length === 0) return null;

  const connected = bluetooth
    ? toDeviceNames((bluetooth as Record<string, unknown>).connected_devices)
    : [];
  const saved = bluetooth
    ? toDeviceNames((bluetooth as Record<string, unknown>).paired_not_connected)
    : [];

  const sections: string[] = [];

  sections.push("Connected Devices:");
  if (connected.length === 0) {
    sections.push("- None");
  } else {
    sections.push(...connected.map((name) => `- ${name}`));
  }

  sections.push("\nPaired Devices:");
  if (saved.length === 0) {
    sections.push("- None");
  } else {
    sections.push(...saved.map((name) => `- ${name}`));
  }

  if (nearby.length > 0) {
    sections.push("\nNearby Devices:");
    sections.push(...nearby.map((name) => `- ${name}`));
  }

  return sections.join("\n");
}

function normalizeInlineDeviceList(text: string): string {
  if (!text.trim()) return text;
  if (/^\s*[-*]\s+/m.test(text)) return text;

  const extractItems = (value: string) =>
    value
      .split(/[,;|]/)
      .map((s) => s.trim())
      .filter((s) => s.length > 0 && !/^none$/i.test(s));

  const connectedMatch = text.match(/connected\s+devices?\s*[:\-]\s*([^\n.]+)/i);
  const pairedMatch = text.match(/(?:paired|saved)\s+devices?\s*[:\-]\s*([^\n.]+)/i);
  const availableMatch = text.match(/available\s+devices?\s*[:\-]\s*([^\n.]+)/i);

  if (!connectedMatch && !pairedMatch && !availableMatch) return text;

  const connected = connectedMatch ? extractItems(connectedMatch[1]) : [];
  const paired = pairedMatch ? extractItems(pairedMatch[1]) : [];
  const available = availableMatch ? extractItems(availableMatch[1]) : [];

  const intro = text
    .split(/connected\s+devices?|paired\s+devices?|saved\s+devices?|available\s+devices?/i)[0]
    .trim();

  const lines: string[] = [];
  if (intro) lines.push(intro);

  if (connectedMatch || connected.length > 0) {
    lines.push("\nConnected Devices:");
    lines.push(...(connected.length > 0 ? connected.map((name) => `- ${name}`) : ["- None"]));
  }
  if (pairedMatch || paired.length > 0) {
    lines.push("\nPaired Devices:");
    lines.push(...(paired.length > 0 ? paired.map((name) => `- ${name}`) : ["- None"]));
  }
  if (availableMatch || available.length > 0) {
    lines.push("\nAvailable Devices:");
    lines.push(...(available.length > 0 ? available.map((name) => `- ${name}`) : ["- None"]));
  }

  return lines.join("\n").trim();
}

function prettifyDeviceNarrative(text: string): string {
  const lower = text.toLowerCase();
  const isDeviceNarrative =
    lower.includes("bluetooth") ||
    lower.includes("device") ||
    lower.includes("saved devices") ||
    lower.includes("connected devices") ||
    lower.includes("nearby scan") ||
    lower.includes("pair/connect") ||
    lower.includes("system status") ||
    lower.includes("battery") ||
    lower.includes("power") ||
    lower.includes("wifi") ||
    lower.includes("wi-fi") ||
    lower.includes("network");

  if (!isDeviceNarrative) return text;

  let formatted = text.trim();

  formatted = formatted.replace(/:\s*-\s+/g, ":\n- ");
  formatted = formatted.replace(/\)\s*-\s+/g, ")\n- ");
  formatted = formatted.replace(/-\s+None\s+(Paired\s+Not\s+Connected\s*\(\d+\):)/gi, "- None\n\n$1");
  formatted = formatted.replace(/-\s+None\s+(Saved\s+Devices\s+You\s+Can\s+Connect\s*\(\d+\):)/gi, "- None\n\n$1");
  formatted = formatted.replace(/-\s+None\s+(Nearby\s+Scan\s+Results\s*\(\d+\):)/gi, "- None\n\n$1");

  const sectionLabels = [
    /Devices Available For Pairing/gi,
    /Bluetooth Status/gi,
    /System Status/gi,
    /Network Status/gi,
    /Power Status/gi,
    /Controller State\s*:\s*/gi,
    /Discoverable\s*:\s*/gi,
    /Controller Addr\s*:\s*/gi,
    /Battery\s*(?:Level|Status)?\s*:\s*/gi,
    /Power Source\s*:\s*/gi,
    /Wi-?Fi\s*:\s*/gi,
    /SSID\s*:\s*/gi,
    /Connected Devices\s*\(\d+\):/gi,
    /Paired Not Connected\s*\(\d+\):/gi,
    /Saved Devices You Can Connect\s*\(\d+\):/gi,
    /Nearby Scan Results\s*\(\d+\):/gi,
    /Paired Devices\s*\(\d+\):/gi,
    /Pairing Readiness\s*:/gi,
    /To pair\/connect, say:/gi,
  ];

  for (const label of sectionLabels) {
    formatted = formatted.replace(label, (match) => `\n\n${match}`);
  }

  // Convert key-value info lines to bullets for better readability.
  formatted = formatted
    .split(/\n+/)
    .map((line) => {
      const trimmed = line.trim();
      if (!trimmed) return "";
      if (/^[A-Za-z][A-Za-z0-9\s\/-]{2,40}:\s+/.test(trimmed) && !trimmed.startsWith("- ")) {
        return `- ${trimmed}`;
      }
      return trimmed;
    })
    .filter(Boolean)
    .join("\n");

  formatted = formatted.replace(/\n{3,}/g, "\n\n").trim();
  return formatted;
}

function formatDialogContent(message: ChatMessage): string {
  const base = (message.content ?? "").trim();
  if (message.role !== "nova") return base;

  const bluetoothMarkdown = buildBluetoothMarkdown(message.details as Record<string, unknown> | undefined);
  if (bluetoothMarkdown) {
    if (!base) return bluetoothMarkdown;
    return `${prettifyDeviceNarrative(base)}\n\n${bluetoothMarkdown}`;
  }

  return prettifyDeviceNarrative(normalizeInlineDeviceList(base));
}

function StructuredDetails({ details }: { details: Record<string, unknown> }) {
  const bluetooth = (details.bluetooth as Record<string, unknown> | undefined) ?? undefined;
  const nearbyScan = Array.isArray(details.nearby_scan) ? details.nearby_scan : [];

  // Nova Status card
  if (details.type === "nova_status") {
    return <NovaStatusCard details={details} />;
  }

  if (bluetooth) {
    const connected = Array.isArray(bluetooth.connected_devices) ? bluetooth.connected_devices as Array<Record<string, unknown>> : [];
    const saved = Array.isArray(bluetooth.paired_not_connected) ? bluetooth.paired_not_connected as Array<Record<string, unknown>> : [];
    const controller = (bluetooth.controller as Record<string, unknown> | undefined) ?? {};

    return (
      <div className="mt-3 rounded-xl border border-border bg-bg-elevated/70 p-3">
        <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-text-muted mb-2">Detailed Output</p>
        <div className="space-y-2 text-[12px] text-text-primary">
          <p>
            Bluetooth Power: <span className="text-accent-green">{String(controller.power ?? "unknown")}</span>
          </p>
          <p>Connected Devices ({connected.length}):</p>
          <ul className="list-disc pl-5 space-y-1 text-text-secondary">
            {(connected.length > 0 ? connected : [{ name: "None", connected: false }]).map((d, idx) => (
              <li key={`${String(d.id ?? d.name ?? idx)}-${idx}`}>
                {String(d.name ?? d.id ?? "Unknown device")}
              </li>
            ))}
          </ul>
          <p>Saved Devices ({saved.length}):</p>
          <ul className="list-disc pl-5 space-y-1 text-text-secondary">
            {(saved.length > 0 ? saved : [{ name: "None" }]).map((d, idx) => (
              <li key={`${String(d.id ?? d.name ?? idx)}-${idx}`}>
                {String(d.name ?? d.id ?? "Unknown device")}
              </li>
            ))}
          </ul>
          {nearbyScan.length > 0 && (
            <>
              <p>Nearby Scan ({nearbyScan.length}):</p>
              <ul className="list-disc pl-5 space-y-1 text-text-secondary">
                {nearbyScan.map((d, idx) => {
                  const dev = d as Record<string, unknown>;
                  return <li key={`${String(dev.id ?? dev.name ?? idx)}-${idx}`}>{String(dev.name ?? dev.id ?? "Unknown device")}</li>;
                })}
              </ul>
            </>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="mt-3 rounded-xl border border-border bg-bg-elevated/70 p-3">
      <p className="text-[10px] font-mono uppercase tracking-[0.18em] text-text-muted mb-2">Detailed Output</p>
      <pre className="text-[11px] leading-5 text-text-secondary overflow-x-auto whitespace-pre-wrap">
        {JSON.stringify(details, null, 2)}
      </pre>
    </div>
  );
}

const QUICK_PROMPTS = [
  "Summarize my current project status",
  "Plan my next 3 development tasks",
  "Debug why my backend is failing startup",
  "Create a clean implementation roadmap",
];

/* ── Nova Status Card ─────────────────────────────────── */

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span
      className="inline-block w-2 h-2 rounded-full"
      style={{
        background: ok ? "#34d399" : "#ef4444",
        boxShadow: ok ? "0 0 6px #34d399" : "0 0 6px #ef4444",
      }}
    />
  );
}

function NovaStatusCard({ details }: { details: Record<string, unknown> }) {
  const allOk = Boolean(details.all_ok);
  const issues = (details.issues as string[]) ?? [];
  const services = (details.services as Record<string, Record<string, unknown>>) ?? {};

  const statusColor = (s: unknown) => {
    const v = String(s ?? "").toLowerCase();
    if (v === "online" || v === "enabled") return "#34d399";
    if (v === "disabled") return "#fbbf24";
    return "#ef4444";
  };

  return (
    <div className="mt-3 rounded-xl border border-white/[0.06] bg-white/[0.03] p-3 backdrop-blur-sm">
      <div className="flex items-center gap-2 mb-3">
        <StatusDot ok={allOk} />
        <span className="text-[10px] font-mono uppercase tracking-[0.2em]" style={{ color: allOk ? "#34d399" : "#ef4444" }}>
          {allOk ? "ALL SYSTEMS OPERATIONAL" : `${issues.length} ISSUE(S) DETECTED`}
        </span>
      </div>

      {issues.length > 0 && (
        <div className="mb-3 p-2 rounded-lg bg-red-500/10 border border-red-500/20">
          {issues.map((issue, i) => (
            <p key={i} className="text-[11px] text-red-300">⚠ {issue}</p>
          ))}
        </div>
      )}

      <div className="grid grid-cols-2 gap-2">
        {Object.entries(services).map(([key, svc]) => {
          const status = String(svc.status ?? "unknown");
          const color = statusColor(status);
          const extra = Object.entries(svc).filter(([k]) => k !== "status").slice(0, 3);

          return (
            <div key={key} className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-2">
              <div className="flex items-center gap-1.5 mb-1">
                <span className="w-1.5 h-1.5 rounded-full" style={{ background: color, boxShadow: `0 0 4px ${color}` }} />
                <span className="text-[10px] font-mono uppercase tracking-wider text-white/50">{key}</span>
                <span className="ml-auto text-[9px] font-mono uppercase" style={{ color }}>{status}</span>
              </div>
              {extra.map(([k, v]) => (
                <p key={k} className="text-[10px] text-white/30 truncate">
                  {k.replace(/_/g, " ")}: <span className="text-white/50">{Array.isArray(v) ? v.join(", ") : String(v)}</span>
                </p>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ChatEmptyState({
  compact,
  onPrompt,
}: {
  compact: boolean;
  onPrompt: (text: string) => void;
}) {
  const shownPrompts = compact ? QUICK_PROMPTS.slice(0, 2) : QUICK_PROMPTS;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4 }}
      className={`flex flex-col items-center justify-center h-full relative overflow-hidden select-none ${
        compact ? "gap-3 py-2" : "gap-5 py-3"
      }`}
    >
      <div className="w-full max-w-xl text-center">
        <Bot size={32} strokeWidth={1.3} className="mx-auto mb-5 text-nova-orange" />
        <p className="nova-panel-heading mb-3">NOVA / Conversation</p>
        <h3 className={`${compact ? "text-2xl" : "text-3xl"} font-display font-medium text-text-primary`}>What's on your mind?</h3>
      </div>

      <div className={`w-full max-w-xl ${compact ? "space-y-1.5" : "space-y-2"}`}>
        <div className="grid sm:grid-cols-2 gap-2 mt-3">
          {shownPrompts.map((prompt, i) => (
            <motion.button
              key={prompt}
              type="button"
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 + i * 0.06 }}
              onClick={() => onPrompt(prompt)}
              className="flex items-center justify-between gap-3 text-left text-sm px-4 py-3 rounded-md border border-border text-text-secondary hover:text-nova-orange hover:border-nova-orange/30 transition-colors"
            >
              {prompt}
              <ArrowUpRight size={14} className="shrink-0" />
            </motion.button>
          ))}
        </div>
      </div>

    </motion.div>
  );
}
