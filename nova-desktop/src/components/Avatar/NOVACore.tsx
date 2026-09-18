import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useAvatarStore } from "@/stores/useAvatarStore";
import type { AvatarState } from "@/types";

type StateVisual = {
  core: string;
  ring: string;
  soft: string;
  glow: string;
  status: string;
};

const STATE_VISUALS: Record<AvatarState, StateVisual> = {
  idle: { core: "#33b5f8", ring: "#2ca7ea", soft: "#153447", glow: "rgba(51,181,248,0.30)", status: "STANDING BY" },
  listening: { core: "#2dff88", ring: "#19d56e", soft: "#102f23", glow: "rgba(45,255,136,0.42)", status: "AUDIO INTAKE" },
  thinking: { core: "#a35bff", ring: "#7a35de", soft: "#271542", glow: "rgba(163,91,255,0.44)", status: "NEURAL PROCESS" },
  speaking: { core: "#ff9a2f", ring: "#ff7812", soft: "#44240f", glow: "rgba(255,154,47,0.44)", status: "VOICE OUTPUT" },
  sleeping: { core: "#5b7f93", ring: "#43697f", soft: "#162634", glow: "rgba(91,127,147,0.30)", status: "LOW POWER" },
  focused: { core: "#58cbff", ring: "#35b2ef", soft: "#14384f", glow: "rgba(88,203,255,0.34)", status: "TARGET LOCK" },
  relaxed: { core: "#6fd7ff", ring: "#42bceb", soft: "#18384a", glow: "rgba(111,215,255,0.32)", status: "STABLE FLOW" },
  proud: { core: "#69d2ff", ring: "#37b8ef", soft: "#17384d", glow: "rgba(105,210,255,0.34)", status: "TASK COMPLETE" },
  shy: { core: "#66c7f4", ring: "#35aadc", soft: "#183044", glow: "rgba(102,199,244,0.30)", status: "LOW VISIBILITY" },
  happy: { core: "#75dbff", ring: "#3cc1ef", soft: "#1a3950", glow: "rgba(117,219,255,0.34)", status: "POSITIVE SIGNAL" },
  curious: { core: "#72d8ff", ring: "#3ebbe9", soft: "#17384d", glow: "rgba(114,216,255,0.34)", status: "SCAN EXPANDING" },
  concerned: { core: "#7fd4ff", ring: "#50b9eb", soft: "#1d3750", glow: "rgba(127,212,255,0.34)", status: "ANOMALY WATCH" },
  excited: { core: "#86e7ff", ring: "#49cef3", soft: "#1a4256", glow: "rgba(134,231,255,0.40)", status: "AMPLIFIED MODE" },
};

function hexPath(size: number): string {
  const points = Array.from({ length: 6 }, (_, i) => {
    const angle = ((Math.PI * 2) / 6) * i - Math.PI / 6;
    return `${Math.cos(angle) * size},${Math.sin(angle) * size}`;
  });
  return `M${points.join("L")}Z`;
}

function pointOnCircle(radius: number, degrees: number) {
  const rad = (degrees * Math.PI) / 180;
  return { x: Math.cos(rad) * radius, y: Math.sin(rad) * radius };
}

