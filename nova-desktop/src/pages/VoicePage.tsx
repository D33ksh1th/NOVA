import { Mic, MicOff, Volume2, Radio } from "lucide-react";
import { useSettingsStore } from "@/stores/useSettingsStore";
import { useChatStore } from "@/stores/useChatStore";
import { useAvatarStore } from "@/stores/useAvatarStore";
import { motion, AnimatePresence } from "framer-motion";
import { useCallback, useRef, useState } from "react";
import { apiVoiceSpeak, apiVoiceText } from "@/services/api";
import { toSubtitleText } from "@/utils/subtitle";

// Minimal local types for Web Speech API (not present in DOM lib by default)
interface ISpeechRecognition extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onresult: ((e: any) => void) | null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onerror: ((e: any) => void) | null;
  onend: (() => void) | null;
  onspeechend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}
type SpeechRecognitionCtor = new () => ISpeechRecognition;

type AudioCapturePayload = {
  audioBase64?: string;
  audioMimeType?: string;
};

type AudioCaptureSession = {
  stop: () => Promise<AudioCapturePayload>;
};

function floatTo16BitPCM(output: DataView, offset: number, input: Float32Array) {
  for (let i = 0; i < input.length; i += 1, offset += 2) {
    const sample = Math.max(-1, Math.min(1, input[i] ?? 0));
    output.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
  }
}

function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);

  const writeString = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i += 1) {
      view.setUint8(offset + i, value.charCodeAt(i));
    }
  };

  writeString(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(36, "data");
  view.setUint32(40, samples.length * 2, true);
  floatTo16BitPCM(view, 44, samples);

  return new Blob([view], { type: "audio/wav" });
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(typeof reader.result === "string" ? reader.result : "");
    reader.onerror = () => reject(reader.error ?? new Error("Failed to read recorded audio"));
    reader.readAsDataURL(blob);
  });
}

async function startAudioCaptureSession(): Promise<AudioCaptureSession | null> {
  if (typeof window === "undefined" || !navigator.mediaDevices?.getUserMedia) {
    return null;
  }

  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      noiseSuppression: true,
      echoCancellation: true,
      autoGainControl: true,
    },
  });
  const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextCtor) {
    stream.getTracks().forEach((track) => track.stop());
    return null;
  }

  const audioContext = new AudioContextCtor();
  const sampleRate = audioContext.sampleRate;
  const source = audioContext.createMediaStreamSource(stream);
  const processor = audioContext.createScriptProcessor(4096, 1, 1);
  const chunks: Float32Array[] = [];

  processor.onaudioprocess = (event) => {
    chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
  };

  source.connect(processor);
  processor.connect(audioContext.destination);

  return {
    stop: async () => {
      processor.disconnect();
      source.disconnect();
      stream.getTracks().forEach((track) => track.stop());
      await audioContext.close().catch(() => {});

      const totalLength = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
      if (!totalLength) return {};

      const merged = new Float32Array(totalLength);
      let offset = 0;
      for (const chunk of chunks) {
        merged.set(chunk, offset);
        offset += chunk.length;
      }

      const wavBlob = encodeWav(merged, sampleRate);
      return {
        audioBase64: await blobToBase64(wavBlob),
        audioMimeType: "audio/wav",
      };
    },
  };
}

declare global {
  interface Window {
    SpeechRecognition: SpeechRecognitionCtor;
    webkitSpeechRecognition: SpeechRecognitionCtor;
    webkitAudioContext?: typeof AudioContext;
  }
}

