import { AnimatePresence, motion } from "framer-motion";
import { useAvatarStore } from "@/stores/useAvatarStore";
import { clsx } from "clsx";

export function SpeechBubble() {
  const speechText = useAvatarStore((s) => s.speechText);
  const avatarState = useAvatarStore((s) => s.state);

  const visible = Boolean(speechText);

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, y: 12, scale: 0.92 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 8, scale: 0.96 }}
          transition={{ type: "spring", stiffness: 400, damping: 30 }}
          className={clsx(
            "fixed top-16 left-1/2 -translate-x-1/2 z-40",
            "w-[min(720px,calc(100vw-2rem))] max-w-[78%] min-w-[140px]",
            "bg-bg-elevated/95 backdrop-blur-md border border-border",
            "rounded-2xl px-4 py-3 shadow-panel",
            "text-text-primary text-[13.5px] leading-relaxed text-center"
          )}
        >
          {/* Speaking bar */}
          {avatarState === "speaking" && (
            <div className="flex items-center justify-center gap-0.5 mb-2">
              {Array.from({ length: 8 }).map((_, i) => (
                <motion.div
                  key={i}
                  className="w-0.5 rounded-full bg-nova-orange"
                  animate={{ height: ["4px", `${8 + (i % 4) * 4}px`, "4px"] }}
                  transition={{
                    duration: 0.5 + (i % 3) * 0.15,
                    repeat: Infinity,
                    ease: "easeInOut",
                    delay: i * 0.06,
                  }}
                />
              ))}
            </div>
          )}
          {/* Thinking dots */}
          {avatarState === "thinking" && (
            <div className="flex items-center justify-center gap-1 mb-2">
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="w-1.5 h-1.5 rounded-full bg-nova-amber animate-typing-dot"
                  style={{ animationDelay: `${i * 0.2}s` }}
                />
              ))}
            </div>
          )}

          <p className="line-clamp-5">{speechText}</p>

          {/* Tail */}
          <div className="absolute -bottom-2 left-1/2 -translate-x-1/2 w-4 h-2 overflow-hidden">
            <div className="w-4 h-4 bg-bg-elevated border-r border-b border-border rotate-45 -translate-y-2 mx-auto" />
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
