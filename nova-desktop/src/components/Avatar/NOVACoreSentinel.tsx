/**
 * NOVACore — NOVA Sentinel (2026 advanced AI HUD)
 *
 * Beyond JARVIS: a living neural mesh that breathes, pulses with
 * data flow, and morphs shape per state. Layered holographic
 * geometry with depth parallax, data-stream trails, and
 * a sentient eye-like core that tracks activity.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useMotionValue, useTransform } from "framer-motion";
import { useAvatarStore } from "@/stores/useAvatarStore";
import { useAppStore } from "@/stores/useAppStore";
import type { AvatarState } from "@/types";

/* ── palette ────────────────────────────────────────────── */

type StateVisual = {
  core: string;      // primary neon
  ring: string;      // secondary
  iris: string;      // the "eye" iris colour
  ambient: string;   // bg glow
  text: string;      // HUD text
  status: string;
};

type CoreMode =
  | "offline" | "booting" | AvatarState | "monitoring" | "processing"
  | "security_alert" | "success" | "error" | "music_vibe";

const PALETTE: Record<CoreMode, StateVisual> = {
  offline:        { core: "#334155", ring: "#1e293b", iris: "#475569", ambient: "rgba(51,65,85,0.08)",  text: "#64748b", status: "DORMANT" },
  booting:        { core: "#06b6d4", ring: "#0e7490", iris: "#22d3ee", ambient: "rgba(6,182,212,0.12)", text: "#67e8f9", status: "INITIALISING" },
  idle:           { core: "#06b6d4", ring: "#0891b2", iris: "#22d3ee", ambient: "rgba(6,182,212,0.10)", text: "#67e8f9", status: "SENTINEL ACTIVE" },
  monitoring:     { core: "#06b6d4", ring: "#0891b2", iris: "#22d3ee", ambient: "rgba(6,182,212,0.12)", text: "#67e8f9", status: "SENTINEL ACTIVE" },
  listening:      { core: "#10b981", ring: "#059669", iris: "#34d399", ambient: "rgba(16,185,129,0.18)", text: "#6ee7b7", status: "RECEIVING" },
  thinking:       { core: "#f59e0b", ring: "#d97706", iris: "#fbbf24", ambient: "rgba(245,158,11,0.18)", text: "#fde68a", status: "COGNITION" },
  processing:     { core: "#8b5cf6", ring: "#7c3aed", iris: "#a78bfa", ambient: "rgba(139,92,246,0.16)", text: "#c4b5fd", status: "NEURAL COMPUTE" },
  speaking:       { core: "#f43f5e", ring: "#e11d48", iris: "#fb7185", ambient: "rgba(244,63,94,0.20)",  text: "#fda4af", status: "VOCALISING" },
  security_alert: { core: "#ef4444", ring: "#b91c1c", iris: "#f87171", ambient: "rgba(239,68,68,0.22)",  text: "#fca5a5", status: "THREAT DETECTED" },
  success:        { core: "#10b981", ring: "#059669", iris: "#34d399", ambient: "rgba(16,185,129,0.14)", text: "#6ee7b7", status: "OBJECTIVE MET" },
  error:          { core: "#ef4444", ring: "#dc2626", iris: "#f87171", ambient: "rgba(239,68,68,0.18)",  text: "#fca5a5", status: "FAULT" },
  sleeping:       { core: "#475569", ring: "#334155", iris: "#64748b", ambient: "rgba(71,85,105,0.06)",  text: "#94a3b8", status: "LOW POWER" },
  focused:        { core: "#8b5cf6", ring: "#7c3aed", iris: "#a78bfa", ambient: "rgba(139,92,246,0.14)", text: "#c4b5fd", status: "DEEP FOCUS" },
  relaxed:        { core: "#06b6d4", ring: "#0891b2", iris: "#22d3ee", ambient: "rgba(6,182,212,0.08)",  text: "#67e8f9", status: "STANDBY" },
  proud:          { core: "#f59e0b", ring: "#d97706", iris: "#fbbf24", ambient: "rgba(245,158,11,0.14)", text: "#fde68a", status: "MISSION COMPLETE" },
  shy:            { core: "#8b5cf6", ring: "#6d28d9", iris: "#a78bfa", ambient: "rgba(139,92,246,0.10)", text: "#c4b5fd", status: "RESERVED" },
  happy:          { core: "#f59e0b", ring: "#d97706", iris: "#fbbf24", ambient: "rgba(245,158,11,0.16)", text: "#fde68a", status: "OPTIMAL" },
  curious:        { core: "#06b6d4", ring: "#0891b2", iris: "#22d3ee", ambient: "rgba(6,182,212,0.14)", text: "#67e8f9", status: "ANALYSING" },
  concerned:      { core: "#f97316", ring: "#c2410c", iris: "#fb923c", ambient: "rgba(249,115,22,0.16)", text: "#fdba74", status: "ELEVATED" },
  excited:        { core: "#ec4899", ring: "#db2777", iris: "#f472b6", ambient: "rgba(236,72,153,0.18)", text: "#f9a8d4", status: "AMPLIFIED" },
  music_vibe:     { core: "#8b5cf6", ring: "#ec4899", iris: "#c084fc", ambient: "rgba(139,92,246,0.18)", text: "#e9d5ff", status: "HARMONIC" },
};

