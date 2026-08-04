import { Eye } from "lucide-react";

export function VisionPage() {
  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-5 border-b border-border flex-shrink-0">
        <div className="flex items-center gap-2">
          <Eye size={18} className="text-nova-orange" />
          <div>
            <h2 className="font-display font-bold text-xl text-text-primary">Vision</h2>
            <p className="text-text-muted text-sm">Camera, face recognition, activity detection.</p>
          </div>
        </div>
      </div>
      <div className="flex-1 flex items-center justify-center p-6">
        <div className="text-center max-w-md">
          <div className="text-5xl mb-5">👁️</div>
          <h3 className="font-display font-bold text-lg text-text-primary mb-2">
            Vision coming in Sprint 5
          </h3>
          <p className="text-text-muted text-sm leading-relaxed">
            Camera input → MediaPipe → YOLO → Qwen2.5 VL → Brain.
            Face recognition, activity detection (coding, reading, meeting), and scene understanding.
          </p>
          <div className="mt-6 grid grid-cols-2 gap-3 text-left">
            {["Face Recognition", "Activity Detection", "Scene Understanding", "Computer Awareness"].map((f) => (
              <div key={f} className="bg-bg-card border border-border rounded-xl p-3 text-[13px] text-text-muted">
                🔜 {f}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