export function VoicePage() {
  const voice = useSettingsStore((s) => s.voice);
  const setVoice = useSettingsStore((s) => s.setVoice);
  const addMessage = useChatStore((s) => s.addMessage);
  const updateMessage = useChatStore((s) => s.updateMessage);
  const setAvatarState = useAvatarStore((s) => s.setState);
  const setSpeechText = useAvatarStore((s) => s.setSpeechText);

  const [listening, setListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [status, setStatus] = useState<"idle" | "listening" | "thinking" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const recognitionRef = useRef<ISpeechRecognition | null>(null);
  const audioCaptureRef = useRef<AudioCaptureSession | null>(null);
  const handledWakeSignalRef = useRef(0);
  const settleRef = useRef<number | null>(null);

  const SpeechRecognitionAPI: SpeechRecognitionCtor | undefined =
    typeof window !== "undefined"
      ? (window.SpeechRecognition || window.webkitSpeechRecognition)
      : undefined;

  const supported = !!SpeechRecognitionAPI;

  // ── Process captured speech through NOVA voice pipeline ─────────
  const processUtterance = useCallback(async (text: string, audio?: AudioCapturePayload) => {
    if (!text.trim()) return;
    setTranscript(text);
    setStatus("thinking");
    setAvatarState("thinking");

    const userMsgId = addMessage({ role: "user", content: text, meta: { source: "voice" } });
    const loaderId = addMessage({ role: "nova", content: "", streaming: true });

    try {
      const payload = await apiVoiceText({
        text,
        speak: false,
        audio_base64: audio?.audioBase64,
        audio_mime_type: audio?.audioMimeType,
        voice_mode: voice.mode,
        voice_style: voice.style,
        voice_rate: voice.rate,
        voice_pitch: voice.pitch,
        voice_name: voice.model,
        accent_profile: voice.accent,
      });

      const response = payload.response ?? "";
      updateMessage(loaderId.id, {
        content: response,
        streaming: false,
        meta: { intent: payload.intent, action: payload.action, source: "voice" },
      });
      const subtitle = toSubtitleText(response);
      if (subtitle) {
        setSpeechText(subtitle);
      }
      setAvatarState("speaking");
      if (voice.speakBack && subtitle) {
        apiVoiceSpeak(subtitle, voice).catch(() => {/* non-critical */});
      }
      setStatus("idle");
      setTranscript("");

      if (settleRef.current) window.clearTimeout(settleRef.current);
      const wordCount = subtitle.split(/\s+/).filter(Boolean).length;
      const duration = Math.max(2500, Math.min((wordCount / 2.8) * 1000, 30000));
      settleRef.current = window.setTimeout(() => {
        setAvatarState("idle");
      }, duration);
    } catch (err) {
      updateMessage(loaderId.id, {
        role: "error",
        content: err instanceof Error ? err.message : "Voice request failed",
        streaming: false,
      });
      setAvatarState("idle");
      setStatus("error");
      setErrorMsg("Could not reach NOVA backend.");
    }
  }, [voice, addMessage, updateMessage, setAvatarState, setSpeechText]);

  // ── Single press-to-talk session ────────────────────────────────
  const startListening = useCallback(() => {
    if (!SpeechRecognitionAPI) {
      setErrorMsg("Speech recognition is not supported in this browser.");
      setStatus("error");
      return;
    }

    if (recognitionRef.current) {
      recognitionRef.current.abort();
    }

    const rec = new SpeechRecognitionAPI();
    rec.lang = "en-US";
    rec.interimResults = true;
    rec.maxAlternatives = 1;
    recognitionRef.current = rec;

    setListening(true);
    setStatus("listening");
    setTranscript("");
    setErrorMsg("");
    setAvatarState("listening");
    audioCaptureRef.current = null;
    void startAudioCaptureSession().then((session) => {
      if (recognitionRef.current === rec) {
        audioCaptureRef.current = session;
        return;
      }
      if (session) {
        void session.stop().catch(() => {});
      }
    }).catch(() => {
      audioCaptureRef.current = null;
    });

    // Single local variable tracks the final transcript so onend can use it.
    let lastFinal = "";

    rec.onresult = (e: any) => {
      let final = "";
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) { final += t; lastFinal = final; }
        else interim += t;
      }
      setTranscript(lastFinal || interim);
    };

    rec.onspeechend = () => {
      rec.stop();
    };

    rec.onerror = (e: any) => {
      if (audioCaptureRef.current) {
        void audioCaptureRef.current.stop().catch(() => {});
        audioCaptureRef.current = null;
      }
      setListening(false);
      setAvatarState("idle");
      if (e.error === "not-allowed") {
        setErrorMsg("Microphone permission denied — allow access in browser/OS settings.");
        setStatus("error");
      } else if (e.error === "no-speech") {
        setErrorMsg("No speech detected. Try again.");
        setStatus("idle");
      } else if (e.error === "network") {
        setErrorMsg("Network error — ensure you're on localhost or HTTPS.");
        setStatus("error");
      } else if (e.error === "aborted") {
        setStatus("idle");
      } else {
        setErrorMsg(`Recognition error: ${e.error}`);
        setStatus("error");
      }
    };

    rec.onend = async () => {
      setListening(false);
      const recordedAudio = audioCaptureRef.current
        ? await audioCaptureRef.current.stop().catch(() => ({} as AudioCapturePayload))
        : undefined;
      audioCaptureRef.current = null;
      if (lastFinal.trim()) {
        processUtterance(lastFinal.trim(), recordedAudio);
      } else {
        setAvatarState("idle");
        setStatus("idle");
      }
    };

    rec.start();
  }, [SpeechRecognitionAPI, processUtterance, setAvatarState]);

  const stopListening = useCallback(() => {
    recognitionRef.current?.stop();
    setListening(false);
  }, []);

  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-5 border-b border-border flex-shrink-0">
        <div className="flex items-center gap-2">
          <Mic size={18} className="text-nova-orange" />
          <div>
            <h2 className="font-display font-bold text-xl text-text-primary">Voice</h2>
            <p className="text-text-muted text-sm">Push-to-talk, wake word, and TTS settings.</p>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-5">

        {!supported && (
          <div className="rounded-xl border border-accent-red/30 bg-accent-red/10 px-4 py-3 text-[13px] text-accent-red">
            Speech recognition is not supported in this browser. Use Chrome or Edge for voice input.
          </div>
        )}

        {/* Push-to-talk */}
        <div className="bg-bg-card border border-border rounded-2xl p-5 flex flex-col items-center gap-4">
          <p className="text-[11px] font-mono uppercase tracking-widest text-text-muted">Push to Talk</p>

          <motion.button
            disabled={!supported || status === "thinking"}
            onMouseDown={startListening}
            onMouseUp={stopListening}
            onTouchStart={startListening}
            onTouchEnd={stopListening}
            whileTap={{ scale: 0.93 }}
            animate={
              listening
                ? { boxShadow: ["0 0 0 0 rgba(249,115,22,0.5)", "0 0 0 20px rgba(249,115,22,0)", "0 0 0 0 rgba(249,115,22,0.5)"] }
                : {}
            }
            transition={{ duration: 1, repeat: Infinity }}
            className={`w-24 h-24 rounded-full flex items-center justify-center border-2 transition-all duration-200 select-none ${
              listening
                ? "border-nova-orange bg-nova-orange/25 text-nova-orange"
                : status === "thinking"
                ? "border-[#a78bfa] bg-[#a78bfa]/15 text-[#a78bfa] cursor-wait"
                : "border-border bg-bg-elevated text-text-muted hover:border-nova-orange/40 hover:text-text-primary"
            }`}
          >
            {status === "thinking" ? (
              <motion.div
                className="w-8 h-8 border-2 border-[#a78bfa] border-t-transparent rounded-full"
                animate={{ rotate: 360 }}
                transition={{ duration: 0.8, repeat: Infinity, ease: "linear" }}
              />
            ) : listening ? (
              <MicOff size={34} />
            ) : (
              <Mic size={34} />
            )}
          </motion.button>

          <p className="text-[13px] text-text-muted text-center">
            {status === "thinking"
              ? "NOVA is processing…"
              : listening
              ? "Release to send"
              : "Hold to speak"}
          </p>

          {/* Live transcript */}
          <AnimatePresence>
            {transcript && (
              <motion.div
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="w-full bg-bg-elevated border border-border rounded-xl px-4 py-2.5 text-[13px] text-text-secondary text-center italic"
              >
                "{transcript}"
              </motion.div>
            )}
          </AnimatePresence>

          <AnimatePresence>
            {errorMsg && (
              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="text-[12px] text-accent-red text-center"
              >
                {errorMsg}
              </motion.p>
            )}
          </AnimatePresence>
        </div>

        {/* Speak-back toggle */}
        <div className="bg-bg-card border border-border rounded-2xl px-4 py-3 flex items-center justify-between">
          <div>
            <p className="text-[13px] font-medium text-text-primary">Speak Back</p>
            <p className="text-[11px] text-text-muted">NOVA speaks every response aloud</p>
          </div>
          <button
            onClick={() => setVoice({ speakBack: !voice.speakBack })}
            className={`w-11 h-6 rounded-full transition-colors relative ${voice.speakBack ? "bg-nova-orange" : "bg-bg-elevated border border-border"}`}
          >
            <motion.span
              className="absolute top-0.5 w-5 h-5 rounded-full bg-white shadow-sm"
              animate={{ x: voice.speakBack ? 22 : 2 }}
              transition={{ type: "spring", stiffness: 500, damping: 36 }}
            />
          </button>
        </div>

        {/* Wake word */}
        <div className="bg-bg-card border border-border rounded-2xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-[13px] font-bold text-text-primary">Hands-free Wake Word</h3>
              <p className="text-[11px] text-text-muted mt-0.5">
                Say <span className="text-nova-orange">"hey nova"</span> or{" "}
                <span className="text-nova-orange">"nova"</span> to trigger voice input
              </p>
            </div>
            <button
              onClick={() =>
                setVoice({
                  handsFreeWake: !voice.handsFreeWake,
                  micEnabled: !voice.handsFreeWake ? true : voice.micEnabled,
                })
              }
              className={`w-11 h-6 rounded-full transition-colors relative flex-shrink-0 ${voice.handsFreeWake ? "bg-nova-orange" : "bg-bg-elevated border border-border"}`}
            >
              <motion.span
                className="absolute top-0.5 w-5 h-5 rounded-full bg-white shadow-sm"
                animate={{ x: voice.handsFreeWake ? 22 : 2 }}
                transition={{ type: "spring", stiffness: 500, damping: 36 }}
              />
            </button>
          </div>

          <div className={`flex items-center gap-2 text-[12px] font-mono ${voice.handsFreeWake ? "text-accent-green" : "text-text-muted"}`}>
            <motion.span
              className={`w-2 h-2 rounded-full ${voice.handsFreeWake ? "bg-accent-green" : "bg-text-muted"}`}
              animate={voice.handsFreeWake ? { opacity: [1, 0.3, 1] } : {}}
              transition={{ duration: 1.2, repeat: Infinity }}
            />
            {voice.handsFreeWake ? "Wake listener active — say \"nova\" to activate" : "Wake listener off"}
          </div>
        </div>

        {/* Current voice indicator */}
        <div className="bg-bg-card border border-border rounded-2xl px-4 py-3 flex items-center gap-3">
          <Volume2 size={16} className="text-nova-orange flex-shrink-0" />
          <div className="flex-1">
            <p className="text-[12px] font-medium text-text-primary">Active Voice</p>
            <p className="text-[11px] text-text-muted font-mono capitalize">
              {voice.model || "english_lessac"} · {voice.style} · {voice.rate} WPM
            </p>
          </div>
          <span className="text-[10px] font-mono uppercase tracking-wider text-text-muted bg-bg-elevated border border-border rounded-full px-2 py-0.5">
            Piper TTS
          </span>
        </div>

      </div>
    </div>
  );
}
