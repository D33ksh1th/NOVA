import { MessageSquare } from "lucide-react";
import { ChatPanel } from "@/components/Chat/ChatPanel";

export function ChatPage() {
  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-5 border-b border-border flex-shrink-0">
        <div className="flex items-center gap-2">
          <MessageSquare size={18} className="text-nova-orange" />
          <div>
            <h2 className="font-display font-bold text-xl text-text-primary">
              Chat
            </h2>
            <p className="text-text-muted text-sm">
              Full conversation history with NOVA.
            </p>
          </div>
        </div>
      </div>
      <div className="flex-1 overflow-hidden">
        <ChatPanel />
      </div>
    </div>
  );
}
