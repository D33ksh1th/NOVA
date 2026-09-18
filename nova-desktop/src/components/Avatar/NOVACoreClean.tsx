/**
 * NOVACore — Enhanced JARVIS HUD.
 *
 * Clean + futuristic: glowing arc reactor, holographic arcs,
 * data ticks, smooth state transitions with motion blur.
 */

import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useAvatarStore } from "@/stores/useAvatarStore";
import { useAppStore } from "@/stores/useAppStore";
import type { AvatarState } from "@/types";

type Visual = { core: string; glow: string; label: string };
type Mode = "offline" | "idle" | "listening" | "thinking" | "speaking" | "alert" | "success" | "music";

const P: Record<Mode, Visual> = {
  offline:   { core: "#475569", glow: "rgba(71,85,105,0.06)",   label: "OFFLINE" },
  idle:      { core: "#38bdf8", glow: "rgba(56,189,248,0.12)",  label: "ONLINE" },
  listening: { core: "#22d3ee", glow: "rgba(34,211,238,0.20)",  label: "LISTENING" },
  thinking:  { core: "#fbbf24", glow: "rgba(251,191,36,0.20)",  label: "ANALYSING" },
  speaking:  { core: "#f97316", glow: "rgba(249,115,22,0.22)",  label: "SPEAKING" },
  alert:     { core: "#ef4444", glow: "rgba(239,68,68,0.20)",   label: "ALERT" },
  success:   { core: "#34d399", glow: "rgba(52,211,153,0.16)",  label: "COMPLETE" },
  music:     { core: "#a78bfa", glow: "rgba(167,139,250,0.18)", label: "VIBING" },
};

function mode(s: AvatarState, bc: boolean, ac: boolean, pg: string, mp: boolean): Mode {
  if (!bc && !ac) return "offline";
  if (s === "speaking") return "speaking";
  if (s === "listening") return "listening";
  if (s === "thinking" || s === "focused") return "thinking";
  if (pg === "security" || s === "concerned") return "alert";
  if (s === "happy" || s === "proud") return "success";
  if (mp) return "music";
  return bc ? "idle" : "offline";
}

function arcPath(cx: number, cy: number, r: number, s: number, e: number) {
  const sr = (s * Math.PI) / 180, er = (e * Math.PI) / 180;
  return `M${cx + r * Math.cos(sr)},${cy + r * Math.sin(sr)} A${r},${r} 0 ${e - s > 180 ? 1 : 0} 1 ${cx + r * Math.cos(er)},${cy + r * Math.sin(er)}`;
}

