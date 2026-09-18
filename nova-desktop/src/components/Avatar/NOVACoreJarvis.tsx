/**
 * NOVACore — JARVIS / Iron Man HUD theme.
 *
 * Layered holographic arcs, rotating targeting rings,
 * hex grid overlay, blue-orange glow, scan-line HUD text.
 */

import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useAvatarStore } from "@/stores/useAvatarStore";
import { useAppStore } from "@/stores/useAppStore";
import type { AvatarState } from "@/types";

/* ── JARVIS colour palette ──────────────────────────────── */

type StateVisual = {
  core: string;
  ring: string;
  soft: string;
  glow: string;
  status: string;
  accent: string;
};

type CoreMode =
  | "offline" | "booting" | AvatarState | "monitoring" | "processing"
  | "security_alert" | "success" | "error" | "music_vibe";

const V: Record<CoreMode, StateVisual> = {
  offline:        { core: "#3a4a5c", ring: "#2a3a4c", soft: "#0a0e14", glow: "rgba(58,74,92,0.12)", status: "OFFLINE",    accent: "#64748b" },
  booting:        { core: "#38bdf8", ring: "#0284c7", soft: "#061520", glow: "rgba(56,189,248,0.20)", status: "BOOTING",   accent: "#7dd3fc" },
  idle:           { core: "#38bdf8", ring: "#0284c7", soft: "#061520", glow: "rgba(56,189,248,0.22)", status: "ONLINE",    accent: "#7dd3fc" },
  monitoring:     { core: "#38bdf8", ring: "#0369a1", soft: "#061822", glow: "rgba(56,189,248,0.24)", status: "MONITORING",accent: "#7dd3fc" },
  listening:      { core: "#22d3ee", ring: "#0891b2", soft: "#051a22", glow: "rgba(34,211,238,0.35)", status: "LISTENING", accent: "#67e8f9" },
  thinking:       { core: "#f59e0b", ring: "#d97706", soft: "#1a1408", glow: "rgba(245,158,11,0.40)", status: "ANALYZING", accent: "#fbbf24" },
  processing:     { core: "#f59e0b", ring: "#b45309", soft: "#1a1205", glow: "rgba(245,158,11,0.35)", status: "PROCESSING",accent: "#fcd34d" },
  speaking:       { core: "#f97316", ring: "#c2410c", soft: "#1a0f05", glow: "rgba(249,115,22,0.42)", status: "SPEAKING",  accent: "#fb923c" },
  security_alert: { core: "#ef4444", ring: "#b91c1c", soft: "#1a0505", glow: "rgba(239,68,68,0.40)", status: "THREAT",    accent: "#fca5a5" },
  success:        { core: "#22d3ee", ring: "#0891b2", soft: "#051a22", glow: "rgba(34,211,238,0.30)", status: "COMPLETE",  accent: "#67e8f9" },
  error:          { core: "#ef4444", ring: "#dc2626", soft: "#1a0505", glow: "rgba(239,68,68,0.35)", status: "ERROR",     accent: "#fca5a5" },
  sleeping:       { core: "#475569", ring: "#334155", soft: "#0a0e14", glow: "rgba(71,85,105,0.18)", status: "STANDBY",   accent: "#94a3b8" },
  focused:        { core: "#38bdf8", ring: "#0284c7", soft: "#061822", glow: "rgba(56,189,248,0.30)", status: "FOCUSED",  accent: "#7dd3fc" },
  relaxed:        { core: "#38bdf8", ring: "#0369a1", soft: "#061520", glow: "rgba(56,189,248,0.20)", status: "STANDBY",  accent: "#7dd3fc" },
  proud:          { core: "#f59e0b", ring: "#d97706", soft: "#1a1408", glow: "rgba(245,158,11,0.30)", status: "COMPLETE", accent: "#fbbf24" },
  shy:            { core: "#38bdf8", ring: "#0284c7", soft: "#061520", glow: "rgba(56,189,248,0.18)", status: "STANDBY",  accent: "#7dd3fc" },
  happy:          { core: "#f59e0b", ring: "#d97706", soft: "#1a1408", glow: "rgba(245,158,11,0.32)", status: "NOMINAL",  accent: "#fbbf24" },
  curious:        { core: "#38bdf8", ring: "#0284c7", soft: "#061822", glow: "rgba(56,189,248,0.28)", status: "SCANNING", accent: "#7dd3fc" },
  concerned:      { core: "#f97316", ring: "#c2410c", soft: "#1a0f05", glow: "rgba(249,115,22,0.35)", status: "CAUTION",  accent: "#fb923c" },
  excited:        { core: "#22d3ee", ring: "#0891b2", soft: "#051a22", glow: "rgba(34,211,238,0.38)", status: "AMPLIFIED",accent: "#67e8f9" },
  music_vibe:     { core: "#38bdf8", ring: "#f97316", soft: "#0a1020", glow: "rgba(56,189,248,0.30)", status: "VIBING",   accent: "#fbbf24" },
};

