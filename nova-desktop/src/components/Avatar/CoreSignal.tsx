import { useEffect, useRef } from "react";
import { useAvatarStore } from "@/stores/useAvatarStore";

export function CoreSignal() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const state = useAvatarStore((store) => store.state);
  const connected = useAvatarStore((store) => store.streamConnected);
  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;
    const motion = matchMedia("(prefers-reduced-motion: reduce)");
    let frame = 0;
    let lastFrame = 0;
    let width = 0;
    let height = 0;
    const draw = (time: number) => {
      if (lastFrame === -Infinity || (!document.hidden && time - lastFrame >= 30)) {
        lastFrame = time;
        context.clearRect(0, 0, width, height);
        const phase = motion.matches ? 0 : time * (state === "thinking" ? 0.0008 : 0.00035);
        const intensity = !connected ? 0.2 : state === "speaking" ? 1 : state === "listening" ? 0.8 : 0.45;
        const spectrum = context.createLinearGradient(width * 0.08, 0, width * 0.92, height);
        spectrum.addColorStop(0, "#83b4e8");
        spectrum.addColorStop(state === "speaking" ? 0.7 : 0.42, state === "speaking" ? "#b5d3f3" : "#d8b142");
        spectrum.addColorStop(1, "#e89582");
        for (let strand = 0; strand < 42; strand++) {
          const spread = (strand - 20.5) / 21;
          context.beginPath();
          for (let step = 0; step <= 150; step++) {
            const progress = step / 150;
            const envelope = Math.sin(progress * Math.PI) ** 1.6;
            const wave = Math.sin(progress * Math.PI * 3 + phase + spread * 1.9);
            const detail = Math.sin(progress * Math.PI * 7 - phase * 1.4 + spread) * intensity * 0.17;
            const vertical = height / 2 + envelope * height * (spread * 0.25 + (wave + detail) * intensity * 0.24);
            const horizontal = width * (0.06 + progress * 0.88);
            if (step === 0) context.moveTo(horizontal, vertical);
            else context.lineTo(horizontal, vertical);
          }
          context.globalAlpha = 0.28 + (1 - Math.abs(spread)) * 0.5;
          context.strokeStyle = strand % 7 === 0 ? "#f1f0ec" : spectrum;
          context.lineWidth = strand % 7 === 0 ? 1.1 : 0.8;
          context.stroke();
        }
      }
      if (!motion.matches) frame = requestAnimationFrame(draw);
    };
    const resize = () => {
      const bounds = canvas.getBoundingClientRect();
      width = bounds.width; height = bounds.height;
      const ratio = Math.min(devicePixelRatio || 1, 2);
      canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      cancelAnimationFrame(frame); lastFrame = -Infinity; draw(performance.now());
    };
    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    motion.addEventListener("change", resize);
    document.addEventListener("visibilitychange", resize);
    return () => { observer.disconnect(); motion.removeEventListener("change", resize); document.removeEventListener("visibilitychange", resize); cancelAnimationFrame(frame); };
  }, [state, connected]);
  return <canvas ref={canvasRef} role="img" aria-label={`NOVA signal: ${connected ? state : "disconnected"}`} className="w-full h-full block" />;
}