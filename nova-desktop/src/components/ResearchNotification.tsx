import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { apiResearchReports, apiVoiceSpeak, type ResearchReportSummary } from "@/services/api";
import { useChatStore } from "@/stores/useChatStore";
import { useSettingsStore } from "@/stores/useSettingsStore";
import { useAvatarStore } from "@/stores/useAvatarStore";
import { OpenResearchReport } from "./OpenResearchReport";

const outcomes: Record<string, string> = {
  COMPLETED: "Your research report is ready.",
  SUCCESS: "Your research report is ready.",
  PARTIAL: "Your research finished with gaps. The partial report is ready.",
  FAILED: "The research couldn't be completed. You can open the report for details.",
  REFUSED: "The research was refused. You can open the report for details.",
  CANCELLED: "The research was cancelled.",
  INTERRUPTED: "The research was interrupted before it finished.",
};

export function ResearchNotification() {
  const [notice, setNotice] = useState<{ report: ResearchReportSummary; text: string } | null>(null);

  useEffect(() => {
    let disposed = false;
    let fetching: AbortController | undefined;
    let pollTimer: ReturnType<typeof setTimeout>;
    let playbackActive = false;
    let speaking = false;
    const startedAt = Date.now();
    const activeReports = new Set<string>();
    const observed = new Set<string>();
    const speechQueue: string[] = [];

    function playback(event: Event) {
      playbackActive = Boolean((event as CustomEvent<{ active: boolean }>).detail?.active);
    }

    async function speakNext() {
      if (disposed || speaking || !speechQueue.length) return;
      const voice = useSettingsStore.getState().voice;
      if (!voice.speakBack) { speechQueue.length = 0; return; }
      if (playbackActive || useChatStore.getState().isStreaming || !["idle", "sleeping"].includes(useAvatarStore.getState().state)) return;
      speaking = true;
      const text = speechQueue.shift()!;
      try { await apiVoiceSpeak(text, voice); }
      catch {}
      finally { speaking = false; }
    }

    async function refresh() {
      fetching = new AbortController();
      const timeout = setTimeout(() => fetching?.abort(), 8000);
      try {
        const { items } = await apiResearchReports("", 0, fetching.signal);
        if (disposed) return;
        for (const report of items) {
          if (["QUEUED", "RUNNING"].includes(report.status)) { activeReports.add(report.id); continue; }
          const text = outcomes[report.status];
          if (!text || observed.has(report.id)) continue;
          const messages = useChatStore.getState().messages;
          const requested = messages.some(message => message.meta?.action === "agent_research_started" && message.details?.report_id === report.id);
          const delivered = messages.some(message => message.meta?.action === "agent_report_finished" && message.details?.report_id === report.id);
          observed.add(report.id);
          if (delivered || (!activeReports.has(report.id) && !requested && Date.parse(report.created_at) < startedAt)) continue;
          activeReports.delete(report.id);
          setNotice({ report, text });
          useChatStore.getState().addMessage({
            role: "nova", content: `${text}\n${report.topic}`,
            meta: { action: "agent_report_finished", source: "agents" },
            details: { report_id: report.id, report_status: report.status },
          });
          if (useSettingsStore.getState().voice.speakBack) speechQueue.push(text);
        }
        void speakNext();
      } catch {} finally {
        clearTimeout(timeout);
        if (!disposed) pollTimer = setTimeout(refresh, 4000);
      }
    }

    window.addEventListener("nova-playback", playback);
    const speechTimer = setInterval(() => void speakNext(), 1000);
    void refresh();
    return () => {
      disposed = true;
      clearTimeout(pollTimer);
      clearInterval(speechTimer);
      fetching?.abort();
      window.removeEventListener("nova-playback", playback);
    };
  }, []);

  if (!notice) return null;
  return <section aria-label="Research notification" className="shrink-0 border-b border-border bg-bg-secondary px-4 sm:px-6 py-3 flex items-start gap-3">
    <div className="min-w-0 flex-1">
      <p role="status" className="text-sm text-text-primary">{notice.text}</p>
      <p className="text-xs text-text-secondary mt-1 truncate" title={notice.report.topic}>{notice.report.topic}</p>
      <OpenResearchReport identity={notice.report.id} />
    </div>
    <button aria-label="Dismiss research notification" title="Dismiss research notification" onClick={() => setNotice(null)} className="w-8 h-8 shrink-0 grid place-items-center text-text-muted hover:text-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent-blue"><X size={16} /></button>
  </section>;
}