function resolveCoreMode(s: AvatarState, bc: boolean, asc: boolean, pg: string, mp: boolean): CoreMode {
  if (!bc && !asc) return "offline";
  if (bc && !asc) return "booting";
  if (pg === "security") return "security_alert";
  if (s === "speaking") return "speaking";
  if (s === "listening") return "listening";
  if (s === "thinking") return pg === "vision" || pg === "memory" ? "processing" : "thinking";
  if (mp) return "music_vibe";
  if (s === "happy" || s === "proud") return "success";
  if (s === "concerned") return "error";
  if (s === "focused") return "processing";
  if (s === "curious") return "monitoring";
  return bc ? "monitoring" : "offline";
}

/* ── geometry helpers ───────────────────────────────────── */

function arc(cx: number, cy: number, r: number, s: number, e: number) {
  const sr = (s * Math.PI) / 180, er = (e * Math.PI) / 180;
  const x1 = cx + r * Math.cos(sr), y1 = cy + r * Math.sin(sr);
  const x2 = cx + r * Math.cos(er), y2 = cy + r * Math.sin(er);
  return `M${x1},${y1} A${r},${r} 0 ${e - s > 180 ? 1 : 0} 1 ${x2},${y2}`;
}

function hexRing(cx: number, cy: number, r: number, count: number, size: number) {
  const pts: { x: number; y: number }[] = [];
  for (let i = 0; i < count; i++) {
    const a = ((i * 360) / count) * (Math.PI / 180);
    pts.push({ x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) });
  }
  return pts.map((p) => {
    const hex = Array.from({ length: 6 }, (_, j) => {
      const a = ((Math.PI * 2) / 6) * j - Math.PI / 6;
      return `${p.x + Math.cos(a) * size},${p.y + Math.sin(a) * size}`;
    });
    return `M${hex.join("L")}Z`;
  });
}

/* ── data stream text ───────────────────────────────────── */

const DATA_STREAMS = [
  "▸ THREAT_SCAN: 0 VECTORS",
  "▸ NEURAL_MESH: 24 NODES",
  "▸ VOICE_LOCK: VERIFIED",
  "▸ PERIMETER: SECURE",
  "▸ INFERENCE: 12ms p95",
  "▸ CONTEXT: 4.2K TOKENS",
  "▸ UPLINK: NOMINAL",
  "▸ MEMORY: 847 EPISODES",
];

/* ── component ──────────────────────────────────────────── */

