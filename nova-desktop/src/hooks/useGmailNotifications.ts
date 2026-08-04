/**
 * useGmailNotifications
 *
 * Listens to the NOVA SSE stream for gmail_new_message events and:
 *  1. Fires an OS/browser Notification (if permission granted and notifications enabled).
 *  2. Injects a chat message into the chat feed — Jarvis style.
 *  3. Flashes the avatar to the "notification" eye state briefly.
 *  4. Speaks the alert via TTS if speakBack is on.
 *
 * Usage:  call useGmailNotifications() in App.tsx (once, globally).
 */

import { useEffect, useRef } from "react";
import { useSettingsStore } from "@/stores/useSettingsStore";
import { useChatStore } from "@/stores/useChatStore";
import { useAvatarStore } from "@/stores/useAvatarStore";
import { AvatarSSEClient } from "@/services/sseClient";
import { apiVoiceSpeak } from "@/services/api";
import type { GmailMessage, GmailUrgency } from "@/types";

const SSE_URL =
  (import.meta.env.VITE_NOVA_API_URL ?? "http://127.0.0.1:8000") + "/avatar/events";

const URGENCY_RANK: Record<GmailUrgency, number> = {
  critical: 3,
  high: 2,
  normal: 1,
  low: 0,
};

const NOTIFY_LEVEL_THRESHOLD: Record<string, number> = {
  all: 0,
  high: 2,
  critical: 3,
};

const URGENCY_LABEL: Record<string, string> = {
  critical: "🚨 CRITICAL",
  high:     "⚠️  High Priority",
  normal:   "📬 New Email",
  low:      "📩 Email",
};

function buildJarvisAlert(msg: GmailMessage): string {
  const urgencyLabel = URGENCY_LABEL[msg.urgency] ?? "📬 New Email";
  const sender = msg.from.replace(/<[^>]+>/g, "").trim();
  return [
    `**${urgencyLabel}**`,
    `**From:** ${sender}`,
    `**Subject:** ${msg.subject}`,
    msg.snippet ? `*${msg.snippet.slice(0, 120)}${msg.snippet.length > 120 ? "…" : ""}*` : "",
  ]
    .filter(Boolean)
    .join("\n");
}

function buildTtsAlert(msg: GmailMessage): string {
  const sender = msg.from.replace(/<[^>]+>/g, "").trim().split("@")[0];
  const urgencyPrefix =
    msg.urgency === "critical"
      ? "Critical alert. "
      : msg.urgency === "high"
      ? "High priority. "
      : "";
  return `${urgencyPrefix}New email from ${sender}. Subject: ${msg.subject}.`;
}

function requestNotificationPermission(): void {
  if (typeof Notification !== "undefined" && Notification.permission === "default") {
    void Notification.requestPermission();
  }
}

function fireOsNotification(msg: GmailMessage, onClick?: () => void): void {
  if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
  const sender = msg.from.replace(/<[^>]+>/g, "").trim();
  const notif = new Notification(`${msg.urgency_emoji} ${msg.subject}`, {
    body: `From: ${sender}\n${msg.snippet?.slice(0, 80) ?? ""}`,
    icon: "/icons/nova-mail.png",
    tag: `gmail-${msg.id}`,
    requireInteraction: msg.urgency === "critical",
  });
  if (onClick) notif.onclick = onClick;
}

export function useGmailNotifications() {
  const voice = useSettingsStore((s) => s.voice);
  const notifications = useSettingsStore((s) => s.notifications);
  const gmailEnabled = useSettingsStore((s) => s.gmailEnabled);
  const gmailSpeakAlerts = useSettingsStore((s) => s.gmailSpeakAlerts);
  const gmailNotifyLevel = useSettingsStore((s) => s.gmailNotifyLevel);
  const addMessage = useChatStore((s) => s.addMessage);
  const setEmotion = useAvatarStore((s) => s.setEmotion);

  const voiceRef = useRef(voice);
  voiceRef.current = voice;
  const settingsRef = useRef({ notifications, gmailEnabled, gmailSpeakAlerts, gmailNotifyLevel });
  settingsRef.current = { notifications, gmailEnabled, gmailSpeakAlerts, gmailNotifyLevel };

  useEffect(() => {
    requestNotificationPermission();

    const client = new AvatarSSEClient(
      SSE_URL,
      (_state, eventName, payload) => {
        if (eventName !== "gmail_new_message") return;
        const msg = payload as unknown as GmailMessage;
        if (!msg?.id) return;

        const s = settingsRef.current;
        if (!s.gmailEnabled) return;

        // Check if this urgency meets the configured threshold
        const msgRank = URGENCY_RANK[msg.urgency] ?? 1;
        const threshold = NOTIFY_LEVEL_THRESHOLD[s.gmailNotifyLevel] ?? 0;
        if (msgRank < threshold) return;

        // 1. Inject Jarvis-style chat message
        addMessage({
          role: "nova",
          content: buildJarvisAlert(msg),
          meta: {
            action: "gmail_notification",
            intent: `gmail_urgency_${msg.urgency}`,
            source: "gmail",
          },
        });

        // 2. Flash notification eye state
        setEmotion("notification" as never);
        setTimeout(() => setEmotion("neutral" as never), 4000);

        // 3. OS notification
        if (s.notifications) {
          fireOsNotification(msg);
        }

        // 4. TTS
        const shouldSpeak =
          s.gmailSpeakAlerts &&
          voiceRef.current.enabled &&
          (msg.urgency === "critical" || msg.urgency === "high" || voiceRef.current.speakBack);

        if (shouldSpeak) {
          void apiVoiceSpeak(buildTtsAlert(msg), voiceRef.current).catch(() => {});
        }
      },
      () => {}
    );

    client.connect();
    return () => client.destroy();
  }, []); // settings read via ref — no re-subscriptions needed
}