export function NOVACore() {
  const avatarState = useAvatarStore((s) => s.state);
  const speechText = useAvatarStore((s) => s.speechText);
  const emotion = useAvatarStore((s) => s.emotion);

  const [speakingVisualLatch, setSpeakingVisualLatch] = useState(false);
  const [speechPulseHold, setSpeechPulseHold] = useState(false);

  useEffect(() => {
    if (avatarState === "speaking") {
      setSpeakingVisualLatch(true);
      return;
    }

    if (avatarState === "idle" && !speechText?.trim()) {
      setSpeakingVisualLatch(false);
      return;
    }

    const timer = setTimeout(() => setSpeakingVisualLatch(false), 1800);
    return () => clearTimeout(timer);
  }, [avatarState, speechText]);

  useEffect(() => {
    if (!speechText?.trim()) return;

    setSpeechPulseHold(true);
    const timer = setTimeout(() => setSpeechPulseHold(false), 2200);
    return () => clearTimeout(timer);
  }, [speechText]);

  useEffect(() => {
    if (avatarState === "idle" && !speechText?.trim()) {
      setSpeechPulseHold(false);
    }
  }, [avatarState, speechText]);

  const speakingPhaseActive = avatarState === "speaking" || speakingVisualLatch || speechPulseHold;
  const visualState: AvatarState = speakingPhaseActive ? "speaking" : avatarState;
  const visual = STATE_VISUALS[visualState] ?? STATE_VISUALS.idle;
  const isActive = visualState !== "idle" && visualState !== "sleeping";
  const isSpeaking = speakingPhaseActive;
  const pulseSpeed = isSpeaking ? 0.68 : avatarState === "thinking" ? 1.15 : 1.7;

  const stars = useMemo(
    () =>
      Array.from({ length: 90 }, (_, i) => ({
        id: i,
        x: Math.random() * 100,
        y: Math.random() * 100,
        size: 1 + Math.random() * 2,
        opacity: 0.1 + Math.random() * 0.5,
        duration: 3 + Math.random() * 4,
      })),
    [],
  );

  const hexNodes = useMemo(
    () =>
      Array.from({ length: 18 }, (_, i) => {
        const angle = (360 / 18) * i;
        return { id: i, ...pointOnCircle(122, angle) };
      }),
    [],
  );

  const plasmaFilaments = useMemo(
    () =>
      Array.from({ length: 5 }, (_, i) => {
        const angle = (360 / 5) * i;
        const radius = 14 + ((i * 9) % 28);
        const pos = pointOnCircle(radius, angle);
        return {
          id: i,
          x: pos.x,
          y: pos.y,
          rx: 8 + (i % 3) * 3,
          ry: 4 + (i % 2) * 2,
          drift: 5 + (i % 4),
          duration: 3.2 + (i % 5) * 0.5,
          delay: i * 0.2,
          angle,
        };
      }),
    [],
  );

  const listeningTicks = useMemo(
    () =>
      Array.from({ length: 24 }, (_, i) => ({
        id: i,
        angle: i * 15,
        long: i % 3 === 0,
      })),
    [],
  );

  const thinkingDots = useMemo(
    () =>
      Array.from({ length: 18 }, (_, i) => {
        const angle = i * 20;
        const radius = 98 + (i % 5) * 9;
        const p = pointOnCircle(radius, angle);
        return {
          id: i,
          x: p.x,
          y: p.y,
          size: 2.8 + (i % 3) * 1.35,
          phase: i * 0.16,
        };
      }),
    [],
  );

  const speakingBeads = useMemo(
    () =>
      Array.from({ length: 28 }, (_, i) => {
        const angle = i * (360 / 28);
        const p = pointOnCircle(124, angle);
        return {
          id: i,
          x: p.x,
          y: p.y,
          size: 3 + (i % 4) * 1.1,
          delay: i * 0.06,
        };
      }),
    [],
  );

  return (
    <div className="relative h-full w-full select-none overflow-hidden bg-[#070d1a]">
      <motion.div
        className="absolute inset-0"
        style={{
          background: `radial-gradient(circle at 50% 44%, ${visual.glow}, rgba(6,12,24,0.94) 62%, #050913 100%)`,
        }}
        animate={{ opacity: [0.9, 1, 0.9] }}
        transition={{ duration: isSpeaking ? 1.6 : 3.6, repeat: Infinity, ease: "easeInOut" }}
      />

      <div className="absolute inset-0 pointer-events-none">
        {stars.map((s) => (
          <motion.span
            key={s.id}
            className="absolute rounded-full bg-[#73d7ff]"
            style={{
              left: `${s.x}%`,
              top: `${s.y}%`,
              width: `${s.size}px`,
              height: `${s.size}px`,
              opacity: s.opacity,
            }}
            animate={{ opacity: [s.opacity * 0.62, s.opacity, s.opacity * 0.62] }}
            transition={{ duration: s.duration + 1.4, repeat: Infinity, ease: "easeInOut" }}
          />
        ))}
      </div>

      <div className="relative z-10 flex h-full flex-col items-center justify-center px-6">
        <motion.div
          className="pointer-events-none absolute left-1/2 top-1/2 h-[300px] w-[300px] -translate-x-1/2 -translate-y-1/2 rounded-full"
          style={{
            background: `radial-gradient(circle, ${visual.glow} 0%, rgba(20,70,96,0.28) 52%, rgba(7,13,26,0) 78%)`,
            filter: "blur(22px)",
            mixBlendMode: "screen",
          }}
          animate={{ scale: [0.97, isSpeaking ? 1.12 : 1.06, 0.97], opacity: [0.4, isSpeaking ? 0.72 : 0.62, 0.4] }}
          transition={{ duration: isSpeaking ? 0.9 : pulseSpeed, repeat: Infinity, ease: "easeInOut" }}
        />

        <motion.div
          className="relative"
          animate={{ filter: `drop-shadow(0 0 26px ${visual.glow})` }}
          transition={{ duration: 0.45 }}
        >
          <svg width={390} height={390} viewBox="-195 -195 390 390" style={{ overflow: "visible" }}>
            <defs>
              <radialGradient id="nova-core-grad" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="#aef0ff" stopOpacity="1" />
                <stop offset="40%" stopColor={visual.core} stopOpacity="0.9" />
                <stop offset="100%" stopColor={visual.ring} stopOpacity="0" />
              </radialGradient>

              <radialGradient id="nova-plasma-haze" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="#c1f4ff" stopOpacity="0.85" />
                <stop offset="40%" stopColor={visual.core} stopOpacity="0.42" />
                <stop offset="100%" stopColor={visual.ring} stopOpacity="0" />
              </radialGradient>

              <radialGradient id="nova-plasma-depth" cx="40%" cy="35%" r="68%">
                <stop offset="0%" stopColor="#b6f1ff" stopOpacity="0.55" />
                <stop offset="48%" stopColor={visual.core} stopOpacity="0.3" />
                <stop offset="100%" stopColor="#02101e" stopOpacity="0.08" />
              </radialGradient>

              <filter id="nova-plasma-blur" x="-150%" y="-150%" width="400%" height="400%">
                <feGaussianBlur stdDeviation="5.2" />
              </filter>

              <filter id="nova-plasma-distort" x="-160%" y="-160%" width="420%" height="420%">
                <feTurbulence type="fractalNoise" baseFrequency="0.017 0.032" numOctaves="3" seed="7" result="noise">
                  <animate attributeName="baseFrequency" values="0.014 0.028;0.021 0.038;0.014 0.028" dur="8s" repeatCount="indefinite" />
                </feTurbulence>
                <feDisplacementMap in="SourceGraphic" in2="noise" scale="10" xChannelSelector="R" yChannelSelector="G" />
              </filter>

              <mask id="nova-core-mask">
                <circle cx={0} cy={0} r={58} fill="white" />
              </mask>
            </defs>

            <motion.circle
              cx={0}
              cy={0}
              r={154}
              fill="none"
              stroke={visual.ring}
              strokeWidth={1}
              strokeDasharray="6 12"
              opacity={0.2}
              animate={{
                strokeDashoffset: [0, -240],
                opacity: [0.16, 0.26, 0.16],
                scale: isSpeaking ? [1, 1.03, 1] : 1,
              }}
              transition={{ duration: isSpeaking ? 5.2 : 9.8, repeat: Infinity, ease: "linear" }}
            />
            <motion.circle
              cx={0}
              cy={0}
              r={136}
              fill="none"
              stroke={visual.ring}
              strokeWidth={1}
              strokeDasharray="2 10"
              opacity={0.26}
              animate={{
                strokeDashoffset: [0, 280],
                opacity: [0.2, 0.34, 0.2],
                scale: isSpeaking ? [1, 1.04, 1] : 1,
              }}
              transition={{ duration: isSpeaking ? 4.2 : 7.8, repeat: Infinity, ease: "linear" }}
            />
            <motion.circle
              cx={0}
              cy={0}
              r={112}
              fill="none"
              stroke={visual.ring}
              strokeWidth={2}
              strokeDasharray="12 6"
              opacity={0.42}
              animate={{
                strokeDashoffset: [0, -160],
                scale: isSpeaking ? [1, 1.05, 1] : 1,
                opacity: isSpeaking ? [0.42, 0.62, 0.42] : 0.42,
              }}
              transition={{ duration: isSpeaking ? 2.6 : 12.4, repeat: Infinity, ease: isSpeaking ? "easeInOut" : "linear" }}
            />
            <motion.circle
              cx={0}
              cy={0}
              r={89}
              fill="none"
              stroke={visual.ring}
              strokeWidth={2}
              strokeDasharray="10 8"
              opacity={0.5}
              animate={{
                strokeDashoffset: [0, 140],
                scale: isSpeaking ? [1, 1.06, 1] : 1,
                opacity: isSpeaking ? [0.5, 0.7, 0.5] : 0.5,
              }}
              transition={{ duration: isSpeaking ? 2.2 : 8.6, repeat: Infinity, ease: isSpeaking ? "easeInOut" : "linear" }}
            />
            <circle cx={0} cy={0} r={64} fill="none" stroke={visual.ring} strokeWidth={1.6} opacity={0.52} />
            <circle cx={0} cy={0} r={50} fill="none" stroke={visual.ring} strokeWidth={1.2} opacity={0.36} />

            {hexNodes.map((h) => (
              <path
                key={h.id}
                d={hexPath(9)}
                transform={`translate(${h.x},${h.y})`}
                fill="none"
                stroke={visual.ring}
                strokeWidth={0.9}
                opacity={0.18}
              />
            ))}

            {[0, 90, 180, 270].map((deg) => {
              const p1 = pointOnCircle(95, deg);
              const p2 = pointOnCircle(104, deg);
              return <line key={deg} x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y} stroke={visual.core} strokeWidth={2.1} opacity={0.78} />;
            })}

            {visualState === "listening" && (
              <motion.g animate={{ opacity: [0.72, 1, 0.72] }} transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}>
                {listeningTicks.map((t) => {
                  const inner = pointOnCircle(96, t.angle);
                  const outer = pointOnCircle(t.long ? 132 : 120, t.angle);
                  return (
                    <motion.line
                      key={`listen-tick-${t.id}`}
                      x1={inner.x}
                      y1={inner.y}
                      x2={outer.x}
                      y2={outer.y}
                      stroke={visual.core}
                      strokeWidth={t.long ? 3.2 : 2.2}
                      strokeLinecap="round"
                      opacity={0.74}
                      animate={{ opacity: [0.3, 0.9, 0.3] }}
                      transition={{ duration: 1.2, repeat: Infinity, delay: t.id * 0.04, ease: "easeInOut" }}
                    />
                  );
                })}
              </motion.g>
            )}

            {visualState === "thinking" && (
              <motion.g animate={{ rotate: [0, 360] }} transition={{ duration: 22, repeat: Infinity, ease: "linear" }}>
                {thinkingDots.map((d) => (
                  <motion.circle
                    key={`think-dot-${d.id}`}
                    cx={d.x}
                    cy={d.y}
                    r={d.size}
                    fill={visual.core}
                    opacity={0.5}
                    animate={{ opacity: [0.2, 0.76, 0.2], scale: [0.8, 1.2, 0.8] }}
                    transition={{ duration: 2.4, repeat: Infinity, delay: d.phase, ease: "easeInOut" }}
                  />
                ))}
              </motion.g>
            )}

            {isSpeaking && (
              <motion.g animate={{ rotate: [0, 360] }} transition={{ duration: 4.6, repeat: Infinity, ease: "linear" }}>
                {speakingBeads.map((b) => (
                  <motion.circle
                    key={`speak-bead-${b.id}`}
                    cx={b.x}
                    cy={b.y}
                    r={b.size}
                    fill={visual.core}
                    opacity={0.56}
                    animate={{ opacity: [0.38, 0.82, 0.38], scale: [0.9, 1.18, 0.9] }}
                    transition={{ duration: 1.45, repeat: Infinity, delay: b.delay, ease: "easeInOut" }}
                  />
                ))}
              </motion.g>
            )}

            {isActive && !isSpeaking && (
              <motion.g animate={{ rotate: 360 }} transition={{ duration: avatarState === "thinking" ? 8 : 4.6, repeat: Infinity, ease: "linear" }}>
                <line x1={0} y1={0} x2={148} y2={0} stroke={visual.core} strokeWidth={1.4} opacity={0.55} />
                <circle cx={148} cy={0} r={3.2} fill={visual.core} opacity={0.88} />
              </motion.g>
            )}

            <motion.g
              animate={{ opacity: [0.58, 0.84, 0.58], scale: [1, 1.07, 1] }}
              transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
            >
              <circle cx={0} cy={0} r={58} fill={visual.soft} opacity={0.74} />
            </motion.g>

            <g mask="url(#nova-core-mask)">
              <rect x={-58} y={-58} width={116} height={116} fill="url(#nova-plasma-depth)" opacity={0.72} />

              <motion.g
                animate={{ rotate: 360 }}
                transition={{ duration: isSpeaking ? 8 : 14, repeat: Infinity, ease: "linear" }}
                filter="url(#nova-plasma-distort)"
              >
                {plasmaFilaments.map((f) => (
                  <motion.g
                    key={f.id}
                    transform={`translate(${f.x},${f.y})`}
                    animate={{
                      x: [-f.drift, f.drift, -f.drift],
                      y: [f.drift * 0.6, -f.drift * 0.6, f.drift * 0.6],
                      rotate: [f.angle - 20, f.angle + 18, f.angle - 20],
                      opacity: [0.14, isSpeaking ? 0.46 : 0.34, 0.14],
                    }}
                    transition={{ duration: f.duration, delay: f.delay, repeat: Infinity, ease: "easeInOut" }}
                  >
                    <ellipse cx={0} cy={0} rx={f.rx} ry={f.ry} fill={visual.core} filter="url(#nova-plasma-blur)" />
                  </motion.g>
                ))}
              </motion.g>
            </g>

            <motion.g
              animate={{ opacity: [0.72, 1, 0.72], scale: [1, isSpeaking ? 1.22 : 1.14, 1] }}
              transition={{ duration: isSpeaking ? 1.05 : pulseSpeed, repeat: Infinity, ease: "easeInOut" }}
            >
              <circle cx={0} cy={0} r={40} fill="url(#nova-core-grad)" />
            </motion.g>

            <motion.circle
              cx={0}
              cy={0}
              r={53}
              fill="url(#nova-plasma-haze)"
              animate={{ opacity: [0.16, isSpeaking ? 0.4 : 0.3, 0.16], scale: [0.98, isSpeaking ? 1.06 : 1.03, 0.98] }}
              transition={{ duration: isSpeaking ? 1.12 : 2.2, repeat: Infinity, ease: "easeInOut" }}
            />

            {isSpeaking ? (
              <>
                {[0, 1, 2].map((i) => (
                  <motion.g
                    key={`speak-inner-oval-${i}`}
                    animate={{
                      scaleX: [1.04, 1.34 + i * 0.07, 0.92, 1.04],
                      scaleY: [0.98, 0.7, 1.08 + i * 0.04, 0.98],
                      rotate: [0, 8 + i * 2, -8 - i * 2, 0],
                      opacity: [0.3, 0.86, 0.4, 0.3],
                    }}
                    transition={{ duration: 1.08 + i * 0.14, repeat: Infinity, ease: "easeInOut", delay: i * 0.1 }}
                  >
                    <ellipse
                      cx={0}
                      cy={0}
                      rx={26 + i * 6}
                      ry={14 + i * 3}
                      fill="none"
                      stroke={visual.core}
                      strokeWidth={i === 0 ? 2 : 1.4}
                      strokeDasharray={i === 0 ? "10 8" : "8 10"}
                    />
                  </motion.g>
                ))}
              </>
            ) : (
              <>
                <motion.circle
                  cx={0}
                  cy={0}
                  r={30}
                  fill="none"
                  stroke={visual.core}
                  strokeWidth={1.2}
                  opacity={0.42}
                  animate={{ rotate: [0, 360], strokeDashoffset: [0, -120] }}
                  transition={{ duration: 6.2, repeat: Infinity, ease: "linear" }}
                  strokeDasharray="8 10"
                />

                <motion.circle
                  cx={0}
                  cy={0}
                  r={20}
                  fill="none"
                  stroke={visual.core}
                  strokeWidth={2.6}
                  opacity={0.9}
                  animate={{ scale: [1, 1.03, 1] }}
                  transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
                />
              </>
            )}
            {!isSpeaking && (
              <motion.g
                animate={{ scale: [1, 1.14, 1] }}
                transition={{ duration: 1.7, repeat: Infinity, ease: "easeInOut" }}
              >
                <circle cx={0} cy={0} r={9.5} fill={visual.core} />
              </motion.g>
            )}

            <line x1={-30} y1={0} x2={-12} y2={0} stroke={visual.core} strokeWidth={1.8} opacity={0.8} />
            <line x1={12} y1={0} x2={30} y2={0} stroke={visual.core} strokeWidth={1.8} opacity={0.8} />
            <line x1={0} y1={-30} x2={0} y2={-12} stroke={visual.core} strokeWidth={1.8} opacity={0.8} />
            <line x1={0} y1={12} x2={0} y2={30} stroke={visual.core} strokeWidth={1.8} opacity={0.8} />
          </svg>
        </motion.div>

        <div className="mt-8 flex w-full max-w-[560px] flex-col items-center gap-2">
          <div className="flex items-center gap-3">
            <motion.span
              className="h-2.5 w-2.5 rounded-full"
              style={{ background: visual.core }}
              animate={{ opacity: [1, 0.35, 1] }}
              transition={{ duration: 1.2, repeat: Infinity }}
            />
            <span className="text-[12px] font-mono font-bold uppercase tracking-[0.35em]" style={{ color: visual.core }}>
              {visual.status}
            </span>
          </div>

          <AnimatePresence>
            {speechText ? (
              <motion.div
                key="speech"
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.24, ease: "easeOut" }}
                className="w-full max-h-[140px] overflow-y-auto rounded-xl border px-4 py-2.5 text-left text-[13px] leading-relaxed whitespace-pre-wrap"
                style={{
                  borderColor: `${visual.core}66`,
                  background: "rgba(9, 26, 42, 0.75)",
                  color: visual.core,
                  boxShadow: `0 0 24px ${visual.glow}`,
                }}
              >
                {speechText}
              </motion.div>
            ) : null}
          </AnimatePresence>

          <AnimatePresence>
            {emotion && emotion !== "neutral" && (
              <motion.span
                key={emotion}
                initial={{ opacity: 0, scale: 0.86 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.86 }}
                className="rounded-full border px-3 py-1 text-[10px] font-mono uppercase tracking-[0.22em]"
                style={{ borderColor: `${visual.ring}90`, color: visual.ring, background: "rgba(10, 33, 50, 0.5)" }}
              >
                {emotion}
              </motion.span>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
