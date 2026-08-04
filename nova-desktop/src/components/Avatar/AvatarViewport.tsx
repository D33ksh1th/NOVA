import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Canvas, useFrame } from "@react-three/fiber";
import {
  OrbitControls,
  Environment,
  ContactShadows,
  Float,
  useAnimations,
  Sphere,
  MeshDistortMaterial,
  Text,
  Billboard,
  useGLTF,
} from "@react-three/drei";
import * as THREE from "three";
import { clone } from "three/examples/jsm/utils/SkeletonUtils.js";
import { useAvatarStore } from "@/stores/useAvatarStore";
import type { AvatarState } from "@/types";
import { NovaEnvironmentProps } from "./NovaEnvironmentProps";
import { missingRequiredClips, resolveClipForState } from "@/avatar/runtimeSpec";

const DEFAULT_CAT_MODEL_URL = "/models/persian_cat.glb";

// ── Placeholder cat orb (Sprint 1) ─────────────────────────────────
// Sprint 2 will replace this with actual GLTF Persian cat model.
function PlaceholderCat({ avatarState }: { avatarState: AvatarState }) {
  const meshRef = useRef<THREE.Mesh>(null);
  const glowRef = useRef<THREE.Mesh>(null);

  const stateColors: Record<AvatarState, string> = {
    idle:      "#f97316",
    listening: "#10b981",
    thinking:  "#fbbf24",
    speaking:  "#f97316",
    sleeping:  "#8b5cf6",
    focused:   "#3b82f6",
    relaxed:   "#22c55e",
    proud:     "#f59e0b",
    shy:       "#a855f7",
    happy:     "#f59e0b",
    curious:   "#06b6d4",
    concerned: "#ef4444",
    excited:   "#ec4899",
  };

  const color = stateColors[avatarState] || "#f97316";

  useFrame((state) => {
    if (!meshRef.current || !glowRef.current) return;
    const t = state.clock.getElapsedTime();

    // Breathing / state-specific motion
    if (avatarState === "idle" || avatarState === "sleeping") {
      meshRef.current.scale.setScalar(1 + Math.sin(t * 1.2) * 0.02);
    } else if (avatarState === "thinking") {
      meshRef.current.rotation.y = Math.sin(t * 0.8) * 0.3;
    } else if (avatarState === "speaking") {
      meshRef.current.scale.setScalar(1 + Math.sin(t * 8) * 0.035);
    } else if (avatarState === "listening") {
      meshRef.current.rotation.y += 0.01;
    }

    glowRef.current.scale.setScalar(1.1 + Math.sin(t * 1.5) * 0.06);
  });

  return (
    <group>
      {/* Glow halo */}
      <Sphere ref={glowRef} args={[1.1, 32, 32]}>
        <meshBasicMaterial color={color} transparent opacity={0.05} />
      </Sphere>

      {/* Main body */}
      <Sphere ref={meshRef} args={[1, 64, 64]}>
        <MeshDistortMaterial
          color={color}
          distort={avatarState === "speaking" ? 0.45 : 0.2}
          speed={avatarState === "thinking" ? 4 : 1.5}
          roughness={0.3}
          metalness={0.1}
          emissive={color}
          emissiveIntensity={0.12}
        />
      </Sphere>

      {/* State label */}
      <Billboard position={[0, 1.6, 0]}>
        <Text
          fontSize={0.18}
          color="#ffffff"
          anchorX="center"
          anchorY="middle"
          font="https://fonts.gstatic.com/s/inter/v13/UcCO3FwrK3iLTeHuS_fvQtMwCp50KnMw2boKoduKmMEVuLyfAZ9hiA.woff2"
        >
          {avatarState.toUpperCase()}
        </Text>
      </Billboard>

      {/* Ears */}
      <EarPair state={avatarState} />
    </group>
  );
}

function EarPair({ state }: { state: AvatarState }) {
  const leftRef = useRef<THREE.Mesh>(null);
  const rightRef = useRef<THREE.Mesh>(null);

  useFrame((clock) => {
    const t = clock.clock.getElapsedTime();
    if (leftRef.current && rightRef.current) {
      const perk = state === "listening" ? 0.3 : 0;
      leftRef.current.rotation.z = 0.3 + perk + Math.sin(t * 2) * 0.02;
      rightRef.current.rotation.z = -0.3 - perk - Math.sin(t * 2) * 0.02;
    }
  });

  const earShape = new THREE.ConeGeometry(0.28, 0.5, 4);

  return (
    <>
      <mesh
        ref={leftRef}
        geometry={earShape}
        position={[-0.65, 0.88, 0]}
        rotation={[0, 0, 0.35]}
      >
        <meshStandardMaterial color="#c2602f" roughness={0.6} />
      </mesh>
      <mesh
        ref={rightRef}
        geometry={earShape}
        position={[0.65, 0.88, 0]}
        rotation={[0, 0, -0.35]}
      >
        <meshStandardMaterial color="#c2602f" roughness={0.6} />
      </mesh>
    </>
  );
}

