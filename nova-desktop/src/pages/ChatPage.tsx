import { MessageSquare } from "lucide-react";
import { ChatPanel } from "@/components/Chat/ChatPanel";

export function ChatPage() {
  return (
    <div className="flex flex-col h-full">
      <div className="px-5 sm:px-8 py-6 border-b border-border flex-shrink-0">
        <div className="flex items-center gap-2">
          <MessageSquare size={18} className="text-nova-orange" />
          <div>
            <p className="nova-panel-heading mb-1">Your workspace</p>
            <h2 className="font-display font-medium text-2xl text-text-primary">
              Conversation
            </h2>
          </div>
        </div>
      </div>
      <div className="flex-1 min-h-0 overflow-hidden w-full max-w-5xl mx-auto">
        <ChatPanel />
      </div>
    </div>
  );
}
