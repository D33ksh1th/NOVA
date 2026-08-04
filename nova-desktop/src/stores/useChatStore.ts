import { create } from "zustand";
import type { ChatMessage } from "@/types";

interface ChatStore {
  messages: ChatMessage[];
  isStreaming: boolean;
  inputValue: string;

  addMessage: (msg: Omit<ChatMessage, "id" | "timestamp">) => ChatMessage;
  updateMessage: (id: string, partial: Partial<ChatMessage>) => void;
  removeMessage: (id: string) => void;
  clearMessages: () => void;
  setStreaming: (val: boolean) => void;
  setInputValue: (val: string) => void;
}

function randomId() {
  return Math.random().toString(36).slice(2, 9);
}

export const useChatStore = create<ChatStore>()((set, get) => ({
  messages: [],
  isStreaming: false,
  inputValue: "",

  addMessage: (msg) => {
    const full: ChatMessage = {
      id: randomId(),
      timestamp: new Date(),
      ...msg,
    };
    set((s) => ({ messages: [...s.messages, full] }));
    return full;
  },

  updateMessage: (id, partial) =>
    set((s) => ({
      messages: s.messages.map((m) => (m.id === id ? { ...m, ...partial } : m)),
    })),

  removeMessage: (id) =>
    set((s) => ({ messages: s.messages.filter((m) => m.id !== id) })),

  clearMessages: () => set({ messages: [] }),
  setStreaming: (val) => set({ isStreaming: val }),
  setInputValue: (val) => set({ inputValue: val }),
}));