function GLTFCat({
  avatarState,
  animationOverride,
  url,
}: {
  avatarState: AvatarState;
  animationOverride: string | null;
  url: string;
}) {
  const { scene, animations } = useGLTF(url);
  const modelRef = useRef<THREE.Group>(null);
  const headRef = useRef<THREE.Object3D | null>(null);
  const collarFoundRef = useRef(false);
  const clipWarningRef = useRef(false);
  const activeClipRef = useRef<string | null>(null);
  const stateTransitionTimerRef = useRef<number | null>(null);
  const prevAvatarStateRef = useRef<AvatarState>(avatarState);

  const model = useMemo(() => {
    const cloned = clone(scene) as THREE.Group;
    cloned.traverse((obj) => {
      if (obj instanceof THREE.Mesh) {
        obj.castShadow = true;
        obj.receiveShadow = true;
      }

      const n = obj.name.toLowerCase();
      if (!headRef.current && (n.includes("head") || n.includes("neck"))) {
        headRef.current = obj;
      }

      if (n.includes("collar") || n.includes("pendant") || n.includes("tag")) {
        collarFoundRef.current = true;
      }
    });
    return cloned;
  }, [scene]);

  const { actions, mixer } = useAnimations(animations, modelRef);

  useEffect(() => {
    const names = Object.keys(actions);
    if (!clipWarningRef.current && names.length > 0) {
      const missing = missingRequiredClips(names);
      if (missing.length > 0) {
        // Keep this as a console warning, not UI noise.
        console.warn("NOVA model is missing expected clips:", missing.slice(0, 8), missing.length > 8 ? `+${missing.length - 8} more` : "");
      }
      clipWarningRef.current = true;
    }
  }, [actions]);

  useEffect(() => {
    const available = Object.keys(actions);
    if (!available.length) return;

    const clipName = resolveClipForState(avatarState, available, animationOverride);
    if (!clipName) return;

    const applyClip = (nextClip: string) => {
      if (activeClipRef.current === nextClip) return;

      Object.entries(actions).forEach(([name, action]) => {
        if (!action) return;
        if (name === nextClip) {
          action.reset();
          action.setLoop(THREE.LoopRepeat, Infinity);
          action.fadeIn(0.32);
          action.play();
          return;
        }
        action.fadeOut(0.28);
      });

      activeClipRef.current = nextClip;
    };

    const isVoiceEdge =
      (prevAvatarStateRef.current === "speaking" && avatarState === "listening") ||
      (prevAvatarStateRef.current === "listening" && avatarState === "speaking");
    const delay = isVoiceEdge ? 120 : 50;

    if (stateTransitionTimerRef.current !== null) {
      window.clearTimeout(stateTransitionTimerRef.current);
      stateTransitionTimerRef.current = null;
    }

    stateTransitionTimerRef.current = window.setTimeout(() => {
      applyClip(clipName);
      stateTransitionTimerRef.current = null;
    }, delay);
    prevAvatarStateRef.current = avatarState;

    return () => {
      if (stateTransitionTimerRef.current !== null) {
        window.clearTimeout(stateTransitionTimerRef.current);
        stateTransitionTimerRef.current = null;
      }
    };
  }, [actions, avatarState, animationOverride]);

  useEffect(() => {
    return () => {
      if (stateTransitionTimerRef.current !== null) {
        window.clearTimeout(stateTransitionTimerRef.current);
        stateTransitionTimerRef.current = null;
      }
    };
  }, []);

  useFrame((clock) => {
    mixer.update(clock.clock.getDelta());

    const t = clock.clock.getElapsedTime();
    if (!modelRef.current) return;

    // Cursor/head tracking for "alive" behavior.
    if (headRef.current && avatarState !== "sleeping") {
      const targetYaw = Math.sin(t * 0.35) * 0.06;
      headRef.current.rotation.y = THREE.MathUtils.lerp(
        headRef.current.rotation.y,
        targetYaw,
        0.06
      );
    }

    if (avatarState === "idle" || avatarState === "sleeping") {
      modelRef.current.position.y = Math.sin(t * 1.2) * 0.03;
    } else if (avatarState === "listening") {
      modelRef.current.rotation.y = Math.sin(t * 1.8) * 0.16;
    } else if (avatarState === "thinking") {
      modelRef.current.rotation.z = Math.sin(t * 1.1) * 0.06;
    } else if (avatarState === "speaking") {
      modelRef.current.position.y = Math.sin(t * 7) * 0.04;
    }
  });

  return (
    <group ref={modelRef} position={[0, -1.6, 0]} scale={1.45}>
      <primitive object={model} />

      {/* Accessory fallback if model does not include collar/pendant */}
      {!collarFoundRef.current ? (
        <group position={[0, 0.72, 0.1]}>
          <mesh rotation={[Math.PI / 2, 0, 0]}>
            <torusGeometry args={[0.23, 0.018, 18, 48]} />
            <meshStandardMaterial color="#162033" roughness={0.72} metalness={0.25} />
          </mesh>
          <mesh position={[0, -0.18, 0.1]}>
            <sphereGeometry args={[0.035, 20, 20]} />
            <meshStandardMaterial color="#41d7ff" emissive="#41d7ff" emissiveIntensity={0.6} roughness={0.25} metalness={0.22} />
          </mesh>
          <mesh position={[0.07, -0.16, 0.1]}>
            <boxGeometry args={[0.08, 0.03, 0.01]} />
            <meshStandardMaterial color="#8f939c" roughness={0.45} metalness={0.72} />
          </mesh>
        </group>
      ) : null}
    </group>
  );
}

