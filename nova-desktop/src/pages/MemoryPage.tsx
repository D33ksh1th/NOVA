import { Brain, Plus } from "lucide-react";

const MOCK_ENTRIES = [
  { id: "1", category: "Preferences", content: "You prefer working late at night 🌙", tags: ["habit", "schedule"] },
  { id: "2", category: "Projects", content: "Building NOVA desktop companion with Tauri + React Three Fiber", tags: ["project", "code"] },
  { id: "3", category: "Preferences", content: "Loves cats, especially Persian breed 🐱", tags: ["personal"] },
  { id: "4", category: "Work Style", content: "Uses VS Code and terminal primarily. Prefers dark theme.", tags: ["dev"] },
  { id: "5", category: "Goals", content: "Wants NOVA to eventually run on a physical robot 🤖", tags: ["vision", "robot"] },
];

export function MemoryPage() {
  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-5 border-b border-border flex-shrink-0 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Brain size={18} className="text-nova-orange" />
          <div>
            <h2 className="font-display font-bold text-xl text-text-primary">Memory</h2>
            <p className="text-text-muted text-sm">What NOVA knows about you.</p>
          </div>
        </div>
        <button className="flex items-center gap-1.5 px-3 py-1.5 bg-nova-orange/15 border border-nova-orange/25 text-nova-orange rounded-xl text-[13px] font-semibold hover:bg-nova-orange/25 transition-all">
          <Plus size={14} /> Add Memory
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="grid gap-3">
          {MOCK_ENTRIES.map((entry) => (
            <div
              key={entry.id}
              className="bg-bg-card border border-border rounded-xl p-4 hover:border-nova-orange/20 transition-colors"
            >
              <div className="flex items-start justify-between gap-3">
                <p className="text-[14px] text-text-primary leading-relaxed flex-1">
                  {entry.content}
                </p>
                <span className="text-[10px] font-bold uppercase tracking-wider text-nova-orange bg-nova-orange/10 border border-nova-orange/20 rounded-lg px-2 py-1 flex-shrink-0">
                  {entry.category}
                </span>
              </div>
              {entry.tags.length > 0 && (
                <div className="flex gap-1.5 mt-2.5">
                  {entry.tags.map((tag) => (
                    <span
                      key={tag}
                      className="text-[10px] text-text-muted bg-bg-elevated border border-border rounded-md px-1.5 py-0.5"
                    >
                      #{tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>

        <div className="mt-6 rounded-xl border border-border bg-bg-card p-4 text-[13px] text-text-muted">
          <p className="font-medium text-nova-amber mb-1">🚧 Sprint 6 Feature</p>
          <p>
            Full relationship engine, daily journal, pattern learning, and long-term memory via Qdrant
            vector store will be implemented in Sprint 6.
          </p>
        </div>
      </div>
    </div>
  );
}
