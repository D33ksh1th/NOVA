import { useEffect, useRef } from "react";
import { useAppStore } from "@/stores/useAppStore";
import { useChatStore } from "@/stores/useChatStore";
import { useAvatarStore } from "@/stores/useAvatarStore";
import { useSettingsStore } from "@/stores/useSettingsStore";
import { apiVoiceSpeak, apiVoiceStop, apiVoiceText } from "@/services/api";
import { toSubtitleText } from "@/utils/subtitle";
import { startKaraoke } from "@/utils/karaoke";

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
type SpeechRecognitionWindow = Window & {
  SpeechRecognition?: SpeechRecognitionCtor;
  webkitSpeechRecognition?: SpeechRecognitionCtor;
};

type AudioCaptureSession = {
  stop: () => Promise<{ audioBase64?: string; audioMimeType?: string }>;
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
    reader.onloadend = () => {
      const result = typeof reader.result === "string" ? reader.result : "";
      resolve(result);
    };
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

  const AudioContextCtor = window.AudioContext || (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioContextCtor) {
    stream.getTracks().forEach((track) => track.stop());
    return null;
  }

  const audioContext = new AudioContextCtor();
  const source = audioContext.createMediaStreamSource(stream);
  const processor = audioContext.createScriptProcessor(4096, 1, 1);
  const chunks: Float32Array[] = [];

  processor.onaudioprocess = (event) => {
    const channel = event.inputBuffer.getChannelData(0);
    chunks.push(new Float32Array(channel));
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

      const wavBlob = encodeWav(merged, audioContext.sampleRate);
      const audioBase64 = await blobToBase64(wavBlob);
      return {
        audioBase64,
        audioMimeType: "audio/wav",
      };
    },
  };
}