function resolveCoreMode(
  avatarState: AvatarState,
  backendConnected: boolean,
  avatarStreamConnected: boolean,
  currentPage: string,
  musicPlaying: boolean,
): CoreMode {
  if (!backendConnected && !avatarStreamConnected) return "offline";
  if (backendConnected && !avatarStreamConnected) return "booting";
  if (currentPage === "security") return "security_alert";
  if (avatarState === "speaking") return "speaking";
  if (avatarState === "listening") return "listening";
  if (avatarState === "thinking") return currentPage === "vision" || currentPage === "memory" ? "processing" : "thinking";
  if (musicPlaying) return "music_vibe";
  if (avatarState === "happy" || avatarState === "proud") return "success";
  if (avatarState === "concerned") return "error";
  if (avatarState === "focused") return "processing";
  if (avatarState === "curious") return "monitoring";
  return backendConnected ? "monitoring" : "offline";
}

/* ── SVG arc helpers ────────────────────────────────────── */

function arcPath(cx: number, cy: number, r: number, startDeg: number, endDeg: number): string {
  const s = (startDeg * Math.PI) / 180;
  const e = (endDeg * Math.PI) / 180;
  const x1 = cx + r * Math.cos(s);
  const y1 = cy + r * Math.sin(s);
  const x2 = cx + r * Math.cos(e);
  const y2 = cy + r * Math.sin(e);
  const large = endDeg - startDeg > 180 ? 1 : 0;
  return `M${x1},${y1} A${r},${r} 0 ${large} 1 ${x2},${y2}`;
}

function tickMarks(cx: number, cy: number, r1: number, r2: number, count: number, skip: number[] = []) {
  const marks: string[] = [];
  for (let i = 0; i < count; i++) {
    if (skip.includes(i)) continue;
    const a = ((i * 360) / count) * (Math.PI / 180);
    marks.push(`M${cx + r1 * Math.cos(a)},${cy + r1 * Math.sin(a)} L${cx + r2 * Math.cos(a)},${cy + r2 * Math.sin(a)}`);
  }
  return marks.join(" ");
}

/* ── component ──────────────────────────────────────────── */

