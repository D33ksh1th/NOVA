import { motion, AnimatePresence } from "framer-motion";
import { useMemo } from "react";

const BAR_COUNT = 48;
const RING_COUNT = 3;

const COLORS = [
  "#a78bfa", "#c084fc", "#e879f9", "#f472b6",
  "#818cf8", "#6366f1", "#8b5cf6", "#d946ef",
];

function randomBetween(a: number, b: number, seed: number) {
  const x = Math.sin(seed * 9301 + 49297) % 233280;
  return a + (Math.abs(x) / 233280) * (b - a);
}

export function MusicVisualizer({ visible }: { visible: boolean }) {
  const bars = useMemo(
    () =>
      Array.from({ length: BAR_COUNT }, (_, i) => ({
        angle: (i / BAR_COUNT) * 360,
        minH: randomBetween(8, 16, i),
        maxH: randomBetween(28, 60, i + 100),
        speed: randomBetween(0.3, 0.8, i + 200),
        delay: randomBetween(0, 0.5, i + 300),
        color: COLORS[i % COLORS.length],
      })),
    [],
  );

  const rings = useMemo(
    () =>
      Array.from({ length: RING_COUNT }, (_, i) => ({
        r: 90 + i * 22,
        speed: 12 + i * 8,
        dir: i % 2 === 0 ? 1 : -1,
        opacity: 0.12 - i * 0.03,
        dash: `${6 + i * 4} ${14 + i * 6}`,
      })),
    [],
  );

  const orbs = useMemo(
    () =>
      Array.from({ length: 6 }, (_, i) => ({
        angle: (i / 6) * 360,
        r: 110 + randomBetween(0, 30, i + 500),
        size: randomBetween(2, 5, i + 600),
        speed: randomBetween(6, 14, i + 700),
        delay: randomBetween(0, 3, i + 800),
        color: COLORS[(i * 2) % COLORS.length],
      })),
    [],
  );

  const CX = 180;
  const CY = 180;

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.9 }}
          transition={{ duration: 0.5 }}
          className="absolute inset-0 z-10 pointer-events-none flex items-center justify-center"
        >
          {/* Ambient purple glow */}
          <motion.div
            className="absolute rounded-full"
            style={{ width: 320, height: 320 }}
            animate={{
              boxShadow: [
                "0 0 60px 20px rgba(167,139,250,0.15), 0 0 120px 40px rgba(192,132,252,0.08)",
                "0 0 80px 30px rgba(232,121,249,0.18), 0 0 160px 60px rgba(167,139,250,0.1)",
                "0 0 60px 20px rgba(167,139,250,0.15), 0 0 120px 40px rgba(192,132,252,0.08)",
              ],
            }}
            transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
          />

          <svg viewBox="0 0 360 360" style={{ width: 360, height: 360 }}>
            <defs>
              <filter id="music-glow">
                <feGaussianBlur stdDeviation="3" />
                <feComposite in="SourceGraphic" operator="over" />
              </filter>
              <radialGradient id="music-center-grad">
                <stop offset="0%" stopColor="#c084fc" stopOpacity="0.25" />
                <stop offset="100%" stopColor="#c084fc" stopOpacity="0" />
              </radialGradient>
            </defs>

            {/* Rotating ring outlines */}
            {rings.map((ring, i) => (
              <motion.circle
                key={`ring-${i}`}
                cx={CX}
                cy={CY}
                r={ring.r}
                fill="none"
                stroke="#a78bfa"
                strokeWidth="0.6"
                strokeDasharray={ring.dash}
                opacity={ring.opacity}
                animate={{ rotate: [0, 360 * ring.dir] }}
                transition={{ duration: ring.speed, repeat: Infinity, ease: "linear" }}
                style={{ transformOrigin: `${CX}px ${CY}px` }}
              />
            ))}

            {/* Circular equalizer bars */}
            {bars.map((bar, i) => {
              const rad = (bar.angle * Math.PI) / 180;
              const innerR = 68;
              const x1 = CX + innerR * Math.cos(rad);
              const y1 = CY + innerR * Math.sin(rad);
              return (
                <motion.line
                  key={`bar-${i}`}
                  x1={x1}
                  y1={y1}
                  x2={x1}
                  y2={y1}
                  stroke={bar.color}
                  strokeWidth="2"
                  strokeLinecap="round"
                  filter="url(#music-glow)"
                  animate={{
                    x2: [
                      CX + (innerR + bar.minH) * Math.cos(rad),
                      CX + (innerR + bar.maxH) * Math.cos(rad),
                      CX + (innerR + bar.minH * 1.5) * Math.cos(rad),
                      CX + (innerR + bar.maxH * 0.7) * Math.cos(rad),
                      CX + (innerR + bar.minH) * Math.cos(rad),
                    ],
                    y2: [
                      CY + (innerR + bar.minH) * Math.sin(rad),
                      CY + (innerR + bar.maxH) * Math.sin(rad),
                      CY + (innerR + bar.minH * 1.5) * Math.sin(rad),
                      CY + (innerR + bar.maxH * 0.7) * Math.sin(rad),
                      CY + (innerR + bar.minH) * Math.sin(rad),
                    ],
                    opacity: [0.4, 0.9, 0.5, 0.85, 0.4],
                  }}
                  transition={{
                    duration: bar.speed,
                    delay: bar.delay,
                    repeat: Infinity,
                    ease: "easeInOut",
                  }}
                />
              );
            })}

            {/* Center glow */}
            <motion.circle
              cx={CX}
              cy={CY}
              r={30}
              fill="url(#music-center-grad)"
              animate={{ r: [28, 35, 28], opacity: [0.4, 0.7, 0.4] }}
              transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
            />

            {/* Orbiting particles */}
            {orbs.map((orb, i) => (
              <motion.circle
                key={`orb-${i}`}
                r={orb.size}
                fill={orb.color}
                filter="url(#music-glow)"
                animate={{
                  cx: [
                    CX + orb.r * Math.cos((orb.angle * Math.PI) / 180),
                    CX + orb.r * Math.cos(((orb.angle + 360) * Math.PI) / 180),
                  ],
                  cy: [
                    CY + orb.r * Math.sin((orb.angle * Math.PI) / 180),
                    CY + orb.r * Math.sin(((orb.angle + 360) * Math.PI) / 180),
                  ],
                  opacity: [0.3, 0.8, 0.3],
                }}
                transition={{
                  cx: { duration: orb.speed, delay: orb.delay, repeat: Infinity, ease: "linear" },
                  cy: { duration: orb.speed, delay: orb.delay, repeat: Infinity, ease: "linear" },
                  opacity: { duration: orb.speed / 3, repeat: Infinity, ease: "easeInOut" },
                }}
              />
            ))}

            {/* Pulsing beat ring */}
            <motion.circle
              cx={CX}
              cy={CY}
              r={65}
              fill="none"
              stroke="#c084fc"
              strokeWidth="1.5"
              filter="url(#music-glow)"
              animate={{
                r: [65, 72, 65],
                opacity: [0.2, 0.5, 0.2],
                strokeWidth: [1.5, 2.5, 1.5],
              }}
              transition={{ duration: 0.8, repeat: Infinity, ease: "easeInOut" }}
            />

            {/* Music note icon in center */}
            <motion.text
              x={CX}
              y={CY + 6}
              textAnchor="middle"
              fontSize="18"
              animate={{ opacity: [0.5, 1, 0.5], scale: [1, 1.1, 1] }}
              transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
              style={{ transformOrigin: `${CX}px ${CY}px` }}
            >
              🎵
            </motion.text>

            {/* Label */}
            <motion.text
              x={CX}
              y={330}
              textAnchor="middle"
              fontSize="8"
              fontFamily="JetBrains Mono, monospace"
              letterSpacing="4"
              fill="#c084fc"
              animate={{ opacity: [0.3, 0.7, 0.3] }}
              transition={{ duration: 2.5, repeat: Infinity }}
            >
              NOW PLAYING
            </motion.text>
          </svg>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
