import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { clsx } from "clsx";
import { useSettingsStore } from "@/stores/useSettingsStore";
import { useAppStore } from "@/stores/useAppStore";
import {
  apiGetVoiceRecognition,
  apiSetVoiceRecognition,
  apiVoiceDeleteAllSpeakers,
  apiVoiceDeleteSpeaker,
  apiVoiceSetAdmin,
  apiVoiceSettings,
  apiVoiceSpeakers,
  apiVoiceSpeak,
  apiVoiceStop,
} from "@/services/api";
import type { VoiceSpeakerProfile } from "@/types";
import {
  Volume2,
  Mic,
  Cat,
  Monitor,
  Bell,
  Code2,
  Save,
  CheckCircle,
  AlertCircle,
  Radio,
  Shield,
  UserRound,
  Trash2,
  Square,
} from "lucide-react";

type SettingsSection = "voice" | "avatar" | "system" | "developer";

export function SettingsPanel() {
  const [activeSection, setActiveSection] = useState<SettingsSection>("voice");
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"idle" | "ok" | "err">("idle");

  const sections: { id: SettingsSection; label: string; icon: React.ReactNode }[] = [
    { id: "voice", label: "Voice & Mic", icon: <Volume2 size={15} /> },
    { id: "avatar", label: "Avatar", icon: <Cat size={15} /> },
    { id: "system", label: "System", icon: <Monitor size={15} /> },
    { id: "developer", label: "Developer", icon: <Code2 size={15} /> },
  ];

  async function handleSave() {
    setSaving(true);
    try {
      const voice = useSettingsStore.getState().voice;
      await apiVoiceSettings(voice);
      setSaveStatus("ok");
    } catch {
      setSaveStatus("err");
    } finally {
      setSaving(false);
      setTimeout(() => setSaveStatus("idle"), 2500);
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-6 py-5 border-b border-border">
        <p className="nova-panel-heading mb-2">Make it yours</p>
        <h2 className="font-display font-medium text-2xl text-text-primary">Settings</h2>
      </div>

      <div className="flex flex-col sm:flex-row flex-1 min-h-0 overflow-hidden">
        {/* Section tabs */}
        <nav className="grid grid-cols-2 sm:block sm:w-44 border-b sm:border-b-0 sm:border-r border-border p-3 gap-1 sm:space-y-1 flex-shrink-0">
          {sections.map((s) => (
            <button
              key={s.id}
              onClick={() => setActiveSection(s.id)}
              className={clsx(
                "w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-[13px] font-medium transition-all",
                activeSection === s.id
                  ? "bg-nova-orange/15 text-nova-orange border border-nova-orange/20"
                  : "text-text-secondary hover:bg-bg-elevated hover:text-text-primary"
              )}
            >
              {s.icon}
              {s.label}
            </button>
          ))}
        </nav>

        {/* Section content */}
        <div className="flex-1 min-w-0 overflow-y-auto p-4 sm:px-8 sm:py-6">
          {activeSection === "voice" && <VoiceSection />}
          {activeSection === "avatar" && <AvatarSection />}
          {activeSection === "system" && <SystemSection />}
          {activeSection === "developer" && <DeveloperSection />}
        </div>
      </div>

      {/* Footer save bar */}
      <div className="border-t border-border px-4 sm:px-6 py-4 flex flex-wrap gap-3 items-center justify-between">
        <div className="flex items-center gap-2 text-[13px]">
          {saveStatus === "ok" && (
            <motion.span
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex items-center gap-1.5 text-accent-green"
            >
              <CheckCircle size={14} /> Settings synced to backend
            </motion.span>
          )}
          {saveStatus === "err" && (
            <motion.span
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex items-center gap-1.5 text-accent-red"
            >
              <AlertCircle size={14} /> Sync failed — backend may be offline
            </motion.span>
          )}
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 bg-nova-orange hover:bg-nova-glow text-white px-4 py-2 rounded-md text-[13px] font-semibold transition-all disabled:opacity-50"
        >
          <Save size={14} />
          {saving ? "Saving…" : "Apply to Backend"}
        </button>
      </div>
    </div>
  );
}

// ── Voice Section ────────────────────────────────────────────────
function VoiceSection() {
  const voice = useSettingsStore((s) => s.voice);
  const setVoice = useSettingsStore((s) => s.setVoice);
  const voiceWakeActive = useAppStore((s) => s.voiceWakeActive);
  const voiceRecognitionEnabled = useSettingsStore((s) => s.voiceRecognitionEnabled);
  const setVoiceRecognitionEnabled = useSettingsStore((s) => s.setVoiceRecognitionEnabled);
  const [speakers, setSpeakers] = useState<VoiceSpeakerProfile[]>([]);
  const [speakersLoading, setSpeakersLoading] = useState(false);
  const [adminSavingId, setAdminSavingId] = useState<string | null>(null);
  const [deletingSpeakerId, setDeletingSpeakerId] = useState<string | null>(null);
  const [deletingAll, setDeletingAll] = useState(false);
  const [previewPending, setPreviewPending] = useState(false);
  const [previewError, setPreviewError] = useState("");

  async function previewVoice(stop = false) {
    setPreviewPending(true);
    setPreviewError("");
    try {
      if (stop) await apiVoiceStop();
      else await apiVoiceSpeak("I have the findings ready. The numbers look promising, but I would check the cooling before declaring victory.", voice);
    } catch {
      setPreviewError("Voice preview unavailable. Check the backend connection.");
    } finally {
      setPreviewPending(false);
    }
  }

  const loadSpeakers = async () => {
    setSpeakersLoading(true);
    try {
      const res = await apiVoiceSpeakers();
      setSpeakers(Array.isArray(res.speakers) ? res.speakers : []);
    } catch {
      setSpeakers([]);
    } finally {
      setSpeakersLoading(false);
    }
  };

  // Auto-sync settings to backend whenever they change
  useEffect(() => {
    const syncTimer = setTimeout(async () => {
      try {
        await apiVoiceSettings(voice);
      } catch (err) {
        console.warn("Failed to auto-sync voice settings to backend:", err);
      }
    }, 300); // Debounce by 300ms to avoid too frequent API calls

    return () => clearTimeout(syncTimer);
  }, [voice]);

  useEffect(() => {
    loadSpeakers();
    // Sync recognition toggle from backend on mount
    apiGetVoiceRecognition().then((r) => setVoiceRecognitionEnabled(r.enabled)).catch(() => {});
  }, []);

  const setAdminSpeaker = async (speakerId: string) => {
    setAdminSavingId(speakerId);
    try {
      await apiVoiceSetAdmin(speakerId);
      await loadSpeakers();
    } finally {
      setAdminSavingId(null);
    }
  };

  const deleteSpeaker = async (speaker: VoiceSpeakerProfile) => {
    const ok = window.confirm(`Delete voice profile ${speaker.name}?`);
    if (!ok) return;
    setDeletingSpeakerId(speaker.id);
    try {
      await apiVoiceDeleteSpeaker(speaker.id);
      await loadSpeakers();
    } finally {
      setDeletingSpeakerId(null);
    }
  };

  const deleteAllSpeakers = async () => {
    const ok = window.confirm("Delete all voice profiles? This cannot be undone.");
    if (!ok) return;
    setDeletingAll(true);
    try {
      await apiVoiceDeleteAllSpeakers();
      await loadSpeakers();
    } finally {
      setDeletingAll(false);
    }
  };

  const toggleRecognition = async (val: boolean) => {
    setVoiceRecognitionEnabled(val);
    try {
      await apiSetVoiceRecognition(val);
    } catch {
      // Revert on failure
      setVoiceRecognitionEnabled(!val);
    }
  };

  return (
    <div className="space-y-6">
      <SectionHeader
        title="Voice & Microphone"
        description="Configure how NOVA speaks and listens."
      />

      <SettingsGroup title="General">
        <ToggleRow
          label="Speak Back"
          description="NOVA responds with voice after each message."
          value={voice.speakBack}
          onChange={(v) => setVoice({ speakBack: v })}
        />
        <ToggleRow
          label="Microphone Enabled"
          description="Allow NOVA to listen via your microphone."
          value={voice.micEnabled}
          onChange={(v) => setVoice({ micEnabled: v })}
        />
        <ToggleRow
          label="Hands-free Wake Word"
          description='Say "hi nova", "hey nova", or "nova" to start talking.'
          value={voice.handsFreeWake}
          onChange={(v) => setVoice({ handsFreeWake: v, micEnabled: v ? true : voice.micEnabled })}
        />
        <ToggleRow
          label="Voice Recognition"
          description="Identify who is speaking. When off, NOVA responds to anyone freely."
          value={voiceRecognitionEnabled}
          onChange={toggleRecognition}
        />

        {/* Live wake listener status indicator */}
        <div className={clsx(
          "flex items-center gap-2.5 px-3 py-2 rounded-xl border text-[12px] font-mono transition-all duration-300",
          voiceWakeActive
            ? "border-accent-green/40 bg-accent-green/8 text-accent-green"
            : "border-border bg-bg-elevated text-text-muted"
        )}>
          <Radio size={12} className="flex-shrink-0" />
          {voiceWakeActive ? (
            <>
              <motion.span
                className="w-1.5 h-1.5 rounded-full bg-accent-green flex-shrink-0"
                animate={{ opacity: [1, 0.2, 1] }}
                transition={{ duration: 1.1, repeat: Infinity }}
              />
              <span>Wake listener active — say <strong className="font-bold">"nova"</strong> to activate</span>
            </>
          ) : (
            <>
              <span className="w-1.5 h-1.5 rounded-full bg-text-muted flex-shrink-0" />
              <span>Wake listener {voice.handsFreeWake ? "starting…" : "off — enable above"}</span>
            </>
          )}
        </div>
      </SettingsGroup>

      <SettingsGroup title="Voice">
        <SelectRow
          label="Voice"
          value={voice.model === "english_amy" ? "english_amy" : "english_lessac"}
          onChange={(v) => {
            const isFemale = v === "english_amy";
            setVoice({
              model: v,
              accent: isFemale ? "english_friday" : "english_jarvis",
              style: isFemale ? "warm" : "calm",
              rate: isFemale ? 180 : 176,
              pitch: isFemale ? 52 : 44,
            });
          }}
          options={[
            { value: "english_lessac", label: "George / British male" },
            { value: "english_amy", label: "Emma / British female" },
          ]}
        />
        <SelectRow
          label="Style"
          value={voice.style}
          onChange={(v) => setVoice({ style: v as typeof voice.style })}
          options={[
            { value: "calm", label: "Calm" },
            { value: "clear", label: "Clear" },
            { value: "natural", label: "Natural" },
            { value: "warm", label: "Warm" },
          ]}
        />
        <div className="flex flex-wrap gap-2">
          <button disabled={previewPending} onClick={() => void previewVoice()} className="inline-flex items-center gap-2 px-3 py-2 border border-border rounded-md text-sm text-text-primary disabled:opacity-50"><Volume2 size={15} />Preview voice</button>
          <button disabled={previewPending} onClick={() => void previewVoice(true)} title="Stop voice preview" aria-label="Stop voice preview" className="h-9 w-9 inline-flex items-center justify-center border border-border rounded-md text-text-muted disabled:opacity-50"><Square size={15} /></button>
        </div>
        {previewError && <p role="alert" className="text-xs text-accent-red">{previewError}</p>}
      </SettingsGroup>

      <SettingsGroup title="Voice Parameters">
        <SliderRow
          label="Speech Rate"
          value={voice.rate}
          min={156}
          max={212}
          step={2}
          onChange={(v) => setVoice({ rate: v })}
          displayValue={`${(voice.rate / 180).toFixed(2)}x`}
        />
      </SettingsGroup>

      <SettingsGroup title="Voice Identity">
        <div className="flex items-center justify-between mb-2 gap-2">
          <p className="text-[12px] text-text-muted">
            Manage recognized voice profiles and admin assignment.
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={loadSpeakers}
              className="text-[11px] px-2.5 py-1 rounded-lg border border-border text-text-muted hover:text-text-primary hover:bg-bg-elevated transition-all"
            >
              Refresh
            </button>
            <button
              onClick={deleteAllSpeakers}
              disabled={deletingAll || speakers.length === 0}
              className="text-[11px] px-2.5 py-1 rounded-lg border border-accent-red/40 text-accent-red hover:bg-accent-red/10 transition-all disabled:opacity-50"
            >
              {deletingAll ? "Deleting…" : "Delete All"}
            </button>
          </div>
        </div>

        {speakersLoading ? (
          <div className="text-[12px] text-text-muted">Loading voice profiles…</div>
        ) : speakers.length === 0 ? (
          <div className="text-[12px] text-text-muted border border-border rounded-xl p-3 bg-bg-elevated/40">
            No voice profiles enrolled yet. Say "recognize voice" in chat to begin enrollment.
          </div>
        ) : (
          <div className="space-y-2">
            {speakers.map((sp) => {
              const isAdmin = (sp.role || "").toLowerCase() === "admin";
              return (
                <div
                  key={sp.id}
                  className={clsx(
                    "flex items-center justify-between rounded-xl border px-3 py-2.5",
                    isAdmin
                      ? "border-accent-green/40 bg-accent-green/8"
                      : "border-border bg-bg-elevated/30"
                  )}
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    {isAdmin ? (
                      <Shield size={14} className="text-accent-green flex-shrink-0" />
                    ) : (
                      <UserRound size={14} className="text-text-muted flex-shrink-0" />
                    )}
                    <div className="min-w-0">
                      <p className="text-[13px] font-semibold text-text-primary truncate">{sp.name}</p>
                      <p className="text-[11px] text-text-muted">
                        {sp.samples} samples • {isAdmin ? "Admin" : "User"}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {isAdmin ? (
                      <span className="text-[11px] px-2 py-1 rounded-lg border border-accent-green/40 text-accent-green bg-accent-green/10">
                        Admin
                      </span>
                    ) : (
                      <button
                        onClick={() => setAdminSpeaker(sp.id)}
                        disabled={adminSavingId === sp.id || deletingSpeakerId === sp.id || deletingAll}
                        className="text-[11px] px-2.5 py-1 rounded-lg border border-border text-text-secondary hover:text-text-primary hover:bg-bg-card transition-all disabled:opacity-50"
                      >
                        {adminSavingId === sp.id ? "Setting…" : "Set Admin"}
                      </button>
                    )}
                    <button
                      onClick={() => deleteSpeaker(sp)}
                      disabled={deletingSpeakerId === sp.id || deletingAll || adminSavingId === sp.id}
                      className="inline-flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-lg border border-accent-red/40 text-accent-red hover:bg-accent-red/10 transition-all disabled:opacity-50"
                    >
                      <Trash2 size={12} />
                      {deletingSpeakerId === sp.id ? "Deleting…" : "Delete"}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </SettingsGroup>
    </div>
  );
}

// ── Avatar Section ───────────────────────────────────────────────
function AvatarSection() {
  const { avatarVisible, avatarTheme, avatarScale, setAvatarVisible, setAvatarTheme, setAvatarScale } =
    useSettingsStore();

  return (
    <div className="space-y-6">
      <SectionHeader
        title="Avatar"
        description="Customise how NOVA looks and behaves."
      />
      <SettingsGroup title="Display">
        <ToggleRow
          label="Show Avatar"
          description="Show the 3D companion on the Companion page."
          value={avatarVisible}
          onChange={setAvatarVisible}
        />
        <SliderRow
          label="Scale"
          value={avatarScale}
          min={0.5}
          max={1.5}
          step={0.05}
          onChange={setAvatarScale}
          displayValue={`${(avatarScale * 100).toFixed(0)}%`}
        />
      </SettingsGroup>
      <SettingsGroup title="Appearance">
        <div>
          <label className="text-[13px] font-medium text-text-primary block mb-3">
            Coat Theme
          </label>
          <div className="flex gap-3">
            {(["orange", "grey", "black"] as const).map((theme) => (
              <button
                key={theme}
                onClick={() => setAvatarTheme(theme)}
                className={clsx(
                  "w-10 h-10 rounded-full border-2 transition-all capitalize",
                  avatarTheme === theme
                    ? "border-nova-orange scale-110 shadow-glow"
                    : "border-border hover:border-text-muted"
                )}
                style={{
                  background:
                    theme === "orange"
                      ? "linear-gradient(135deg,#f97316,#c2410c)"
                      : theme === "grey"
                      ? "linear-gradient(135deg,#9ca3af,#6b7280)"
                      : "linear-gradient(135deg,#374151,#111827)",
                }}
                title={theme}
              />
            ))}
          </div>
        </div>
      </SettingsGroup>

      <div className="rounded-xl border border-border bg-bg-card p-4 text-[13px] text-text-muted">
        <p className="font-medium text-nova-amber mb-1">🚧 Sprint 2 Feature</p>
        <p>
          Realistic 3D Persian cat GLTF model with Blender-exported animations, morph targets for lip sync,
          and emotion-driven expression blending will be added in Sprint 2.
        </p>
      </div>
    </div>
  );
}

// ── System Section ───────────────────────────────────────────────
function SystemSection() {
  const { notifications } = useSettingsStore();

  return (
    <div className="space-y-6">
      <SectionHeader
        title="System"
        description="Notifications, privacy and behaviour settings."
      />
      <SettingsGroup title="Notifications">
        <ToggleRow
          label="Desktop Notifications"
          description="Allow NOVA to send desktop notifications."
          value={notifications}
          onChange={() => {}}
        />
      </SettingsGroup>
      <SettingsGroup title="Privacy">
        <InfoRow label="Camera" value="Not enabled" />
        <InfoRow label="Microphone" value="Requires permission" />
        <InfoRow label="File Access" value="Not enabled" />
        <InfoRow label="Data Storage" value="Local only (SQLite)" />
      </SettingsGroup>
      <SettingsGroup title="Backend">
        <InfoRow label="API URL" value="http://127.0.0.1:8000" />
        <InfoRow label="SSE Stream" value="/avatar/events" />
        <InfoRow label="Chat Endpoint" value="POST /chat" />
      </SettingsGroup>
    </div>
  );
}

// ── Developer Section ─────────────────────────────────────────────
function DeveloperSection() {
  const { developerMode, setDeveloperMode } = useSettingsStore();

  return (
    <div className="space-y-6">
      <SectionHeader title="Developer" description="Debug tools and advanced options." />
      <SettingsGroup title="Developer Mode">
        <ToggleRow
          label="Developer Mode"
          description="Show extra debug info, state inspector, and API logs."
          value={developerMode}
          onChange={setDeveloperMode}
        />
      </SettingsGroup>
      <SettingsGroup title="Tech Stack">
        {[
          { label: "Desktop", value: "Tauri 2 + React 18 + TypeScript 5" },
          { label: "3D", value: "React Three Fiber 8 + Drei + Three.js" },
          { label: "State", value: "Zustand 5" },
          { label: "Styling", value: "Tailwind CSS 3 + Framer Motion 11" },
          { label: "Backend", value: "FastAPI + Python + Ollama" },
          { label: "Voice", value: "Kokoro TTS + Whisper.cpp (planned)" },
          { label: "Build", value: "Vite 6 + Cargo" },
        ].map(({ label, value }) => (
          <InfoRow key={label} label={label} value={value} />
        ))}
      </SettingsGroup>
    </div>
  );
}

// ── Shared Form Components ─────────────────────────────────────────
function SectionHeader({ title, description }: { title: string; description: string }) {
  return (
    <div>
      <h3 className="font-display font-bold text-lg text-text-primary">{title}</h3>
      <p className="text-text-muted text-sm mt-0.5">{description}</p>
    </div>
  );
}

function SettingsGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-border pt-5 max-w-3xl">
      <p className="nova-panel-heading mb-3">
        {title}
      </p>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

function ToggleRow({
  label,
  description,
  value,
  onChange,
}: {
  label: string;
  description?: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-3 border-b border-border/50 last:border-0">
      <div>
        <p className="text-[13px] font-medium text-text-primary">{label}</p>
        {description && (
          <p className="text-[12px] text-text-muted mt-0.5">{description}</p>
        )}
      </div>
      <button
        type="button"
        role="switch"
        aria-label={label}
        aria-checked={value}
        onClick={() => onChange(!value)}
        className={clsx(
          "relative flex-shrink-0 w-[52px] h-7 rounded-full border transition-all duration-200",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-nova-orange/50",
          value
            ? "bg-nova-orange/80 border-nova-orange"
            : "bg-bg-elevated border-border"
        )}
      >
        <motion.span
          animate={{ x: value ? 26 : 3 }}
          transition={{ type: "spring", stiffness: 520, damping: 34 }}
          className="absolute top-[3px] w-5 h-5 bg-white rounded-full shadow-md"
        />
        <span
          className={clsx(
            "absolute inset-0 flex items-center justify-center text-[9px] font-mono font-bold tracking-wide pointer-events-none",
            value ? "text-white/90" : "text-text-muted"
          )}
        >
          {value ? "ON" : "OFF"}
        </span>
      </button>
    </div>
  );
}

function SelectRow({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-3 border-b border-border/50 last:border-0">
      <p className="text-[13px] font-medium text-text-primary flex-shrink-0">{label}</p>
      <select
        aria-label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="min-w-0 bg-bg-secondary border border-border rounded-md px-3 py-2 text-[12px] text-text-primary outline-none focus:border-nova-orange/50 max-w-[200px]"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function SliderRow({
  label,
  value,
  min,
  max,
  step,
  onChange,
  displayValue,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  displayValue: string;
}) {
  return (
    <div className="py-3 border-b border-border/50 last:border-0">
      <div className="flex justify-between mb-2">
        <p className="text-[13px] font-medium text-text-primary">{label}</p>
        <span className="text-[12px] text-nova-orange font-semibold tabular-nums">
          {displayValue}
        </span>
      </div>
      <input
        type="range"
        aria-label={label}
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-nova-orange"
      />
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-border/50 last:border-0">
      <p className="text-[13px] text-text-muted">{label}</p>
      <p className="text-[12px] font-medium text-text-primary font-mono">{value}</p>
    </div>
  );
}