function useModelAvailability(url: string) {
  const [available, setAvailable] = useState(false);

  useEffect(() => {
    let active = true;
    fetch(url, { method: "HEAD" })
      .then((res) => {
        if (active) {
          setAvailable(res.ok);
        }
      })
      .catch(() => {
        if (active) {
          setAvailable(false);
        }
      });

    return () => {
      active = false;
    };
  }, [url]);

  return available;
}

// ── Main viewport ─────────────────────────────────────────────────
export function AvatarViewport() {
  const avatarState = useAvatarStore((s) => s.state);
  const animationOverride = useAvatarStore((s) => s.animationOverride);
  const modelUrl =
    import.meta.env.VITE_CAT_MODEL_URL?.trim() || DEFAULT_CAT_MODEL_URL;
  const hasModel = useModelAvailability(modelUrl);
  const [visualState, setVisualState] = useState<AvatarState>(avatarState);
  const visualStateTimerRef = useRef<number | null>(null);

  useEffect(() => {
    if (avatarState === visualState) return;

    // Soften frequent speaking/listening flips to reduce visible jitter.
    const isVoiceEdge =
      (visualState === "speaking" && avatarState === "listening") ||
      (visualState === "listening" && avatarState === "speaking");
    const delay = isVoiceEdge ? 120 : 60;

    if (visualStateTimerRef.current !== null) {
      window.clearTimeout(visualStateTimerRef.current);
      visualStateTimerRef.current = null;
    }

    visualStateTimerRef.current = window.setTimeout(() => {
      setVisualState(avatarState);
      visualStateTimerRef.current = null;
    }, delay);

    return () => {
      if (visualStateTimerRef.current !== null) {
        window.clearTimeout(visualStateTimerRef.current);
        visualStateTimerRef.current = null;
      }
    };
  }, [avatarState, visualState]);

  const bgColors: Record<AvatarState, [string, string]> = {
    idle:      ["#0f172a", "#1a1f35"],
    listening: ["#0f1f17", "#0d2018"],
    thinking:  ["#1a1408", "#1f1a08"],
    speaking:  ["#1a0d0a", "#200e0a"],
    sleeping:  ["#120d1f", "#180f2a"],
    focused:   ["#0b1a24", "#102133"],
    relaxed:   ["#122016", "#1b2a20"],
    proud:     ["#1d1210", "#291611"],
    shy:       ["#17131f", "#21172a"],
    happy:     ["#1a1408", "#1a1205"],
    curious:   ["#080f1a", "#091525"],
    concerned: ["#1a0a0a", "#200808"],
    excited:   ["#1a0810", "#200810"],
  };

  const [bgA, bgB] = bgColors[visualState] ?? bgColors.idle;

  return (
    <div
      className="relative w-full h-full rounded-2xl overflow-hidden transition-colors duration-700"
      style={{
        background: `radial-gradient(ellipse at 40% 30%, ${bgA}, ${bgB})`,
      }}
    >
      {/* Three.js canvas */}
      <Canvas
        camera={{ position: [0, 0, 4.5], fov: 45 }}
        gl={{ antialias: true, alpha: true }}
        style={{ position: "absolute", inset: 0 }}
      >
        <Suspense fallback={null}>
          {/* Lighting */}
          <ambientLight intensity={0.4} />
          <directionalLight
            position={[3, 8, 5]}
            intensity={1.4}
            color="#fff7e8"
            castShadow
          />
          <pointLight position={[-4, 2, -2]} intensity={0.5} color="#ff8040" />
          <pointLight
            position={[0, -2, 3]}
            intensity={0.3}
            color={
              visualState === "listening"
                ? "#10b981"
                : visualState === "thinking"
                ? "#fbbf24"
                : "#f97316"
            }
          />

          {/* Environment */}
          <Environment preset="city" />

          {/* Companion prop set from avatar specification */}
          <NovaEnvironmentProps />

          {/* Sprint 2: Prefer GLTF cat model, keep placeholder fallback */}
          {hasModel ? (
            <GLTFCat
              avatarState={visualState}
              animationOverride={animationOverride}
              url={modelUrl}
            />
          ) : (
            <Float speed={1.2} rotationIntensity={0.18} floatIntensity={0.35}>
              <PlaceholderCat avatarState={visualState} />
            </Float>
          )}

          {/* Ground shadow */}
          <ContactShadows
            position={[0, -1.8, 0]}
            opacity={0.55}
            scale={5}
            blur={2}
            far={3}
            color="#f97316"
          />

          {/* Camera controls */}
          <OrbitControls
            enableZoom={false}
            enablePan={false}
            maxPolarAngle={Math.PI / 1.8}
            minPolarAngle={Math.PI / 3}
            autoRotate={visualState === "idle"}
            autoRotateSpeed={0.4}
          />
        </Suspense>
      </Canvas>

      {/* State indicator badge */}
      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-10 flex flex-col items-center gap-2">
        <span className="text-[10px] px-2 py-0.5 rounded-full border border-border bg-bg-card/70 text-text-muted uppercase tracking-wider">
          {hasModel ? "GLTF Model" : "Placeholder"}
        </span>
        <StateBadge state={visualState} />
      </div>
    </div>
  );
}