export function useVoiceWakeListener() {
  const voice = useSettingsStore((s) => s.voice);
  const voiceListenSignal = useAppStore((s) => s.voiceListenSignal);
  const setVoiceWakeActive = useAppStore((s) => s.setVoiceWakeActive);
  const addMessage = useChatStore((s) => s.addMessage);
  const updateMessage = useChatStore((s) => s.updateMessage);
  const setAvatarState = useAvatarStore((s) => s.setState);
  const setSpeechText = useAvatarStore((s) => s.setSpeechText);

  // voiceRef holds the latest voice settings without re-running the main effect.
  const voiceRef = useRef(voice);
  voiceRef.current = voice;

  const recognitionRef = useRef<ISpeechRecognition | null>(null);
  const captureRef = useRef<ISpeechRecognition | null>(null);
  const timeoutRef = useRef<number | null>(null);
  const settleTimerRef = useRef<number | null>(null);
  const wakeWatchdogRef = useRef<number | null>(null);
  const handledListenSignalRef = useRef(0);
  const karaokeRef = useRef<(() => void) | null>(null);
  const interruptRef = useRef<ISpeechRecognition | null>(null);
  // Prevents wake.onend from restarting while a capture session is in progress.
  const captureActiveRef = useRef(false);
  // Guards wake/capture handoff to avoid duplicate transitions.
  const transitioningToCaptureRef = useRef(false);
  // Keeps an active conversational session after wake word until explicit exit.
  const conversationActiveRef = useRef(false);
  const speakingTextRef = useRef("");
  // Tracks how many times in a row we got empty capture to trigger a re-prompt.
  const emptyCaptureSinceLastResponseRef = useRef(0);
  // Latest enrollment prompt text so we can replay it if speech not caught.
  const lastEnrollmentPromptRef = useRef("");
  // Monotonic turn id to ignore stale timers from older responses.
  const responseTurnRef = useRef(0);
  // Monotonic speech session id to ignore stale TTS completion callbacks.
  const speechSessionRef = useRef(0);
  // If true, wake/capture loops remain paused until user manually starts listening again.
  const listeningPausedRef = useRef(false);
  // Earliest time we will accept an onend with empty text (minimum listen window).
  const captureStartedAtRef = useRef(0);
  const audioCaptureRef = useRef<AudioCaptureSession | null>(null);

  const normalizeText = (v: string) =>
    String(v || "")
      .toLowerCase()
      .replace(/[^a-z\s]/g, " ")
      .replace(/\bknow\s+va\b/g, "nova")
      .replace(/\s+/g, " ")
      .trim();

  const isExitCommand = (v: string) => {
    const n = normalizeText(v);
    return (
      n === "exit" ||
      n === "quit" ||
      n.includes("exit listening") ||
      n.includes("stop listening") ||
      n.includes("stop nova") ||
      n.includes("exit nova") ||
      n.includes("quit nova") ||
      n.includes("goodbye nova") ||
      n.includes("bye nova")
    );
  };

  const cancelKaraoke = () => {
    if (karaokeRef.current !== null) {
      karaokeRef.current();
      karaokeRef.current = null;
    }
  };

  const SpeechRecognitionAPI: SpeechRecognitionCtor | undefined =
    typeof window !== "undefined"
      ? ((window as SpeechRecognitionWindow).SpeechRecognition || (window as SpeechRecognitionWindow).webkitSpeechRecognition)
      : undefined;

  // ─── Main listener effect ─────────────────────────────────────────
  // Only re-runs when the things that control whether we should be listening
  // change. Voice rate/style/model etc. are read via voiceRef.current to
  // avoid tearing down the recognition chain on every settings auto-sync.
  useEffect(() => {
    if (timeoutRef.current !== null) {
      window.clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    if (settleTimerRef.current !== null) {
      window.clearTimeout(settleTimerRef.current);
      settleTimerRef.current = null;
    }
    if (wakeWatchdogRef.current !== null) {
      window.clearInterval(wakeWatchdogRef.current);
      wakeWatchdogRef.current = null;
    }

    const manualListenRequested = voiceListenSignal !== handledListenSignalRef.current;
    const v = voiceRef.current;

    if (!v.enabled || !SpeechRecognitionAPI) {
      recognitionRef.current?.abort();
      captureRef.current?.abort();
      recognitionRef.current = null;
      captureRef.current = null;
      captureActiveRef.current = false;
      setVoiceWakeActive(false);
      return;
    }

    if (!manualListenRequested && !v.handsFreeWake) {
      recognitionRef.current?.abort();
      captureRef.current?.abort();
      recognitionRef.current = null;
      captureRef.current = null;
      captureActiveRef.current = false;
      setVoiceWakeActive(false);
      return;
    }

    let disposed = false;

    const scheduleTimeout = (fn: () => void, ms: number) => {
      if (timeoutRef.current !== null) window.clearTimeout(timeoutRef.current);
      timeoutRef.current = window.setTimeout(fn, ms);
    };

    const clearScheduledTimeout = () => {
      if (timeoutRef.current !== null) {
        window.clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
    };

    const clearSettleTimer = () => {
      if (settleTimerRef.current !== null) {
        window.clearTimeout(settleTimerRef.current);
        settleTimerRef.current = null;
      }
    };

    const clearWakeWatchdog = () => {
      if (wakeWatchdogRef.current !== null) {
        window.clearInterval(wakeWatchdogRef.current);
        wakeWatchdogRef.current = null;
      }
    };

    const stopInterruptListener = () => {
      if (interruptRef.current) {
        interruptRef.current.onend = null;
        interruptRef.current.abort();
        interruptRef.current = null;
      }
    };

    const hardStopAllRecognition = () => {
      clearScheduledTimeout();
      clearSettleTimer();
      clearWakeWatchdog();
      responseTurnRef.current += 1;

      if (recognitionRef.current) {
        recognitionRef.current.onend = null;
        recognitionRef.current.abort();
        recognitionRef.current = null;
      }
      if (captureRef.current) {
        captureRef.current.onend = null;
        captureRef.current.abort();
        captureRef.current = null;
      }
      stopInterruptListener();
      if (audioCaptureRef.current) {
        void audioCaptureRef.current.stop().catch(() => {});
        audioCaptureRef.current = null;
      }
      captureActiveRef.current = false;
      transitioningToCaptureRef.current = false;
      setVoiceWakeActive(false);
    };

    const exitListeningSession = () => {
      listeningPausedRef.current = true;
      conversationActiveRef.current = false;
      speechSessionRef.current += 1;
      cancelKaraoke();
      setSpeechText(null);
      window.speechSynthesis?.cancel();
      apiVoiceStop().catch(() => {/* non-critical */});
      hardStopAllRecognition();
      setAvatarState("idle");
    };

    const startInterruptListener = () => {
      // Never run the interrupt listener while enrollment is active — enrollment
      // sample phrases often contain "nova" and would falsely fire the interrupt.
      if (disposed || !conversationActiveRef.current || captureActiveRef.current) return;
      if (lastEnrollmentPromptRef.current) return;
      stopInterruptListener();

      const interrupt = new SpeechRecognitionAPI();
      interrupt.lang = "en-US";
      interrupt.continuous = true;
      interrupt.interimResults = true;
      interrupt.maxAlternatives = 1;
      interruptRef.current = interrupt;

      const handleInterruptText = (raw: string) => {
        const heard = normalizeText(raw);
        if (!heard) return;

        if (isExitCommand(heard)) {
          exitListeningSession();
          addMessage({ role: "user", content: heard, meta: { source: "voice" } });
          addMessage({
            role: "nova",
            content: "Okay, exiting voice session. Tap mic or toggle Hands-Free Wake to start again.",
            meta: { source: "voice" },
          });
          return;
        }

        // Ignore short echo fragments from NOVA's own TTS output.
        const words = heard.split(" ").filter(Boolean);
        if (words.length <= 2 && speakingTextRef.current.includes(heard)) return;

        const explicitInterrupt =
          heard.includes("nova") ||
          heard.includes("stop") ||
          heard.includes("wait") ||
          heard.includes("listen");
        const naturalInterrupt = words.length >= 4 && !speakingTextRef.current.includes(heard);

        if (!explicitInterrupt && !naturalInterrupt) return;

        responseTurnRef.current += 1;
        speechSessionRef.current += 1;
        clearScheduledTimeout();
        clearSettleTimer();
        stopInterruptListener();
        cancelKaraoke();
        window.speechSynthesis?.cancel();
        apiVoiceStop().catch(() => {/* non-critical */});
        setSpeechText(null);
        setAvatarState("listening");
        window.setTimeout(() => {
          if (!disposed && conversationActiveRef.current) {
            startCapture(0);
          }
        }, 120);
      };

      interrupt.onresult = (e: any) => {
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const t = String(e.results[i][0].transcript || "");
          handleInterruptText(t);
        }
      };

      interrupt.onend = () => {
        interruptRef.current = null;
        if (!disposed && conversationActiveRef.current && !captureActiveRef.current) {
          scheduleTimeout(startInterruptListener, 500);
        }
      };

      interrupt.onerror = () => {
        interruptRef.current = null;
        if (!disposed && conversationActiveRef.current && !captureActiveRef.current) {
          scheduleTimeout(startInterruptListener, 900);
        }
      };

      try {
        interrupt.start();
      } catch {
        interruptRef.current = null;
      }
    };

    const captureAndRespond = async (text: string) => {
      captureActiveRef.current = false;
      const recordedAudio: { audioBase64?: string; audioMimeType?: string } = audioCaptureRef.current
        ? await audioCaptureRef.current.stop().catch(() => ({}))
        : {};
      audioCaptureRef.current = null;
      const utterance = text.trim();
      if (!utterance) {
        // Nothing heard — keep session alive if in active conversation.
        if (!disposed && conversationActiveRef.current) {
          emptyCaptureSinceLastResponseRef.current += 1;
          // After 2 silent attempts during enrollment, replay the last prompt aloud.
          if (emptyCaptureSinceLastResponseRef.current >= 2 && lastEnrollmentPromptRef.current) {
            const reminder = lastEnrollmentPromptRef.current;
            setSpeechText(reminder);
            const cv = voiceRef.current;
            apiVoiceSpeak(reminder, cv).catch(() => {}).finally(() => {
              if (!disposed && conversationActiveRef.current) scheduleTimeout(() => startCapture(0), 300);
            });
            emptyCaptureSinceLastResponseRef.current = 0;
            return;
          }
          scheduleTimeout(() => startCapture(0), 300);
          return;
        }
        if (!disposed && voiceRef.current.handsFreeWake) {
          scheduleTimeout(startWake, 350);
        }
        return;
      }

      if (isExitCommand(utterance)) {
        exitListeningSession();
        addMessage({ role: "user", content: utterance, meta: { source: "voice" } });
        addMessage({ role: "nova", content: "Okay, exiting voice session. Tap mic or toggle Hands-Free Wake to start again.", meta: { source: "voice" } });
        return;
      }

      setAvatarState("thinking");
      addMessage({ role: "user", content: utterance, meta: { source: "voice" } });
      const loaderId = addMessage({ role: "nova", content: "", streaming: true });
      const turnId = responseTurnRef.current + 1;
      responseTurnRef.current = turnId;

      const cv = voiceRef.current;
      try {
        emptyCaptureSinceLastResponseRef.current = 0;
        const payload = await apiVoiceText({
          text: utterance,
          speak: false,
          audio_base64: recordedAudio.audioBase64,
          audio_mime_type: recordedAudio.audioMimeType,
          voice_mode: cv.mode,
          voice_style: cv.style,
          voice_rate: cv.rate,
          voice_pitch: cv.pitch,
          voice_name: cv.model,
          accent_profile: cv.accent,
        });
        // Keep enrollment prompt so we can replay it if next capture is empty.
        if ((payload.action ?? "") === "voice_enrollment" && payload.response) {
          lastEnrollmentPromptRef.current = payload.response;
        } else if ((payload.action ?? "") !== "voice_enrollment") {
          lastEnrollmentPromptRef.current = "";
        }

        const response = payload.response ?? "";
        updateMessage(loaderId.id, {
          content: response,
          streaming: false,
          meta: { intent: payload.intent, action: payload.action, source: "voice" },
        });
        const subtitle = toSubtitleText(response);
        const wordCount = subtitle.trim().split(/\s+/).filter(Boolean).length;
        const duration = Math.max(2500, Math.min((wordCount / 2.8) * 1000, 30000));
        speakingTextRef.current = normalizeText(subtitle);
        setAvatarState("speaking");
        const speechSessionId = speechSessionRef.current + 1;
        speechSessionRef.current = speechSessionId;
        if (cv.speakBack && subtitle) {
          cancelKaraoke();
          karaokeRef.current = startKaraoke(subtitle, cv.rate, setSpeechText);
          apiVoiceSpeak(subtitle, cv).catch(() => {/* non-critical */});
          if (conversationActiveRef.current) {
            if ((payload.action ?? "") !== "voice_enrollment") {
              startInterruptListener();
            }
            const restartDelay = duration + ((payload.action ?? "") === "voice_enrollment" ? 700 : 180);
            settleTimerRef.current = window.setTimeout(() => {
              if (
                disposed ||
                speechSessionRef.current !== speechSessionId ||
                responseTurnRef.current !== turnId ||
                !conversationActiveRef.current ||
                captureActiveRef.current
              ) {
                return;
              }
              stopInterruptListener();
              startCapture(0);
              settleTimerRef.current = null;
            }, restartDelay);
            return;
          }
        } else if (subtitle) {
          setSpeechText(subtitle);
        }
        if (conversationActiveRef.current) {
          startInterruptListener();
          // No TTS playback; use estimated settle to keep the loop moving.
          settleTimerRef.current = window.setTimeout(() => {
            if (
              !disposed &&
              speechSessionRef.current === speechSessionId &&
              responseTurnRef.current === turnId &&
              conversationActiveRef.current &&
              !captureActiveRef.current
            ) {
              stopInterruptListener();
              startCapture(0);
            }
            settleTimerRef.current = null;
          }, duration + 120);
          return;
        }

        settleTimerRef.current = window.setTimeout(() => {
          if (!disposed && responseTurnRef.current === turnId) {
            setAvatarState("idle");
          }
          settleTimerRef.current = null;
        }, duration);
      } catch (error) {
        updateMessage(loaderId.id, {
          role: "error",
          content: error instanceof Error ? error.message : "Voice request failed",
          streaming: false,
        });
        if (!disposed) setAvatarState("idle");
        if (!disposed && conversationActiveRef.current) {
          scheduleTimeout(() => startCapture(0), 350);
          return;
        }
      }

      // Restart wake listening only if still active.
      if (!disposed && voiceRef.current.handsFreeWake) {
        scheduleTimeout(startWake, 600);
      }
    };

    const startCapture = (attempt = 0) => {
      if (disposed) return;
      listeningPausedRef.current = false;
      if (captureActiveRef.current && captureRef.current) return;
      clearScheduledTimeout();
      clearSettleTimer();
      stopInterruptListener();

      // Abort any leftover wake listener before capturing.
      if (recognitionRef.current) {
        recognitionRef.current.onend = null;
        recognitionRef.current.abort();
        recognitionRef.current = null;
      }

      captureActiveRef.current = true;
      transitioningToCaptureRef.current = false;
      captureStartedAtRef.current = Date.now();
      audioCaptureRef.current = null;
      void startAudioCaptureSession().then((session) => {
        if (!disposed && captureActiveRef.current) {
          audioCaptureRef.current = session;
          return;
        }
        if (session) {
          void session.stop().catch(() => {});
        }
      }).catch(() => {
        audioCaptureRef.current = null;
      });

      const capture = new SpeechRecognitionAPI();
      capture.lang = "en-US";
      capture.continuous = false;
      capture.interimResults = true;
      capture.maxAlternatives = 1;
      captureRef.current = capture;
      setAvatarState("listening");
      setVoiceWakeActive(false);

      let lastFinal = "";
      let lastInterim = "";
      let heardSpeech = false;

      capture.onresult = (e: any) => {
        heardSpeech = true;
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const t = e.results[i][0].transcript;
          if (e.results[i].isFinal) {
            lastFinal += " " + t;
            lastInterim = "";
          } else {
            lastInterim = t;
          }
        }
      };

      capture.onspeechend = () => {
        // Only stop if enough time has passed (min 1400ms listen window).
        const elapsed = Date.now() - captureStartedAtRef.current;
        if (elapsed >= 1400) {
          capture.stop();
        }
        // Otherwise ignore early onspeechend — keep listening until onend fires naturally.
      };

      capture.onend = () => {
        if (disposed) return;
        captureRef.current = null;
        const best = lastFinal.trim() || lastInterim.trim();
        const elapsed = Date.now() - captureStartedAtRef.current;

        // If capture closes too quickly without hearing anything, retry twice.
        if (!best && !heardSpeech && elapsed < 2500 && attempt < 2) {
          captureActiveRef.current = false;
          scheduleTimeout(() => startCapture(attempt + 1), 280);
          return;
        }

        // Strip any trailing wake-word artifact heard at the start of capture.
        const cleaned = best
          .replace(/^\s*(hi|hey|ok|okay)\s+nova\b\s*/i, "")
          .replace(/^\s*nova\b\s*/i, "")
          .trim();
        captureAndRespond(cleaned);
      };

      capture.onerror = (e: any) => {
        if (disposed) return;
        captureRef.current = null;
        captureActiveRef.current = false;
        if (e.error === "not-allowed") {
          setAvatarState("idle");
          setVoiceWakeActive(false);
          return;
        }
        // Fast retry for transient engine errors to avoid requiring page refresh.
        if (e.error === "aborted" || e.error === "network" || e.error === "audio-capture") {
          scheduleTimeout(() => startCapture(Math.min(attempt + 1, 2)), 180 + attempt * 120);
          return;
        }
        if (conversationActiveRef.current) {
          scheduleTimeout(() => startCapture(Math.min(attempt + 1, 2)), 350 + attempt * 200);
          return;
        }
        if (voiceRef.current.handsFreeWake) {
          scheduleTimeout(startWake, 1200);
        }
      };

      try {
        capture.start();
      } catch {
        captureRef.current = null;
        captureActiveRef.current = false;
        if (attempt < 2) {
          scheduleTimeout(() => startCapture(attempt + 1), 400 + attempt * 250);
          return;
        }
        if (conversationActiveRef.current) {
          scheduleTimeout(() => startCapture(0), 700);
          return;
        }
        if (voiceRef.current.handsFreeWake) {
          scheduleTimeout(startWake, 1200);
        }
      }
    };

    const startWake = () => {
      if (disposed) return;
      if (listeningPausedRef.current) {
        setVoiceWakeActive(false);
        setAvatarState("idle");
        return;
      }
      // Don't start a new wake listener while capture is active.
      if (captureActiveRef.current) return;
      clearSettleTimer();

      if (recognitionRef.current) {
        recognitionRef.current.onend = null;
        recognitionRef.current.abort();
        recognitionRef.current = null;
      }

      const wake = new SpeechRecognitionAPI();
      wake.lang = "en-US";
      wake.continuous = true;
      wake.interimResults = false;
      wake.maxAlternatives = 1;
      recognitionRef.current = wake;
      setVoiceWakeActive(true);
      // Stay visually idle while passively waiting for the wake word.
      setAvatarState("idle");

      wake.onresult = (e: any) => {
        if (transitioningToCaptureRef.current) return;
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const result = e.results[i];
          if (!result?.isFinal) continue;
          const transcript = String(result[0]?.transcript || "").toLowerCase().trim();
          const normalized = normalizeText(transcript);
          const confidence = Number(result[0]?.confidence ?? 0);
          const wakeDetected =
            /\b(hi|hey|hello|ok|okay)\s+nova\b/.test(normalized) ||
            normalized === "nova" ||
            normalized.startsWith("nova ");

          const confidenceOk = confidence === 0 || confidence >= 0.45;

          if (wakeDetected && confidenceOk) {
            conversationActiveRef.current = true;
            transitioningToCaptureRef.current = true;
            setVoiceWakeActive(false);
            // Detach onend before stopping so it doesn't restart wake.
            wake.onend = null;
            wake.abort();
            recognitionRef.current = null;
            // Short delay so mic clears the tail of the wake word.
            window.setTimeout(() => startCapture(0), 120);
            return;
          }
        }
      };

      wake.onend = () => {
        if (disposed) return;
        recognitionRef.current = null;
        // Only restart if capture is NOT in progress.
        if (!captureActiveRef.current && !transitioningToCaptureRef.current && voiceRef.current.handsFreeWake) {
          scheduleTimeout(startWake, 500);
        }
      };

      wake.onerror = (e: any) => {
        if (disposed) return;
        if (e.error === "not-allowed") {
          setAvatarState("idle");
          setVoiceWakeActive(false);
          return;
        }
        // Recover faster on transient wake listener errors.
        if (e.error === "aborted" || e.error === "network" || e.error === "audio-capture") {
          if (!captureActiveRef.current && !transitioningToCaptureRef.current && voiceRef.current.handsFreeWake) {
            scheduleTimeout(startWake, 220);
          }
          return;
        }
        if (!captureActiveRef.current && !transitioningToCaptureRef.current && voiceRef.current.handsFreeWake) {
          scheduleTimeout(startWake, 1200);
        }
      };

      try {
        wake.start();
      } catch {
        setVoiceWakeActive(false);
        if (!captureActiveRef.current && voiceRef.current.handsFreeWake) {
          scheduleTimeout(startWake, 1200);
        }
      }
    };

    if (manualListenRequested) {
      handledListenSignalRef.current = voiceListenSignal;
      // Manual mic tap should take over instantly from any ongoing speech/playback.
      responseTurnRef.current += 1;
      speechSessionRef.current += 1;
      clearSettleTimer();
      stopInterruptListener();
      cancelKaraoke();
      setSpeechText(null);
      window.speechSynthesis?.cancel();
      apiVoiceStop().catch(() => {/* non-critical */});
      startCapture();
    } else {
      startWake();
    }

    // Recover from silent recognition stalls without needing manual refresh.
    const recoverWakeIfNeeded = () => {
      if (disposed) return;
      if (!voiceRef.current.enabled) return;
      if (listeningPausedRef.current) return;
      if (!voiceRef.current.handsFreeWake && !conversationActiveRef.current) return;
      if (captureActiveRef.current || transitioningToCaptureRef.current) return;
      if (recognitionRef.current) return;
      startWake();
    };

    const onVisibilityOrFocus = () => {
      if (document.visibilityState === "visible") {
        recoverWakeIfNeeded();
      }
    };

    window.addEventListener("focus", onVisibilityOrFocus);
    document.addEventListener("visibilitychange", onVisibilityOrFocus);
    wakeWatchdogRef.current = window.setInterval(recoverWakeIfNeeded, 3000);

    return () => {
      disposed = true;
      window.removeEventListener("focus", onVisibilityOrFocus);
      document.removeEventListener("visibilitychange", onVisibilityOrFocus);
      clearWakeWatchdog();
      if (timeoutRef.current !== null) {
        window.clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
      if (settleTimerRef.current !== null) {
        window.clearTimeout(settleTimerRef.current);
        settleTimerRef.current = null;
      }
      if (recognitionRef.current) {
        recognitionRef.current.onend = null;
        recognitionRef.current.abort();
        recognitionRef.current = null;
      }
      if (captureRef.current) {
        captureRef.current.onend = null;
        captureRef.current.abort();
        captureRef.current = null;
      }
      if (audioCaptureRef.current) {
        void audioCaptureRef.current.stop().catch(() => {});
        audioCaptureRef.current = null;
      }
      if (interruptRef.current) {
        interruptRef.current.onend = null;
        interruptRef.current.abort();
        interruptRef.current = null;
      }
      captureActiveRef.current = false;
      transitioningToCaptureRef.current = false;
      conversationActiveRef.current = false;
      setVoiceWakeActive(false);
    };
  // Only re-run when the on/off switches change or a manual listen is requested.
  // All other voice properties are read via voiceRef.current.
  }, [SpeechRecognitionAPI, voice.enabled, voice.handsFreeWake, voiceListenSignal,
      addMessage, updateMessage, setAvatarState, setSpeechText, setVoiceWakeActive]);
}
