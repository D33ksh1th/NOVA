/**
 * NOVACore — Cyberpunk/Neon redesign.
 *
 * Replaces the geometric SVG orb with a layered neon-glow
 * plasma sphere, glitch text, animated scan lines, and
 * reactive particle trails.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useAvatarStore } from "@/stores/useAvatarStore";
import { useAppStore } from "@/stores/useAppStore";
import type { AvatarState } from "@/types";

/* ── colour system ──────────────────────────────────────── */

type StateVisual = {
  core: string;
  ring: string;
  soft: string;
  glow: string;
  status: string;
  accent: string;
  particle: string;
};

type CoreMode =
  | "offline"
  | "booting"
  | AvatarState
  | "monitoring"
  | "processing"
  | "security_alert"
  | "success"
  | "error"
  | "music_vibe";

const STATE_VISUALS: Record<CoreMode, StateVisual> = {
  offline:        { core: "#4a4e69", ring: "#22223b", soft: "#0a0a12", glow: "rgba(74,78,105,0.15)", status: "OFFLINE",   accent: "#6c757d", particle: "#4a4e69" },
  booting:        { core: "#00f0ff", ring: "#0a7e8c", soft: "#031b1e", glow: "rgba(0,240,255,0.25)", status: "BOOTING",   accent: "#00f0ff", particle: "#00d4ff" },
  idle:           { core: "#00f0ff", ring: "#0891b2", soft: "#0a1a20", glow: "rgba(0,240,255,0.20)", status: "ONLINE",    accent: "#22d3ee", particle: "#06b6d4" },
  monitoring:     { core: "#00f0ff", ring: "#0891b2", soft: "#0a1a20", glow: "rgba(0,240,255,0.22)", status: "MONITORING",accent: "#22d3ee", particle: "#06b6d4" },
  listening:      { core: "#00ff9f", ring: "#059669", soft: "#051a12", glow: "rgba(0,255,159,0.35)", status: "LISTENING", accent: "#34d399", particle: "#10b981" },
  thinking:       { core: "#f59e0b", ring: "#d97706", soft: "#1a1005", glow: "rgba(245,158,11,0.40)", status: "THINKING", accent: "#fbbf24", particle: "#f59e0b" },
  processing:     { core: "#e879f9", ring: "#a21caf", soft: "#1a0520", glow: "rgba(232,121,249,0.35)", status: "PROCESSING", accent: "#d946ef", particle: "#c026d3" },
  speaking:       { core: "#ff2d78", ring: "#be185d", soft: "#1a0510", glow: "rgba(255,45,120,0.40)", status: "SPEAKING",  accent: "#f472b6", particle: "#ec4899" },
  security_alert: { core: "#ff3333", ring: "#dc2626", soft: "#1a0505", glow: "rgba(255,51,51,0.45)", status: "ALERT",     accent: "#ef4444", particle: "#f87171" },
  success:        { core: "#00ff9f", ring: "#059669", soft: "#051a12", glow: "rgba(0,255,159,0.30)", status: "SUCCESS",   accent: "#34d399", particle: "#10b981" },
  error:          { core: "#ff3333", ring: "#dc2626", soft: "#1a0505", glow: "rgba(255,51,51,0.35)", status: "ERROR",     accent: "#f87171", particle: "#ef4444" },
  sleeping:       { core: "#6366f1", ring: "#4338ca", soft: "#0a0520", glow: "rgba(99,102,241,0.20)", status: "SLEEPING",  accent: "#818cf8", particle: "#6366f1" },
  focused:        { core: "#e879f9", ring: "#a21caf", soft: "#15051f", glow: "rgba(232,121,249,0.30)", status: "FOCUSED",  accent: "#d946ef", particle: "#c026d3" },
  relaxed:        { core: "#22d3ee", ring: "#0891b2", soft: "#051a20", glow: "rgba(34,211,238,0.22)", status: "RELAXED",  accent: "#67e8f9", particle: "#06b6d4" },
  proud:          { core: "#fbbf24", ring: "#d97706", soft: "#1a1508", glow: "rgba(251,191,36,0.30)", status: "SUCCESS",  accent: "#fde68a", particle: "#f59e0b" },
  shy:            { core: "#a78bfa", ring: "#7c3aed", soft: "#0d0520", glow: "rgba(167,139,250,0.22)", status: "SHY",     accent: "#c4b5fd", particle: "#8b5cf6" },
  happy:          { core: "#fbbf24", ring: "#d97706", soft: "#1a1508", glow: "rgba(251,191,36,0.35)", status: "HAPPY",    accent: "#fde68a", particle: "#f59e0b" },
  curious:        { core: "#00f0ff", ring: "#0891b2", soft: "#051a22", glow: "rgba(0,240,255,0.28)", status: "OBSERVING", accent: "#22d3ee", particle: "#06b6d4" },
  concerned:      { core: "#ff6b6b", ring: "#ef4444", soft: "#1a0808", glow: "rgba(255,107,107,0.35)", status: "ALERT",   accent: "#fb7185", particle: "#f43f5e" },
  excited:        { core: "#ff2d78", ring: "#e11d48", soft: "#1a0512", glow: "rgba(255,45,120,0.40)", status: "EXCITED",  accent: "#fb7185", particle: "#ec4899" },
  music_vibe:     { core: "#e879f9", ring: "#22d3ee", soft: "#0a0520", glow: "rgba(232,121,249,0.35)", status: "VIBING",  accent: "#facc15", particle: "#d946ef" },
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

/* ── particles ──────────────────────────────────────────── */

function generateParticles(count: number) {
  return Array.from({ length: count }, (_, i) => ({
    id: i,
    angle: Math.random() * 360,
    radius: 100 + Math.random() * 60,
    size: 1 + Math.random() * 2.5,
    speed: 8 + Math.random() * 20,
    delay: Math.random() * 6,
    opacity: 0.3 + Math.random() * 0.5,
  }));
}

/* ── component ──────────────────────────────────────────── */

export function NOVACore() {
  const avatarState = useAvatarStore((s) => s.state);
  const speechText = useAvatarStore((s) => s.speechText);
  const emotion = useAvatarStore((s) => s.emotion);
  const appStatus = useAppStore((s) => s.status);
  const currentPage = useAppStore((s) => s.currentPage);
  const musicPlaying = appStatus.musicPlaying;

  const mode = resolveCoreMode(
    avatarState,
    appStatus.backendConnected,
    appStatus.avatarStreamConnected,
    currentPage,
    musicPlaying,
  );
  const v = STATE_VISUALS[mode] ?? STATE_VISUALS.monitoring;
  const particles = useMemo(() => generateParticles(30), []);
  const isActive = mode !== "offline" && mode !== "sleeping";
  const isSpeaking = mode === "speaking";
  const isListening = mode === "listening";
  const isThinking = mode === "thinking" || mode === "processing";

  /* glitch text effect */
  const [glitch, setGlitch] = useState(false);
  useEffect(() => {
    const timer = setInterval(() => {
      setGlitch(true);
      setTimeout(() => setGlitch(false), 100 + Math.random() * 80);
    }, 3000 + Math.random() * 4000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="relative flex flex-col items-center justify-center select-none" style={{ minHeight: 420 }}>
      {/* background radial glow */}
      <div
        className="absolute inset-0 transition-all duration-700"
        style={{
          background: `radial-gradient(ellipse at 50% 45%, ${v.glow} 0%, transparent 65%)`,
        }}
      />

      {/* scan lines overlay */}
      <div
        className="absolute inset-0 pointer-events-none opacity-[0.03]"
        style={{
          backgroundImage: `repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(255,255,255,0.05) 2px, rgba(255,255,255,0.05) 4px)`,
        }}
      />

      {/* orbiting particles */}
      <div className="absolute" style={{ width: 360, height: 360 }}>
        {particles.map((p) => (
          <motion.div
            key={p.id}
            className="absolute rounded-full"
            style={{
              width: p.size,
              height: p.size,
              background: v.particle,
              boxShadow: `0 0 ${p.size * 3}px ${v.particle}`,
              left: "50%",
              top: "50%",
              transformOrigin: "center center",
            }}
            animate={{
              rotate: [p.angle, p.angle + 360],
              x: [Math.cos((p.angle * Math.PI) / 180) * p.radius, Math.cos(((p.angle + 360) * Math.PI) / 180) * p.radius],
              y: [Math.sin((p.angle * Math.PI) / 180) * p.radius, Math.sin(((p.angle + 360) * Math.PI) / 180) * p.radius],
              opacity: [p.opacity * 0.4, p.opacity, p.opacity * 0.4],
            }}
            transition={{
              duration: p.speed,
              delay: p.delay,
              repeat: Infinity,
              ease: "linear",
            }}
          />
        ))}
      </div>

      {/* main orb container */}
      <div className="relative" style={{ width: 280, height: 280 }}>
        {/* outer ring — neon glow */}
        <motion.div
          className="absolute inset-0 rounded-full"
          style={{
            border: `2px solid ${v.ring}`,
            boxShadow: `0 0 20px ${v.glow}, inset 0 0 20px ${v.glow}, 0 0 60px ${v.glow}`,
          }}
          animate={{
            scale: isActive ? [1, 1.02, 1] : 1,
            opacity: isActive ? [0.7, 1, 0.7] : 0.3,
          }}
          transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
        />

        {/* second ring — thinner, offset rotation */}
        <motion.div
          className="absolute rounded-full"
          style={{
            inset: 16,
            border: `1px solid ${v.accent}40`,
            boxShadow: `0 0 12px ${v.accent}20`,
          }}
          animate={{ rotate: [0, 360] }}
          transition={{ duration: 25, repeat: Infinity, ease: "linear" }}
        />

        {/* third ring — dashed */}
        <motion.div
          className="absolute rounded-full"
          style={{
            inset: 32,
            border: `1px dashed ${v.accent}30`,
          }}
          animate={{ rotate: [360, 0] }}
          transition={{ duration: 35, repeat: Infinity, ease: "linear" }}
        />

        {/* core sphere */}
        <motion.div
          className="absolute rounded-full"
          style={{
            inset: 48,
            background: `radial-gradient(circle at 40% 35%, ${v.core}dd, ${v.core}88 45%, ${v.ring}44 70%, transparent)`,
            boxShadow: `
              0 0 40px ${v.core}60,
              0 0 80px ${v.core}30,
              inset 0 0 30px ${v.core}40,
              inset 0 -20px 40px ${v.ring}20
            `,
          }}
          animate={{
            scale: isSpeaking ? [1, 1.08, 0.96, 1.05, 1] : isListening ? [1, 1.04, 1] : isThinking ? [1, 1.02, 1] : [1, 1.01, 1],
          }}
          transition={{
            duration: isSpeaking ? 0.8 : isListening ? 1.8 : 2.5,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        >
          {/* inner plasma shimmer */}
          <motion.div
            className="absolute inset-2 rounded-full"
            style={{
              background: `conic-gradient(from 0deg, ${v.core}00, ${v.accent}40, ${v.core}00, ${v.accent}20, ${v.core}00)`,
              mixBlendMode: "screen",
            }}
            animate={{ rotate: [0, 360] }}
            transition={{ duration: 6, repeat: Infinity, ease: "linear" }}
          />

          {/* highlight spot */}
          <div
            className="absolute rounded-full"
            style={{
              width: 24,
              height: 24,
              top: "22%",
              left: "28%",
              background: `radial-gradient(circle, rgba(255,255,255,0.4), transparent)`,
              filter: "blur(6px)",
            }}
          />
        </motion.div>

        {/* listening wave rings */}
        <AnimatePresence>
          {isListening && (
            <>
              {[0, 1, 2].map((i) => (
                <motion.div
                  key={`wave-${i}`}
                  className="absolute inset-0 rounded-full"
                  style={{
                    border: `1px solid ${v.core}`,
                  }}
                  initial={{ scale: 0.7, opacity: 0.6 }}
                  animate={{ scale: [0.7, 1.4], opacity: [0.5, 0] }}
                  exit={{ opacity: 0 }}
                  transition={{
                    duration: 2,
                    delay: i * 0.6,
                    repeat: Infinity,
                    ease: "easeOut",
                  }}
                />
              ))}
            </>
          )}
        </AnimatePresence>

        {/* speaking pulse rings */}
        <AnimatePresence>
          {isSpeaking && (
            <>
              {[0, 1].map((i) => (
                <motion.div
                  key={`speak-${i}`}
                  className="absolute rounded-full"
                  style={{
                    inset: -8 - i * 12,
                    border: `1.5px solid ${v.core}80`,
                    boxShadow: `0 0 15px ${v.core}30`,
                  }}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: [0.4, 0.8, 0.4], scale: [0.98, 1.03, 0.98] }}
                  exit={{ opacity: 0 }}
                  transition={{
                    duration: 1.2,
                    delay: i * 0.4,
                    repeat: Infinity,
                    ease: "easeInOut",
                  }}
                />
              ))}
            </>
          )}
        </AnimatePresence>

        {/* thinking orbit dots */}
        <AnimatePresence>
          {isThinking && (
            <motion.div
              className="absolute inset-0"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1, rotate: [0, 360] }}
              exit={{ opacity: 0 }}
              transition={{ rotate: { duration: 4, repeat: Infinity, ease: "linear" }, opacity: { duration: 0.3 } }}
            >
              {[0, 120, 240].map((deg) => {
                const rad = (deg * Math.PI) / 180;
                return (
                  <div
                    key={deg}
                    className="absolute rounded-full"
                    style={{
                      width: 6,
                      height: 6,
                      background: v.accent,
                      boxShadow: `0 0 10px ${v.accent}`,
                      left: `calc(50% + ${Math.cos(rad) * 125}px)`,
                      top: `calc(50% + ${Math.sin(rad) * 125}px)`,
                      transform: "translate(-50%, -50%)",
                    }}
                  />
                );
              })}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* status label */}
      <motion.div
        className="mt-6 flex items-center gap-2"
        animate={{ opacity: [0.7, 1, 0.7] }}
        transition={{ duration: 2.5, repeat: Infinity }}
      >
        <div
          className="w-2 h-2 rounded-full"
          style={{
            background: v.core,
            boxShadow: `0 0 8px ${v.core}`,
          }}
        />
        <span
          className={`font-mono text-xs tracking-[0.25em] uppercase transition-all duration-300 ${glitch ? "translate-x-[1px] skew-x-2" : ""}`}
          style={{ color: v.accent }}
        >
          {v.status}
        </span>
      </motion.div>

      {/* speech bubble */}
      <AnimatePresence>
        {speechText && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.2 }}
            className="mt-3 max-w-xs px-4 py-2 rounded-xl text-center text-sm"
            style={{
              color: v.accent,
              background: `${v.soft}cc`,
              border: `1px solid ${v.accent}30`,
              backdropFilter: "blur(8px)",
              boxShadow: `0 0 20px ${v.glow}`,
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
            className="mt-2 px-3 py-0.5 rounded-full text-[10px] font-mono uppercase tracking-widest border"
            style={{
              color: v.accent,
              borderColor: `${v.accent}40`,
              background: `${v.soft}88`,
            }}
          >
            {emotion}
          </motion.span>
        )}
      </AnimatePresence>
    </div>
  );
}