function StateBadge({ state }: { state: AvatarState }) {
  const cfg: Record<AvatarState, { label: string; color: string }> = {
    idle:      { label: "Idle", color: "text-text-muted border-border bg-bg-card/80" },
    listening: { label: "Listening…", color: "text-accent-green border-accent-green/40 bg-accent-green/10" },
    thinking:  { label: "Thinking…", color: "text-nova-amber border-nova-amber/40 bg-nova-amber/10" },
    speaking:  { label: "Speaking", color: "text-nova-orange border-nova-orange/40 bg-nova-orange/10" },
    sleeping:  { label: "Sleeping", color: "text-accent-purple border-accent-purple/40 bg-accent-purple/10" },
    focused:   { label: "Focused", color: "text-accent-blue border-accent-blue/40 bg-accent-blue/10" },
    relaxed:   { label: "Relaxed", color: "text-accent-green border-accent-green/40 bg-accent-green/10" },
    proud:     { label: "Proud", color: "text-nova-amber border-nova-amber/40 bg-nova-amber/10" },
    shy:       { label: "Shy", color: "text-accent-purple border-accent-purple/40 bg-accent-purple/10" },
    happy:     { label: "Happy 😺", color: "text-nova-amber border-nova-amber/40 bg-nova-amber/10" },
    curious:   { label: "Curious", color: "text-accent-blue border-accent-blue/40 bg-accent-blue/10" },
    concerned: { label: "Concerned", color: "text-accent-red border-accent-red/40 bg-accent-red/10" },
    excited:   { label: "Excited!", color: "text-nova-orange border-nova-orange/40 bg-nova-orange/10" },
  };
  const { label, color } = cfg[state] ?? cfg.idle;

  return (
    <AnimatePresence mode="wait">
      <motion.span
        key={state}
        initial={{ opacity: 0, y: 4, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: -4, scale: 0.98 }}
        transition={{ duration: 0.16, ease: "easeOut" }}
        className={`text-[11px] font-bold uppercase tracking-widest px-3 py-1 rounded-full border backdrop-blur-sm ${color}`}
      >
        {label}
      </motion.span>
    </AnimatePresence>
  );
}