export function NOVACore() {
  const avatarState = useAvatarStore((s) => s.state);
  const speechText = useAvatarStore((s) => s.speechText);
  const emotion = useAvatarStore((s) => s.emotion);
  const appStatus = useAppStore((s) => s.status);
  const currentPage = useAppStore((s) => s.currentPage);
  const musicPlaying = appStatus.musicPlaying;

  const mode = resolveCoreMode(avatarState, appStatus.backendConnected, appStatus.avatarStreamConnected, currentPage, musicPlaying);
  const v = V[mode] ?? V.monitoring;
  const isActive = mode !== "offline" && mode !== "sleeping";
  const isSpeaking = mode === "speaking";
  const isListening = mode === "listening";
  const isThinking = mode === "thinking" || mode === "processing";
  const isAlert = mode === "security_alert" || mode === "error";

  const CX = 200;
  const CY = 200;

  /* HUD data readouts */
  const [hudTick, setHudTick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setHudTick((n) => n + 1), 80);
    return () => clearInterval(t);
  }, []);

  const hudValues = useMemo(() => ({
    cpu: 12 + Math.sin(hudTick * 0.15) * 8,
    mem: 34 + Math.cos(hudTick * 0.1) * 6,
    net: 2 + Math.sin(hudTick * 0.2) * 2,
  }), [hudTick]);

  return (
    <div className="relative flex flex-col items-center justify-center select-none" style={{ minHeight: 440 }}>
      {/* background radial glow */}
      <div
        className="absolute inset-0 transition-all duration-700"
        style={{ background: `radial-gradient(ellipse at 50% 45%, ${v.glow} 0%, transparent 60%)` }}
      />

      {/* subtle grid overlay */}
      <div
        className="absolute inset-0 pointer-events-none opacity-[0.025]"
        style={{
          backgroundImage: `
            linear-gradient(${v.core}15 1px, transparent 1px),
            linear-gradient(90deg, ${v.core}15 1px, transparent 1px)
          `,
          backgroundSize: "40px 40px",
        }}
      />

      {/* main SVG HUD */}
      <svg viewBox="0 0 400 400" className="relative" style={{ width: 380, height: 380 }}>
        <defs>
          {/* core glow filter */}
          <filter id="jarvis-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="6" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
          <filter id="jarvis-glow-strong" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="12" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
          {/* arc gradient */}
          <linearGradient id="arc-grad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor={v.core} stopOpacity="0" />
            <stop offset="50%" stopColor={v.core} stopOpacity="0.9" />
            <stop offset="100%" stopColor={v.core} stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* ── outer targeting arcs ────────────── */}
        <motion.g
          animate={{ rotate: [0, 360] }}
          transition={{ duration: 60, repeat: Infinity, ease: "linear" }}
          style={{ transformOrigin: `${CX}px ${CY}px` }}
        >
          {[
            { r: 175, s: 0, e: 70 },
            { r: 175, s: 120, e: 190 },
            { r: 175, s: 250, e: 320 },
          ].map((a, i) => (
            <path
              key={`outer-${i}`}
              d={arcPath(CX, CY, a.r, a.s, a.e)}
              fill="none"
              stroke={v.core}
              strokeWidth="1.5"
              strokeLinecap="round"
              opacity={0.5}
              filter="url(#jarvis-glow)"
            />
          ))}
        </motion.g>

        {/* ── second arc ring (counter-rotate) ── */}
        <motion.g
          animate={{ rotate: [360, 0] }}
          transition={{ duration: 45, repeat: Infinity, ease: "linear" }}
          style={{ transformOrigin: `${CX}px ${CY}px` }}
        >
          {[
            { r: 158, s: 30, e: 80 },
            { r: 158, s: 150, e: 210 },
            { r: 158, s: 270, e: 340 },
          ].map((a, i) => (
            <path
              key={`mid-${i}`}
              d={arcPath(CX, CY, a.r, a.s, a.e)}
              fill="none"
              stroke={v.accent}
              strokeWidth="1"
              strokeLinecap="round"
              opacity={0.35}
            />
          ))}
        </motion.g>

        {/* ── tick marks ring ─────────────────── */}
        <motion.g
          animate={{ rotate: [0, 360] }}
          transition={{ duration: 90, repeat: Infinity, ease: "linear" }}
          style={{ transformOrigin: `${CX}px ${CY}px` }}
        >
          <path
            d={tickMarks(CX, CY, 140, 147, 72, [0, 18, 36, 54])}
            stroke={v.core}
            strokeWidth="0.8"
            opacity={0.3}
          />
          {/* cardinal tick marks — longer */}
          <path
            d={tickMarks(CX, CY, 137, 147, 4)}
            stroke={v.accent}
            strokeWidth="1.5"
            opacity={0.6}
          />
        </motion.g>

        {/* ── inner ring (dashed) ─────────────── */}
        <circle
          cx={CX} cy={CY} r={125}
          fill="none"
          stroke={v.core}
          strokeWidth="0.6"
          strokeDasharray="3 6"
          opacity={0.25}
        />

        {/* ── core reactor ────────────────────── */}
        <motion.circle
          cx={CX} cy={CY}
          r={isSpeaking ? 58 : isListening ? 55 : 52}
          fill="none"
          stroke={v.core}
          strokeWidth="2"
          filter="url(#jarvis-glow-strong)"
          opacity={0.8}
          animate={{
            r: isSpeaking ? [55, 62, 52, 60, 55] : isListening ? [52, 56, 52] : [52, 53, 52],
            opacity: isActive ? [0.6, 0.9, 0.6] : 0.3,
          }}
          transition={{
            duration: isSpeaking ? 0.7 : isListening ? 1.5 : 3,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        />

        {/* inner core fill */}
        <motion.circle
          cx={CX} cy={CY} r={45}
          fill={`${v.core}15`}
          stroke={v.core}
          strokeWidth="0.5"
          opacity={0.6}
          animate={{
            r: isSpeaking ? [42, 48, 40, 46, 42] : [44, 46, 44],
          }}
          transition={{
            duration: isSpeaking ? 0.6 : 2.5,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        />

        {/* reactor center glow */}
        <circle
          cx={CX} cy={CY} r={20}
          fill={`${v.core}30`}
          filter="url(#jarvis-glow-strong)"
        />
        <circle
          cx={CX} cy={CY} r={8}
          fill={v.core}
          opacity={0.6}
          filter="url(#jarvis-glow)"
        />
        <circle
          cx={CX} cy={CY} r={3}
          fill="white"
          opacity={0.9}
        />

        {/* ── listening: sonar rings ──────────── */}
        {isListening && [0, 1, 2].map((i) => (
          <motion.circle
            key={`sonar-${i}`}
            cx={CX} cy={CY} r={55}
            fill="none"
            stroke={v.core}
            strokeWidth="1"
            initial={{ r: 55, opacity: 0.5 }}
            animate={{ r: [55, 140], opacity: [0.5, 0] }}
            transition={{
              duration: 2.2,
              delay: i * 0.7,
              repeat: Infinity,
              ease: "easeOut",
            }}
          />
        ))}

        {/* ── thinking: rotating scanner ──────── */}
        {isThinking && (
          <motion.g
            animate={{ rotate: [0, 360] }}
            transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
            style={{ transformOrigin: `${CX}px ${CY}px` }}
          >
            <line
              x1={CX} y1={CY}
              x2={CX + 130} y2={CY}
              stroke={v.core}
              strokeWidth="1.5"
              opacity={0.5}
              filter="url(#jarvis-glow)"
            />
            <circle
              cx={CX + 130} cy={CY} r={3}
              fill={v.accent}
              filter="url(#jarvis-glow)"
            />
          </motion.g>
        )}

        {/* ── alert: flashing crosshairs ─────── */}
        {isAlert && (
          <motion.g
            animate={{ opacity: [0.3, 0.8, 0.3] }}
            transition={{ duration: 0.8, repeat: Infinity }}
          >
            <line x1={CX - 160} y1={CY} x2={CX - 60} y2={CY} stroke={v.core} strokeWidth="1" opacity={0.5} />
            <line x1={CX + 60} y1={CY} x2={CX + 160} y2={CY} stroke={v.core} strokeWidth="1" opacity={0.5} />
            <line x1={CX} y1={CY - 160} x2={CX} y2={CY - 60} stroke={v.core} strokeWidth="1" opacity={0.5} />
            <line x1={CX} y1={CY + 60} x2={CX} y2={CY + 160} stroke={v.core} strokeWidth="1" opacity={0.5} />
          </motion.g>
        )}

        {/* ── HUD text readouts ───────────────── */}
        <text x={38} y={90} fill={v.accent} opacity={0.45} fontSize="8" fontFamily="JetBrains Mono, monospace">
          SYS {hudValues.cpu.toFixed(1)}%
        </text>
        <text x={38} y={102} fill={v.accent} opacity={0.35} fontSize="8" fontFamily="JetBrains Mono, monospace">
          MEM {hudValues.mem.toFixed(1)}%
        </text>
        <text x={38} y={114} fill={v.accent} opacity={0.3} fontSize="8" fontFamily="JetBrains Mono, monospace">
          NET {hudValues.net.toFixed(1)} Mb/s
        </text>

        <text x={310} y={90} fill={v.accent} opacity={0.45} fontSize="8" fontFamily="JetBrains Mono, monospace" textAnchor="end">
          NOVA v0.4
        </text>
        <text x={310} y={102} fill={v.accent} opacity={0.35} fontSize="8" fontFamily="JetBrains Mono, monospace" textAnchor="end">
          {mode.toUpperCase()}
        </text>
        <text x={310} y={114} fill={v.accent} opacity={0.3} fontSize="8" fontFamily="JetBrains Mono, monospace" textAnchor="end">
          JARVIS PROTOCOL
        </text>

        {/* bottom HUD bar */}
        <line x1={80} y1={355} x2={320} y2={355} stroke={v.core} strokeWidth="0.5" opacity={0.2} />
        <text x={CX} y={348} fill={v.accent} opacity={0.5} fontSize="9" fontFamily="JetBrains Mono, monospace" textAnchor="middle" letterSpacing="3">
          {v.status}
        </text>
      </svg>

      {/* status indicator below SVG */}
      <motion.div
        className="flex items-center gap-2 -mt-2"
        animate={{ opacity: [0.6, 1, 0.6] }}
        transition={{ duration: 3, repeat: Infinity }}
      >
        <motion.div
          className="w-1.5 h-1.5 rounded-full"
          style={{ background: v.core, boxShadow: `0 0 6px ${v.core}` }}
          animate={{ scale: [1, 1.4, 1] }}
          transition={{ duration: 2, repeat: Infinity }}
        />
        <span
          className="font-mono text-[10px] tracking-[0.3em] uppercase"
          style={{ color: v.accent }}
        >
          {isActive ? "SYSTEMS NOMINAL" : "OFFLINE"}
        </span>
        <motion.div
          className="w-1.5 h-1.5 rounded-full"
          style={{ background: v.core, boxShadow: `0 0 6px ${v.core}` }}
          animate={{ scale: [1, 1.4, 1] }}
          transition={{ duration: 2, repeat: Infinity, delay: 1 }}
        />
      </motion.div>

      {/* speech bubble */}
      <AnimatePresence>
        {speechText && (
          <motion.div
            initial={{ opacity: 0, y: 8, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.96 }}
            transition={{ duration: 0.2 }}
            className="mt-3 max-w-sm px-5 py-2.5 text-center text-sm font-light"
            style={{
              color: "#e2e8f0",
              background: "rgba(8,15,25,0.85)",
              border: `1px solid ${v.core}30`,
              borderRadius: 12,
              backdropFilter: "blur(12px)",
              boxShadow: `0 0 30px ${v.glow}, inset 0 1px 0 ${v.core}15`,
            }}
          >
            {speechText}
          </motion.div>
        )}
      </AnimatePresence>

      {/* emotion badge */}
      <AnimatePresence>
        {emotion && emotion !== "neutral" && (
          <motion.span
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            className="mt-2 px-3 py-0.5 rounded-full text-[9px] font-mono uppercase tracking-[0.2em] border"
            style={{
              color: v.accent,
              borderColor: `${v.core}25`,
              background: `${v.soft}aa`,
            }}
          >
            {emotion}
          </motion.span>
        )}
      </AnimatePresence>
    </div>
  );
}