export function NOVACore() {
  const avatarState = useAvatarStore((s) => s.state);
  const speechText = useAvatarStore((s) => s.speechText);
  const emotion = useAvatarStore((s) => s.emotion);
  const app = useAppStore((s) => s.status);
  const page = useAppStore((s) => s.currentPage);

  const m = mode(avatarState, app.backendConnected, app.avatarStreamConnected, page, app.musicPlaying);
  const v = P[m];
  const active = m !== "offline";
  const speaking = m === "speaking";
  const listening = m === "listening";
  const thinking = m === "thinking";

  const CX = 180, CY = 180;

  // Floating particles
  const particles = useMemo(() =>
    Array.from({ length: 16 }, (_, i) => ({
      angle: (i / 16) * 360,
      r: 130 + Math.random() * 20,
      size: 1 + Math.random() * 1.5,
      speed: 20 + Math.random() * 15,
      delay: Math.random() * 5,
    })), []);

  return (
    <div className="relative flex flex-col items-center justify-center select-none" style={{ minHeight: 400 }}>
      {/* ambient glow */}
      <motion.div
        className="absolute inset-0"
        animate={{ background: `radial-gradient(circle at 50% 44%, ${v.glow} 0%, transparent 55%)` }}
        transition={{ duration: 0.8 }}
      />

      {/* floating particles */}
      <div className="absolute" style={{ width: 360, height: 360, left: "50%", top: "50%", transform: "translate(-50%, -50%)" }}>
        {active && particles.map((p, i) => (
          <motion.div
            key={i}
            className="absolute rounded-full"
            style={{
              width: p.size, height: p.size,
              background: v.core,
              boxShadow: `0 0 ${p.size * 4}px ${v.core}`,
              left: "50%", top: "50%",
            }}
            animate={{
              x: [Math.cos((p.angle * Math.PI) / 180) * p.r, Math.cos(((p.angle + 360) * Math.PI) / 180) * p.r],
              y: [Math.sin((p.angle * Math.PI) / 180) * p.r, Math.sin(((p.angle + 360) * Math.PI) / 180) * p.r],
              opacity: [0.2, 0.6, 0.2],
            }}
            transition={{ duration: p.speed, delay: p.delay, repeat: Infinity, ease: "linear" }}
          />
        ))}
      </div>

      <svg viewBox="0 0 360 360" style={{ width: 360, height: 360 }}>
        <defs>
          <filter id="hglow">
            <feGaussianBlur stdDeviation="5" />
            <feComposite in="SourceGraphic" operator="over" />
          </filter>
          <filter id="hglow-lg">
            <feGaussianBlur stdDeviation="10" />
            <feComposite in="SourceGraphic" operator="over" />
          </filter>
        </defs>

        {/* outer holographic arcs */}
        <motion.g
          animate={{ rotate: [0, 360] }}
          transition={{ duration: 50, repeat: Infinity, ease: "linear" }}
          style={{ transformOrigin: `${CX}px ${CY}px` }}
        >
          {[{ s: 0, e: 55 }, { s: 130, e: 185 }, { s: 260, e: 315 }].map((a, i) => (
            <motion.path
              key={`arc1-${i}`}
              d={arcPath(CX, CY, 155, a.s, a.e)}
              fill="none" strokeLinecap="round"
              animate={{ stroke: v.core, opacity: active ? 0.35 : 0.06 }}
              transition={{ duration: 0.6 }}
              strokeWidth="1.2"
            />
          ))}
        </motion.g>

        {/* inner arcs — counter rotate */}
        <motion.g
          animate={{ rotate: [360, 0] }}
          transition={{ duration: 35, repeat: Infinity, ease: "linear" }}
          style={{ transformOrigin: `${CX}px ${CY}px` }}
        >
          {[{ s: 20, e: 80 }, { s: 160, e: 220 }, { s: 300, e: 345 }].map((a, i) => (
            <motion.path
              key={`arc2-${i}`}
              d={arcPath(CX, CY, 125, a.s, a.e)}
              fill="none" strokeLinecap="round"
              animate={{ stroke: v.core, opacity: active ? 0.2 : 0.04 }}
              transition={{ duration: 0.6 }}
              strokeWidth="0.8"
            />
          ))}
        </motion.g>

        {/* tick ring */}
        <motion.g
          animate={{ rotate: [0, 360] }}
          transition={{ duration: 90, repeat: Infinity, ease: "linear" }}
          style={{ transformOrigin: `${CX}px ${CY}px` }}
        >
          {Array.from({ length: 36 }, (_, i) => {
            const a = (i * 10 * Math.PI) / 180;
            const long = i % 9 === 0;
            const r1 = long ? 102 : 106;
            return (
              <motion.line
                key={`tick-${i}`}
                x1={CX + r1 * Math.cos(a)} y1={CY + r1 * Math.sin(a)}
                x2={CX + 112 * Math.cos(a)} y2={CY + 112 * Math.sin(a)}
                animate={{ stroke: v.core, opacity: active ? (long ? 0.4 : 0.15) : 0.05 }}
                transition={{ duration: 0.6 }}
                strokeWidth={long ? 1.2 : 0.5}
              />
            );
          })}
        </motion.g>

        {/* core reactor ring */}
        <motion.circle
          cx={CX} cy={CY}
          fill="none" filter="url(#hglow)"
          animate={{
            r: speaking ? [48, 56, 44, 54, 48] : listening ? [48, 52, 48] : thinking ? [48, 50, 48] : [48, 49, 48],
            stroke: v.core,
            strokeWidth: speaking ? 2.5 : 2,
            opacity: active ? [0.5, 1, 0.5] : 0.15,
          }}
          transition={{
            r: { duration: speaking ? 0.5 : listening ? 1.2 : 3, repeat: Infinity, ease: "easeInOut" },
            stroke: { duration: 0.6 },
            opacity: { duration: speaking ? 0.5 : 2.5, repeat: Infinity },
          }}
        />

        {/* inner fill */}
        <motion.circle
          cx={CX} cy={CY}
          animate={{
            r: speaking ? [34, 40, 32, 38, 34] : [34, 36, 34],
            fill: `${v.core}12`,
          }}
          transition={{
            r: { duration: speaking ? 0.4 : 3, repeat: Infinity, ease: "easeInOut" },
            fill: { duration: 0.6 },
          }}
        />

        {/* reactor core glow */}
        <motion.circle
          cx={CX} cy={CY} r={18}
          filter="url(#hglow-lg)"
          animate={{ fill: `${v.core}25`, opacity: active ? [0.3, 0.6, 0.3] : 0.08 }}
          transition={{ duration: 2, repeat: Infinity }}
        />

        {/* center bright point */}
        <motion.circle
          cx={CX} cy={CY} r={7}
          filter="url(#hglow)"
          animate={{ fill: v.core, opacity: active ? [0.4, 0.9, 0.4] : 0.1 }}
          transition={{ duration: 2, repeat: Infinity }}
        />
        <circle cx={CX} cy={CY} r={2.5} fill="white" opacity={0.8} />

        {/* listening: sonar */}
        {listening && [0, 1, 2].map(i => (
          <motion.circle
            key={`s${i}`} cx={CX} cy={CY}
            fill="none" stroke={v.core} strokeWidth="0.8"
            initial={{ r: 52, opacity: 0.5 }}
            animate={{ r: [52, 140], opacity: [0.4, 0] }}
            transition={{ duration: 2, delay: i * 0.6, repeat: Infinity, ease: "easeOut" }}
          />
        ))}

        {/* thinking: orbiting dots */}
        {thinking && (
          <motion.g
            animate={{ rotate: [0, 360] }}
            transition={{ duration: 3.5, repeat: Infinity, ease: "linear" }}
            style={{ transformOrigin: `${CX}px ${CY}px` }}
          >
            {[0, 120, 240].map(deg => {
              const a = (deg * Math.PI) / 180;
              return <circle key={deg} cx={CX + 85 * Math.cos(a)} cy={CY + 85 * Math.sin(a)} r={2.5} fill={v.core} filter="url(#hglow)" />;
            })}
          </motion.g>
        )}

        {/* speaking: outer pulse ring */}
        {speaking && (
          <motion.circle
            cx={CX} cy={CY}
            fill="none" stroke={v.core} strokeWidth="1.2" filter="url(#hglow)"
            animate={{ r: [55, 68, 55], opacity: [0.2, 0.5, 0.2] }}
            transition={{ duration: 0.7, repeat: Infinity, ease: "easeInOut" }}
          />
        )}

        {/* speaking: secondary pulse */}
        {speaking && (
          <motion.circle
            cx={CX} cy={CY}
            fill="none" stroke={v.core} strokeWidth="0.6"
            animate={{ r: [70, 85, 70], opacity: [0.1, 0.3, 0.1] }}
            transition={{ duration: 0.9, repeat: Infinity, ease: "easeInOut" }}
          />
        )}

        {/* status text */}
        <motion.text
          x={CX} y={310}
          textAnchor="middle" fontSize="8.5"
          fontFamily="JetBrains Mono, monospace" letterSpacing="3.5"
          animate={{ fill: v.core, opacity: [0.3, 0.6, 0.3] }}
          transition={{ fill: { duration: 0.6 }, opacity: { duration: 3, repeat: Infinity } }}
        >
          {v.label}
        </motion.text>

        {/* HUD corner brackets */}
        <motion.path d="M20,40 L20,20 L40,20" fill="none" strokeWidth="0.8" animate={{ stroke: v.core, opacity: active ? 0.2 : 0.05 }} transition={{ duration: 0.6 }} />
        <motion.path d="M320,20 L340,20 L340,40" fill="none" strokeWidth="0.8" animate={{ stroke: v.core, opacity: active ? 0.2 : 0.05 }} transition={{ duration: 0.6 }} />
        <motion.path d="M20,320 L20,340 L40,340" fill="none" strokeWidth="0.8" animate={{ stroke: v.core, opacity: active ? 0.2 : 0.05 }} transition={{ duration: 0.6 }} />
        <motion.path d="M320,340 L340,340 L340,320" fill="none" strokeWidth="0.8" animate={{ stroke: v.core, opacity: active ? 0.2 : 0.05 }} transition={{ duration: 0.6 }} />
      </svg>

      {/* bottom status */}
      <div className="flex items-center gap-2 -mt-2">
        <motion.div className="h-px w-12" style={{ background: `linear-gradient(to left, ${v.core}50, transparent)` }} animate={{ scaleX: [0.5, 1, 0.5] }} transition={{ duration: 2.5, repeat: Infinity }} />
        <motion.div className="w-1.5 h-1.5 rounded-full" animate={{ backgroundColor: v.core, boxShadow: `0 0 6px ${v.core}`, scale: [1, 1.3, 1] }} transition={{ scale: { duration: 2, repeat: Infinity } }} />
        <span className="font-mono text-[9px] tracking-[0.3em] uppercase text-white/35">
          {active ? "NOVA ONLINE" : "OFFLINE"}
        </span>
        <motion.div className="w-1.5 h-1.5 rounded-full" animate={{ backgroundColor: v.core, boxShadow: `0 0 6px ${v.core}`, scale: [1, 1.3, 1] }} transition={{ scale: { duration: 2, repeat: Infinity, delay: 1 } }} />
        <motion.div className="h-px w-12" style={{ background: `linear-gradient(to right, ${v.core}50, transparent)` }} animate={{ scaleX: [0.5, 1, 0.5] }} transition={{ duration: 2.5, repeat: Infinity }} />
      </div>

      {/* speech bubble */}
      <AnimatePresence>
        {speechText && (
          <motion.div
            initial={{ opacity: 0, y: 8, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.15 }}
            className="mt-3 max-w-xs px-4 py-2 rounded-xl text-center text-sm text-white/80"
            style={{ background: "rgba(5,10,20,0.85)", border: `1px solid ${v.core}18`, backdropFilter: "blur(12px)" }}
          >
            {speechText}
          </motion.div>
        )}
      </AnimatePresence>

      {/* emotion */}
      <AnimatePresence>
        {emotion && emotion !== "neutral" && (
          <motion.span
            initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}
            className="mt-2 px-2.5 py-0.5 rounded-full text-[9px] font-mono uppercase tracking-[0.2em]"
            style={{ color: `${v.core}bb`, border: `1px solid ${v.core}18` }}
          >
            {emotion}
          </motion.span>
        )}
      </AnimatePresence>
    </div>
  );
}
