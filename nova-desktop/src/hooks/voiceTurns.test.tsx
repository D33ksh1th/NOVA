import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { useVoiceWakeListener } from "./useVoiceWakeListener";
import { useNovaChat } from "./useNovaChat";
import { useSettingsStore } from "@/stores/useSettingsStore";
import { useAppStore } from "@/stores/useAppStore";
import { useChatStore } from "@/stores/useChatStore";
import { useAvatarStore } from "@/stores/useAvatarStore";
import { apiChat, apiVoiceSpeak, apiVoiceStop, apiVoiceText } from "@/services/api";

vi.mock("@/services/api", () => ({
  apiChat: vi.fn(), apiVoiceText: vi.fn(), apiVoiceSpeak: vi.fn(), apiVoiceStop: vi.fn(),
  apiVoiceEnrollmentAnswer: vi.fn(), apiVoiceEnrollmentStart: vi.fn(),
}));
vi.mock("@/utils/karaoke", () => ({ startKaraoke: vi.fn(() => vi.fn()) }));

function deferred<Value>() {
  let resolve!: (value: Value) => void;
  const promise = new Promise<Value>(complete => { resolve = complete; });
  return { promise, resolve };
}

class Socket {
  static OPEN = 1;
  static CONNECTING = 0;
  static latest: Socket;
  readyState = Socket.OPEN;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  send = vi.fn();
  close = vi.fn();
  constructor() { Socket.latest = this; }
  emit(data: object) { this.onmessage?.({ data: JSON.stringify(data) }); }
}

const source = { connect: vi.fn(), disconnect: vi.fn() };
const processor = { connect: vi.fn(), disconnect: vi.fn(), onaudioprocess: null as null | ((event: { inputBuffer: { getChannelData: () => Float32Array } }) => void) };
const stopTrack = vi.fn();
class AudioContextMock {
  sampleRate = 16000;
  destination = {};
  createMediaStreamSource = () => source;
  createScriptProcessor = () => processor;
  close = vi.fn(async () => {});
}

function Listener() { useVoiceWakeListener(); return null; }
let chat: ReturnType<typeof useNovaChat>;
function Chat() { chat = useNovaChat(); return null; }