export function NOVACore() {
  const avatarState = useAvatarStore((s) => s.state);
  const speechText = useAvatarStore((s) => s.speechText);
  const emotion = useAvatarStore((s) => s.emotion);
  const appStatus = useAppStore((s) => s.status);
  const currentPage = useAppStore((s) => s.currentPage);
  const musicPlaying = appStatus.musicPlaying;

  const mode = resolveCoreMode(avatarState, appStatus.backendConnected, appStatus.avatarStreamConnected, currentPage, musicPlaying);
  const p = PALETTE[mode] ?? PALETTE.monitoring;
  const active = mode !== "offline" && mode !== "sleeping";
  const speaking = mode === "speaking";
  const listening = mode === "listening";
  const thinking = mode === "thinking" || mode === "processing";
  const alert = mode === "security_alert" || mode === "error";

  const CX = 200, CY = 200;

  /* ticking HUD data */
  const [tick, setTick] = useState(0);
  const [streamIdx, setStreamIdx] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setTick((n) => n + 1), 60);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    const t = setInterval(() => setStreamIdx((n) => (n + 1) % DATA_STREAMS.length), 2400);
    return () => clearInterval(t);
  }, []);

  const hexPaths = useMemo(() => hexRing(CX, CY, 152, 12, 11), []);
  const innerHex = useMemo(() => hexRing(CX, CY, 108, 6, 8), []);

  /* iris pupil dilation based on state */
  const pupilR = speaking ? 18 : listening ? 14 : thinking ? 10 : 12;
  const irisR = speaking ? 38 : listening ? 35 : thinking ? 32 : 34;

  /* waveform for speaking */
  const wavePoints = useMemo(() => {
    if (!speaking) return "";
    const pts: string[] = [];
    for (let i = 0; i <= 60; i++) {
      const x = CX - 100 + (i / 60) * 200;
      const amp = Math.sin((i / 60) * Math.PI) * (15 + Math.sin(tick * 0.3 + i * 0.4) * 10);
      const y = CY + 90 + Math.sin(tick * 0.25 + i * 0.5) * amp;
      pts.push(`${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`);
    }
    return pts.join(" ");
  }, [speaking, tick]);

  return (
    <div className="relative flex flex-col items-center justify-center select-none" style={{ minHeight: 460 }}>
      {/* deep ambient glow */}
      <div className="absolute inset-0 transition-all duration-1000" style={{
        background: `radial-gradient(ellipse at 50% 42%, ${p.ambient} 0%, transparent 55%)`,
      }} />

      {/* floating data streams — left */}
      <div className="absolute left-4 top-1/2 -translate-y-1/2 flex flex-col gap-1 opacity-30">
        {DATA_STREAMS.slice(0, 4).map((line, i) => (
          <motion.span
            key={i}
            className="font-mono text-[8px] tracking-wide"
            style={{ color: p.text }}
            animate={{ opacity: streamIdx === i ? [0.3, 0.8, 0.3] : 0.2 }}
            transition={{ duration: 2 }}
          >
            {line}
          </motion.span>
        ))}
      </div>

      {/* floating data streams — right */}
      <div className="absolute right-4 top-1/2 -translate-y-1/2 flex flex-col gap-1 items-end opacity-30">
        {DATA_STREAMS.slice(4).map((line, i) => (
          <motion.span
            key={i}
            className="font-mono text-[8px] tracking-wide"
            style={{ color: p.text }}
            animate={{ opacity: streamIdx === i + 4 ? [0.3, 0.8, 0.3] : 0.2 }}
            transition={{ duration: 2 }}
          >
            {line}
          </motion.span>
        ))}
      </div>

      {/* main SVG */}
      <svg viewBox="0 0 400 400" className="relative" style={{ width: 400, height: 400 }}>
        <defs>
          <filter id="s-glow" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="5" result="b" />
            <feComposite in="SourceGraphic" in2="b" operator="over" />
          </filter>
          <filter id="s-glow-lg" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="14" result="b" />
            <feComposite in="SourceGraphic" in2="b" operator="over" />
          </filter>
          <radialGradient id="iris-grad" cx="45%" cy="40%">
            <stop offset="0%" stopColor="white" stopOpacity="0.3" />
            <stop offset="40%" stopColor={p.iris} stopOpacity="0.8" />
            <stop offset="100%" stopColor={p.core} stopOpacity="0.2" />
          </radialGradient>
          <radialGradient id="pupil-grad" cx="42%" cy="38%">
            <stop offset="0%" stopColor={p.iris} stopOpacity="0.9" />
            <stop offset="60%" stopColor={p.core} stopOpacity="0.6" />
            <stop offset="100%" stopColor="#000" stopOpacity="0.95" />
          </radialGradient>
        </defs>

        {/* ── outer hex mesh ──────────────────── */}
        <motion.g
          animate={{ rotate: [0, 360] }}
          transition={{ duration: 120, repeat: Infinity, ease: "linear" }}
          style={{ transformOrigin: `${CX}px ${CY}px` }}
        >
          {hexPaths.map((d, i) => (
            <motion.path
              key={`hex-${i}`}
              d={d}
              fill="none"
              stroke={p.core}
              strokeWidth="0.7"
              animate={{
                opacity: active ? [0.1, 0.35, 0.1] : 0.05,
                strokeWidth: [0.5, 0.9, 0.5],
              }}
              transition={{ duration: 3, delay: i * 0.25, repeat: Infinity }}
            />
          ))}
        </motion.g>

        {/* ── inner hex nodes ─────────────────── */}
        <motion.g
          animate={{ rotate: [360, 0] }}
          transition={{ duration: 80, repeat: Infinity, ease: "linear" }}
          style={{ transformOrigin: `${CX}px ${CY}px` }}
        >
          {innerHex.map((d, i) => (
            <path
              key={`ihex-${i}`}
              d={d}
              fill={`${p.core}08`}
              stroke={p.core}
              strokeWidth="0.5"
              opacity={0.2}
            />
          ))}
        </motion.g>

        {/* ── arc segments ────────────────────── */}
        <motion.g
          animate={{ rotate: [0, 360] }}
          transition={{ duration: 50, repeat: Infinity, ease: "linear" }}
          style={{ transformOrigin: `${CX}px ${CY}px` }}
        >
          {[
            { r: 170, s: 10, e: 55 },
            { r: 170, s: 130, e: 175 },
            { r: 170, s: 250, e: 295 },
          ].map((a, i) => (
            <path key={`a1-${i}`} d={arc(CX, CY, a.r, a.s, a.e)} fill="none" stroke={p.core} strokeWidth="1.2" strokeLinecap="round" opacity={0.4} filter="url(#s-glow)" />
          ))}
        </motion.g>

        <motion.g
          animate={{ rotate: [360, 0] }}
          transition={{ duration: 38, repeat: Infinity, ease: "linear" }}
          style={{ transformOrigin: `${CX}px ${CY}px` }}
        >
          {[
            { r: 130, s: 20, e: 90 },
            { r: 130, s: 160, e: 230 },
            { r: 130, s: 300, e: 350 },
          ].map((a, i) => (
            <path key={`a2-${i}`} d={arc(CX, CY, a.r, a.s, a.e)} fill="none" stroke={p.ring} strokeWidth="0.8" strokeLinecap="round" opacity={0.3} />
          ))}
        </motion.g>

        {/* ── data orbit dots ─────────────────── */}
        <motion.g
          animate={{ rotate: [0, 360] }}
          transition={{ duration: 18, repeat: Infinity, ease: "linear" }}
          style={{ transformOrigin: `${CX}px ${CY}px` }}
        >
          {Array.from({ length: 8 }, (_, i) => {
            const a = (i * 45 * Math.PI) / 180;
            return (
              <circle
                key={`dot-${i}`}
                cx={CX + 142 * Math.cos(a)}
                cy={CY + 142 * Math.sin(a)}
                r={1.8}
                fill={p.iris}
                opacity={0.5}
                filter="url(#s-glow)"
              />
            );
          })}
        </motion.g>

        {/* ── THE EYE — iris ──────────────────── */}
        <motion.circle
          cx={CX} cy={CY}
          r={irisR}
          fill="url(#iris-grad)"
          stroke={p.core}
          strokeWidth="1.5"
          filter="url(#s-glow-lg)"
          animate={{
            r: speaking ? [36, 42, 34, 40, 36] : listening ? [33, 37, 33] : [33, 35, 33],
          }}
          transition={{
            duration: speaking ? 0.6 : listening ? 1.6 : 3,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        />

        {/* iris texture rings */}
        {[0.7, 0.5, 0.3].map((frac, i) => (
          <circle
            key={`iris-ring-${i}`}
            cx={CX} cy={CY}
            r={irisR * frac}
            fill="none"
            stroke={p.iris}
            strokeWidth="0.3"
            opacity={0.15 + i * 0.05}
          />
        ))}

        {/* pupil */}
        <motion.circle
          cx={CX} cy={CY}
          r={pupilR}
          fill="url(#pupil-grad)"
          animate={{
            r: speaking ? [16, 22, 14, 20, 16] : thinking ? [8, 12, 8] : [11, 13, 11],
          }}
          transition={{
            duration: speaking ? 0.5 : thinking ? 1.2 : 2.5,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        />

        {/* pupil highlight */}
        <circle cx={CX - 5} cy={CY - 6} r={4} fill="white" opacity={0.35} filter="url(#s-glow)" />
        <circle cx={CX + 8} cy={CY + 4} r={2} fill="white" opacity={0.2} />

        {/* ── listening: concentric sonar ─────── */}
        {listening && [0, 1, 2, 3].map((i) => (
          <motion.circle
            key={`sonar-${i}`}
            cx={CX} cy={CY} r={40}
            fill="none" stroke={p.core} strokeWidth="0.8"
            initial={{ r: 40, opacity: 0.5 }}
            animate={{ r: [40, 170], opacity: [0.4, 0] }}
            transition={{ duration: 2.5, delay: i * 0.6, repeat: Infinity, ease: "easeOut" }}
          />
        ))}

        {/* ── thinking: scanning beam ─────────── */}
        {thinking && (
          <motion.g
            animate={{ rotate: [0, 360] }}
            transition={{ duration: 2.5, repeat: Infinity, ease: "linear" }}
            style={{ transformOrigin: `${CX}px ${CY}px` }}
          >
            <line x1={CX} y1={CY} x2={CX + 155} y2={CY} stroke={p.core} strokeWidth="1" opacity={0.4} filter="url(#s-glow)" />
            {/* scan trail */}
            <path
              d={`M${CX},${CY} L${CX + 155},${CY - 8} L${CX + 155},${CY + 8} Z`}
              fill={p.core}
              opacity={0.06}
            />
            <circle cx={CX + 155} cy={CY} r={3} fill={p.iris} filter="url(#s-glow)" />
          </motion.g>
        )}

        {/* ── speaking: voice waveform ────────── */}
        {speaking && wavePoints && (
          <motion.path
            d={wavePoints}
            fill="none"
            stroke={p.core}
            strokeWidth="1.5"
            strokeLinecap="round"
            filter="url(#s-glow)"
            animate={{ opacity: [0.4, 0.8, 0.4] }}
            transition={{ duration: 0.3, repeat: Infinity }}
          />
        )}

        {/* ── alert: pulsing danger ring ──────── */}
        {alert && (
          <motion.circle
            cx={CX} cy={CY} r={90}
            fill="none" stroke={p.core} strokeWidth="2" strokeDasharray="8 4"
            animate={{ opacity: [0.2, 0.7, 0.2], r: [85, 95, 85] }}
            transition={{ duration: 1, repeat: Infinity }}
            filter="url(#s-glow)"
          />
        )}

        {/* ── HUD corners ─────────────────────── */}
        {/* top-left bracket */}
        <path d="M30,55 L30,30 L55,30" fill="none" stroke={p.core} strokeWidth="1" opacity={0.25} />
        {/* top-right bracket */}
        <path d="M345,30 L370,30 L370,55" fill="none" stroke={p.core} strokeWidth="1" opacity={0.25} />
        {/* bottom-left bracket */}
        <path d="M30,345 L30,370 L55,370" fill="none" stroke={p.core} strokeWidth="1" opacity={0.25} />
        {/* bottom-right bracket */}
        <path d="M345,370 L370,370 L370,345" fill="none" stroke={p.core} strokeWidth="1" opacity={0.25} />

        {/* top HUD label */}
        <text x={CX} y={24} fill={p.text} opacity={0.4} fontSize="8" fontFamily="JetBrains Mono, monospace" textAnchor="middle" letterSpacing="4">
          N O V A &nbsp; S E N T I N E L
        </text>

        {/* bottom status */}
        <motion.text
          x={CX} y={388}
          fill={p.text}
          fontSize="9"
          fontFamily="JetBrains Mono, monospace"
          textAnchor="middle"
          letterSpacing="3"
          animate={{ opacity: [0.3, 0.7, 0.3] }}
          transition={{ duration: 3, repeat: Infinity }}
        >
          {p.status}
        </motion.text>
      </svg>

      {/* status line below SVG */}
      <div className="flex items-center gap-3 -mt-1">
        <motion.div
          className="h-[1px] w-16 origin-right"
          style={{ background: `linear-gradient(to left, ${p.core}60, transparent)` }}
          animate={{ scaleX: [0.6, 1, 0.6] }}
          transition={{ duration: 2, repeat: Infinity }}
        />
        <div className="flex items-center gap-1.5">
          <motion.div
            className="w-1.5 h-1.5 rounded-full"
            style={{ background: p.core, boxShadow: `0 0 8px ${p.core}` }}
            animate={{ scale: [1, 1.6, 1], opacity: [0.5, 1, 0.5] }}
            transition={{ duration: 2, repeat: Infinity }}
          />
          <span className="font-mono text-[9px] tracking-[0.35em] uppercase" style={{ color: p.text }}>
            {active ? "ALL SYSTEMS OPERATIONAL" : "SYSTEMS OFFLINE"}
          </span>
          <motion.div
            className="w-1.5 h-1.5 rounded-full"
            style={{ background: p.core, boxShadow: `0 0 8px ${p.core}` }}
            animate={{ scale: [1, 1.6, 1], opacity: [0.5, 1, 0.5] }}
            transition={{ duration: 2, repeat: Infinity, delay: 1 }}
          />
        </div>
        <motion.div
          className="h-[1px] w-16 origin-left"
          style={{ background: `linear-gradient(to right, ${p.core}60, transparent)` }}
          animate={{ scaleX: [0.6, 1, 0.6] }}
          transition={{ duration: 2, repeat: Infinity }}
        />
      </div>

      {/* speech bubble */}
      <AnimatePresence>
        {speechText && (
          <motion.div
            initial={{ opacity: 0, y: 10, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.95 }}
            transition={{ duration: 0.2 }}
            className="mt-4 max-w-sm px-5 py-3 text-center text-sm"
            style={{
              color: "#e2e8f0",
              background: "rgba(5,10,18,0.88)",
              border: `1px solid ${p.core}20`,
              borderRadius: 14,
              backdropFilter: "blur(16px)",
              boxShadow: `0 0 40px ${p.ambient}, 0 4px 30px rgba(0,0,0,0.4), inset 0 1px 0 ${p.core}10`,
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
            initial={{ opacity: 0, scale: 0.8, y: 4 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.8 }}
            className="mt-2 px-3 py-0.5 rounded-full text-[9px] font-mono uppercase tracking-[0.25em]"
            style={{
              color: p.text,
              border: `1px solid ${p.core}20`,
              background: `linear-gradient(135deg, ${p.core}08, ${p.ring}05)`,
            }}
          >
            {emotion}
          </motion.span>
        )}
      </AnimatePresence>
    </div>
  );
}