describe("voice turn ownership", () => {
  let root: Root;
  let container: HTMLDivElement;
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
    vi.stubGlobal("WebSocket", Socket);
    vi.stubGlobal("AudioContext", AudioContextMock);
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: vi.fn(async () => ({ getTracks: () => [{ stop: stopTrack }], getAudioTracks: () => [{}] })) } });
    vi.spyOn(useSettingsStore.persist, "hasHydrated").mockReturnValue(true);
    useSettingsStore.setState({ voice: { ...useSettingsStore.getState().voice, enabled: true, handsFreeWake: true, speakBack: true } });
    useAppStore.setState({ voiceListenSignal: 0, status: { ...useAppStore.getState().status, musicPlaying: false } });
    useAvatarStore.setState({ state: "idle", speechText: null });
    vi.mocked(apiVoiceStop).mockResolvedValue({ ok: true });
    vi.mocked(apiVoiceSpeak).mockResolvedValue();
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
  });
  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  async function mountListener() {
    await act(async () => root.render(<Listener />));
    await act(async () => Socket.latest.onopen?.());
    await act(async () => Socket.latest.emit({ type: "wake_detected" }));
  }

  it("accepts a fresh wake command while music is playing", async () => {
    useAppStore.getState().setStatus({ musicPlaying: true });
    vi.mocked(apiVoiceText).mockResolvedValueOnce({ response: "", action: "music_playback", success: true, playback_state: "paused" });
    await mountListener();
    await act(async () => Socket.latest.emit({ type: "transcript", text: "Pause music" }));
    expect(apiVoiceText).toHaveBeenCalledWith(expect.objectContaining({ text: "Pause music" }));
    expect(useAppStore.getState().status.musicPlaying).toBe(false);
    expect(Socket.latest.close).not.toHaveBeenCalled();
  });

  it("retains report navigation metadata for a spoken research request", async () => {
    vi.mocked(apiVoiceText).mockResolvedValueOnce({ response: "On it.", action: "agent_research_started", data: { report_id: "voice-report-test" } });
    await mountListener();
    await act(async () => Socket.latest.emit({ type: "transcript", text: "Search up local speech models" }));
    expect(useChatStore.getState().messages.at(-1)?.details?.report_id).toBe("voice-report-test");
  });

  it("keeps the conversation open for a music choice after no match", async () => {
    vi.mocked(apiVoiceText).mockResolvedValueOnce({ response: "Which artist?", action: "music_playback", success: false, playback_state: "paused" });
    await mountListener();
    await act(async () => Socket.latest.emit({ type: "transcript", text: "Play something" }));
    expect(Socket.latest.send).not.toHaveBeenCalledWith(JSON.stringify({ type: "exit" }));
  });

  it.each([
    { success: true, playback_state: "playing", expected: true },
    { success: false, playback_state: "playing", expected: false },
    { success: false, playback_state: "unknown", expected: false },
    { success: true, playback_state: "unknown", expected: false },
    { success: null, playback_state: null, expected: false },
  ])("only confirms voice music playback for $success / $playback_state", async ({ expected, ...outcome }) => {
    vi.mocked(apiVoiceText).mockResolvedValueOnce({ response: "", action: "music_playback", ...outcome });
    await mountListener();
    await act(async () => Socket.latest.emit({ type: "transcript", text: "Play music" }));
    expect(useAppStore.getState().status.musicPlaying).toBe(expected);
  });

  it.each([
    { initial: false, success: true, playback_state: "playing", expected: true },
    { initial: false, success: true, playback_state: "unknown", expected: false },
    { initial: true, success: false, playback_state: "paused", expected: true },
    { initial: true, success: true, playback_state: "paused", expected: false },
  ])("preserves confirmed chat music state for $success / $playback_state", async ({ initial, expected, ...outcome }) => {
    useAppStore.getState().setStatus({ musicPlaying: initial });
    vi.mocked(apiChat).mockResolvedValueOnce({ response: "", action: "music_playback", ...outcome });
    await act(async () => root.render(<Chat />));
    await act(async () => chat.sendMessage("Change music playback"));
    expect(useAppStore.getState().status.musicPlaying).toBe(expected);
  });

  it("queues a follow-up while thinking and does not speak the obsolete answer", async () => {
    const first = deferred<Awaited<ReturnType<typeof apiVoiceText>>>();
    const second = deferred<Awaited<ReturnType<typeof apiVoiceText>>>();
    vi.mocked(apiVoiceText).mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    await mountListener();
    await act(async () => Socket.latest.emit({ type: "transcript", text: "Check tomorrow" }));
    await act(async () => Socket.latest.emit({ type: "transcript", text: "Include Friday too" }));
    expect(apiVoiceText).toHaveBeenCalledTimes(1);
    await act(async () => first.resolve({ response: "First answer" }));
    expect(apiVoiceText).toHaveBeenCalledTimes(2);
    expect(apiVoiceText).toHaveBeenLastCalledWith(expect.objectContaining({ text: "Include Friday too" }));
    expect(apiVoiceSpeak).not.toHaveBeenCalled();
    await act(async () => second.resolve({ response: "Updated answer" }));
    expect(apiVoiceSpeak).toHaveBeenCalledWith("Updated answer", expect.anything());
  });

  it("streams during playback and ignores the interrupted speech completion", async () => {
    const speech = deferred<void>();
    const followUp = deferred<Awaited<ReturnType<typeof apiVoiceText>>>();
    vi.mocked(apiVoiceText).mockResolvedValueOnce({ response: "Original answer" }).mockReturnValueOnce(followUp.promise);
    vi.mocked(apiVoiceSpeak).mockReturnValueOnce(speech.promise);
    await mountListener();
    await act(async () => Socket.latest.emit({ type: "transcript", text: "First question" }));
    expect(useAvatarStore.getState().state).toBe("speaking");
    processor.onaudioprocess?.({ inputBuffer: { getChannelData: () => new Float32Array(100) } });
    expect(Socket.latest.send).toHaveBeenCalledWith(expect.any(ArrayBuffer));
    expect(source.disconnect).not.toHaveBeenCalled();
    await act(async () => {
      Socket.latest.emit({ type: "barge_in" });
      Socket.latest.emit({ type: "transcript", text: "Actually compare both" });
    });
    await act(async () => speech.resolve());
    expect(useAvatarStore.getState().state).toBe("thinking");
    await act(async () => followUp.resolve({ response: "Comparison" }));
    expect(apiVoiceSpeak).toHaveBeenLastCalledWith("Comparison", expect.anything());
  });

  it("awaits stop before forwarding a transcript captured during external playback", async () => {
    const stopped = deferred<Awaited<ReturnType<typeof apiVoiceStop>>>();
    vi.mocked(apiVoiceStop).mockReturnValueOnce(stopped.promise);
    vi.mocked(apiVoiceText).mockResolvedValue({ response: "Follow-up" });
    await mountListener();
    await act(async () => window.dispatchEvent(new CustomEvent("nova-playback", { detail: { active: true, text: "External reply" } })));
    await act(async () => Socket.latest.emit({ type: "transcript", text: "Wait, include Friday" }));
    expect(apiVoiceStop).toHaveBeenCalledTimes(1);
    expect(apiVoiceText).not.toHaveBeenCalled();
    await act(async () => stopped.resolve({ ok: true }));
    expect(apiVoiceText).toHaveBeenCalledTimes(1);
  });

  it("opens a follow-up window for chat speech without another wake word", async () => {
    await act(async () => root.render(<Listener />));
    await act(async () => Socket.latest.onopen?.());
    await act(async () => window.dispatchEvent(new CustomEvent("nova-playback", { detail: { active: true, text: "Chat reply" } })));
    const controls = Socket.latest.send.mock.calls.map(([value]) => JSON.parse(value as string));
    expect(controls).toContainEqual({ type: "start_conversation" });
    expect(controls).toContainEqual({ type: "playback_started", text: "Chat reply" });
  });

  it("does not speak a late answer after the microphone is disabled", async () => {
    const answer = deferred<Awaited<ReturnType<typeof apiVoiceText>>>();
    vi.mocked(apiVoiceText).mockReturnValueOnce(answer.promise);
    await mountListener();
    await act(async () => Socket.latest.emit({ type: "transcript", text: "Check tomorrow" }));
    await act(async () => useSettingsStore.setState({ voice: { ...useSettingsStore.getState().voice, enabled: false } }));
    await act(async () => answer.resolve({ response: "Late answer" }));
    expect(apiVoiceSpeak).not.toHaveBeenCalled();
    expect(stopTrack).toHaveBeenCalled();
  });

  it("does not let chat playback completion overwrite a listening follow-up", async () => {
    const speech = deferred<void>();
    vi.mocked(apiChat).mockResolvedValue({ response: "Chat answer" });
    vi.mocked(apiVoiceSpeak).mockReturnValueOnce(speech.promise);
    await act(async () => root.render(<Chat />));
    let sending!: Promise<void>;
    await act(async () => { sending = chat.sendMessage("Explain the plan"); });
    expect(useAvatarStore.getState().state).toBe("speaking");
    await act(async () => {
      window.dispatchEvent(new Event("nova-speech-interrupted"));
      useAvatarStore.getState().setState("listening");
      speech.resolve();
      await sending;
    });
    expect(useAvatarStore.getState().state).toBe("listening");
  });
});