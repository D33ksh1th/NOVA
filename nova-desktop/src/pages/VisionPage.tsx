import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Camera, Eye, Loader2, Mic, Square, Trash2, UserRoundCheck } from "lucide-react";
import {
  apiIdentitySync,
  apiGetFacialRecognition,
  apiSetFacialRecognition,
  apiVoiceEnrollmentAnswer,
  apiVoiceEnrollmentStart,
  apiVoiceSpeakers,
  apiVoiceText,
  apiVisionFaceAnalyze,
  apiVisionFaceDeleteProfile,
  apiVisionFaceEnroll,
  apiVisionFaceProfiles,
  apiVisionFaceRecognize,
  apiVisionFaceSession,
  apiVisionFaceSessionReset,
} from "@/services/api";
import { useSettingsStore } from "@/stores/useSettingsStore";
import type {
  FaceDetectedAttributes,
  FaceFrameAnalysisResponse,
  FacePresenceSession,
  FaceProfileSummary,
  FaceRecognizeResponse,
  VoiceSpeakerProfile,
  VoiceTextResponse,
} from "@/types";

const ANALYSIS_INTERVAL_MS = 950;
const REQUIRED_READY_STREAK = 3;
const AUTO_RECOGNIZE_INTERVAL_MS = 3200;

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

async function startAudioCaptureSession(onLevel?: (level: number) => void): Promise<AudioCaptureSession | null> {
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
    const data = new Float32Array(event.inputBuffer.getChannelData(0));
    chunks.push(data);
    if (onLevel) {
      let sum = 0;
      for (let i = 0; i < data.length; i++) sum += data[i] * data[i];
      onLevel(Math.min(1, Math.sqrt(sum / data.length) * 8));
    }
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
    webkitAudioContext?: typeof AudioContext;
  }
}

const EMPTY_FACE_SESSION: FacePresenceSession = {
  present: false,
  active_identity: null,
  last_seen_at: null,
  last_recognition: null,
};

function toPercent(value: number) {
  return `${Math.max(0, Math.min(100, value * 100))}%`;
}

function formatAgo(iso?: string | null) {
  if (!iso) return "-";
  const ts = Date.parse(iso);
  if (!Number.isFinite(ts)) return "-";
  const diff = Date.now() - ts;
  if (diff < 1000) return "just now";
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  return `${hr}h ago`;
}

export function VisionPage() {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [cameraOn, setCameraOn] = useState(false);
  const [busy, setBusy] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysis, setAnalysis] = useState<FaceFrameAnalysisResponse>({
    ok: true,
    ready_for_enrollment: false,
    guidance: ["Turn on camera to begin."],
  });
  const [profiles, setProfiles] = useState<FaceProfileSummary[]>([]);
  const [name, setName] = useState("Admin");
  const [role, setRole] = useState<"admin" | "user">("admin");
  const [status, setStatus] = useState("Start camera and center your face.");
  const [readyStreak, setReadyStreak] = useState(0);
  const [recognitionResult, setRecognitionResult] = useState<FaceRecognizeResponse | null>(null);
  const [deletingProfileId, setDeletingProfileId] = useState<string | null>(null);
  const [autoRecognizeEnabled, setAutoRecognizeEnabled] = useState(true);
  const [presenceSession, setPresenceSession] = useState<FacePresenceSession>(EMPTY_FACE_SESSION);
  const [greetingBanner, setGreetingBanner] = useState<string | null>(null);
  const [unknownAlertBanner, setUnknownAlertBanner] = useState<string | null>(null);
  const [liveAttrs, setLiveAttrs] = useState<FaceDetectedAttributes | null>(null);
  const [voiceProfiles, setVoiceProfiles] = useState<VoiceSpeakerProfile[]>([]);
  const [voiceName, setVoiceName] = useState("Admin");
  const [voiceEnrollmentStatus, setVoiceEnrollmentStatus] = useState("Start voice enrollment to capture speaker samples.");
  const [voiceEnrollmentBusy, setVoiceEnrollmentBusy] = useState(false);
  const [voiceEnrollmentRecording, setVoiceEnrollmentRecording] = useState(false);
  const [micLevel, setMicLevel] = useState(0);
  const [voiceEnrollmentSessionId, setVoiceEnrollmentSessionId] = useState<string | null>(null);
  const [voiceEnrollmentStage, setVoiceEnrollmentStage] = useState<string>("none");
  const [voiceEnrollmentSamplesCollected, setVoiceEnrollmentSamplesCollected] = useState(0);
  const [voiceEnrollmentRequiredSamples, setVoiceEnrollmentRequiredSamples] = useState(0);
  const [voiceSampleText, setVoiceSampleText] = useState("Matrix, this is my enrollment sample.");
  const [identityLinkBusy, setIdentityLinkBusy] = useState(false);
  const [identityLinkSummary, setIdentityLinkSummary] = useState("");
  const voiceCaptureRef = useRef<AudioCaptureSession | null>(null);
  const recognizingRef = useRef(false);
  const facialRecognitionEnabled = useSettingsStore((s) => s.facialRecognitionEnabled);
  const setFacialRecognitionEnabled = useSettingsStore((s) => s.setFacialRecognitionEnabled);

  const captureFrame = useCallback((): string | null => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || video.videoWidth <= 0 || video.videoHeight <= 0) return null;

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", 0.9);
  }, []);

  const refreshProfiles = useCallback(async () => {
    try {
      const response = await apiVisionFaceProfiles();
      if (response.ok) {
        setProfiles(response.profiles || []);
      }
    } catch {
      // Non-fatal for runtime; camera flow should still work.
    }
  }, []);

  const refreshVoiceProfiles = useCallback(async () => {
    try {
      const response = await apiVoiceSpeakers();
      if (response.ok) {
        setVoiceProfiles(response.speakers || []);
      }
    } catch {
      // Non-fatal: vision flow can continue without voice profile listing.
    }
  }, []);

  const applyVoiceEnrollmentProgress = useCallback((payload: VoiceTextResponse | { response: string; data?: Record<string, unknown> }) => {
    const message = String(payload.response || "").trim();
    const data = payload.data && typeof payload.data === "object" ? payload.data : undefined;
    const stage = typeof data?.stage === "string" ? data.stage : "none";
    const sessionId = typeof data?.session_id === "string" ? data.session_id : null;
    const samplesCollected = Number(data?.samples_collected || 0);
    const requiredSamples = Number(data?.required_samples || 0);
    const completed = Boolean(data?.completed);

    setVoiceEnrollmentStatus(message || "Voice enrollment updated.");
    setVoiceEnrollmentStage(stage);
    setVoiceEnrollmentSessionId(sessionId);
    setVoiceEnrollmentSamplesCollected(Number.isFinite(samplesCollected) ? samplesCollected : 0);
    setVoiceEnrollmentRequiredSamples(Number.isFinite(requiredSamples) ? requiredSamples : 0);

    if (stage === "await_sample" && message) {
      setVoiceSampleText(message);
    }

    if (completed) {
      setVoiceEnrollmentStage("completed");
      setVoiceEnrollmentSessionId(null);
      void refreshVoiceProfiles();
    }
  }, [refreshVoiceProfiles]);

  const linkFaceAndVoice = useCallback(async () => {
    setIdentityLinkBusy(true);
    setIdentityLinkSummary("");
    try {
      const result = await apiIdentitySync("face");
      if (!result.ok) {
        setIdentityLinkSummary(result.error || "Identity sync failed.");
        return;
      }
      setIdentityLinkSummary(
        `Identity link complete: ${result.updated_count} updated, ${result.skipped_count} skipped.`
      );
      await Promise.all([refreshProfiles(), refreshVoiceProfiles()]);
    } catch (error) {
      setIdentityLinkSummary(
        error instanceof Error ? error.message : "Identity sync request failed."
      );
    } finally {
      setIdentityLinkBusy(false);
    }
  }, [refreshProfiles, refreshVoiceProfiles]);

  const startVoiceEnrollment = useCallback(async () => {
    const trimmed = voiceName.trim();
    if (!trimmed) {
      setVoiceEnrollmentStatus("Enter a person name before starting voice enrollment.");
      return;
    }
    setVoiceEnrollmentBusy(true);
    try {
      const result = await apiVoiceEnrollmentStart(trimmed);
      applyVoiceEnrollmentProgress(result as VoiceTextResponse);
    } catch (error) {
      setVoiceEnrollmentStatus(
        error instanceof Error ? `Voice enrollment start failed: ${error.message}` : "Voice enrollment start failed."
      );
    } finally {
      setVoiceEnrollmentBusy(false);
    }
  }, [applyVoiceEnrollmentProgress, voiceName]);

  const submitVoiceEnrollmentAnswer = useCallback(async (answer: string) => {
    const trimmed = answer.trim();
    if (!trimmed) {
      setVoiceEnrollmentStatus("Enter your answer before submitting.");
      return;
    }
    setVoiceEnrollmentBusy(true);
    try {
      const result = await apiVoiceEnrollmentAnswer(trimmed, voiceEnrollmentSessionId || undefined);
      applyVoiceEnrollmentProgress(result as VoiceTextResponse);
      if (Boolean((result as { data?: Record<string, unknown> }).data?.completed)) {
        void linkFaceAndVoice();
      }
    } catch (error) {
      setVoiceEnrollmentStatus(
        error instanceof Error ? `Voice enrollment step failed: ${error.message}` : "Voice enrollment step failed."
      );
    } finally {
      setVoiceEnrollmentBusy(false);
    }
  }, [applyVoiceEnrollmentProgress, linkFaceAndVoice, voiceEnrollmentSessionId]);

  const startVoiceSampleRecording = useCallback(async () => {
    if (voiceEnrollmentRecording) return;
    try {
      const session = await startAudioCaptureSession((level) => setMicLevel(level));
      if (!session) {
        setVoiceEnrollmentStatus("Microphone capture is not available in this browser context.");
        return;
      }
      voiceCaptureRef.current = session;
      setVoiceEnrollmentRecording(true);
      setVoiceEnrollmentStatus("Recording sample... speak clearly, then click Stop & Submit Sample.");
    } catch (error) {
      setVoiceEnrollmentStatus(
        error instanceof Error ? `Mic permission failed: ${error.message}` : "Mic permission failed."
      );
    }
  }, [voiceEnrollmentRecording]);

  const stopAndSubmitVoiceSample = useCallback(async () => {
    const session = voiceCaptureRef.current;
    if (!session) return;
    voiceCaptureRef.current = null;
    setVoiceEnrollmentRecording(false);
    setMicLevel(0);

    const normalizedText = voiceSampleText.trim();
    if (normalizedText.split(/\s+/).filter(Boolean).length < 2) {
      setVoiceEnrollmentStatus("Sample text must have at least two words.");
      return;
    }

    setVoiceEnrollmentBusy(true);
    try {
      const audio = await session.stop();
      const result = await apiVoiceText({
        text: normalizedText,
        speak: false,
        audio_base64: audio.audioBase64,
        audio_mime_type: audio.audioMimeType,
      });
      applyVoiceEnrollmentProgress(result);
      if (Boolean(result.data?.completed)) {
        void linkFaceAndVoice();
      }
    } catch (error) {
      setVoiceEnrollmentStatus(
        error instanceof Error ? `Voice sample submit failed: ${error.message}` : "Voice sample submit failed."
      );
    } finally {
      setVoiceEnrollmentBusy(false);
    }
  }, [applyVoiceEnrollmentProgress, linkFaceAndVoice, voiceSampleText]);

  const stopCamera = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setCameraOn(false);
    setReadyStreak(0);
    setPresenceSession(EMPTY_FACE_SESSION);
    setGreetingBanner(null);
    setUnknownAlertBanner(null);
    apiVisionFaceSessionReset().catch(() => {});
  }, []);

  const startCamera = useCallback(async () => {
    setStatus("Requesting camera permission...");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 960 }, height: { ideal: 540 }, facingMode: "user" },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setCameraOn(true);
      setStatus("Camera ready. Follow the guidance panel.");
    } catch (error) {
      const message = error instanceof Error ? error.message : "unknown camera error";
      setStatus(`Camera access failed: ${message}`);
    }
  }, []);

  const runFrameAnalysis = useCallback(async () => {
    const image = captureFrame();
    if (!image || analyzing) return;
    setAnalyzing(true);
    try {
      const result = await apiVisionFaceAnalyze(image);
      setAnalysis(result);
      if (result.attributes) setLiveAttrs(result.attributes);
      if (result.error === "facial_recognition_disabled") {
        setReadyStreak(0);
        setStatus("Facial recognition is disabled. Enable it in Settings.");
        return;
      }
      if (result.ready_for_enrollment) {
        setReadyStreak((prev) => Math.min(REQUIRED_READY_STREAK, prev + 1));
        setStatus("Good framing detected. Hold still for stable enrollment.");
      } else if (result.primary_instruction) {
        setReadyStreak(0);
        setStatus(result.primary_instruction);
      }
    } catch {
      setAnalysis({
        ok: false,
        error: "analysis_failed",
        ready_for_enrollment: false,
        guidance: ["Unable to analyze frame. Check backend and camera."],
      });
      setStatus("Frame analysis failed. Check backend connectivity.");
      setReadyStreak(0);
    } finally {
      setAnalyzing(false);
    }
  }, [analyzing, captureFrame]);

  const enrollFace = useCallback(async () => {
    const trimmedName = name.trim();
    if (!trimmedName) {
      setStatus("Enter a person name before enrolling.");
      return;
    }
    const image = captureFrame();
    if (!image) {
      setStatus("Unable to capture frame for enrollment.");
      return;
    }
    setBusy(true);
    setStatus("Enrolling face profile...");
    try {
      const result = await apiVisionFaceEnroll({
        name: trimmedName,
        role,
        imageBase64: image,
      });
      if (result.error === "facial_recognition_disabled") {
        setFacialRecognitionEnabled(false);
      }
      setStatus(result.response || result.error || "Enrollment completed.");
      setReadyStreak(0);
      await refreshProfiles();
    } catch (error) {
      const message = error instanceof Error ? error.message : "unknown error";
      setStatus(`Enrollment failed: ${message}`);
    } finally {
      setBusy(false);
    }
  }, [captureFrame, name, refreshProfiles, role]);

  const recognizeFace = useCallback(async (mode: "manual" | "auto" = "manual") => {
    if (recognizingRef.current) return;
    const image = captureFrame();
    if (!image) {
      if (mode === "manual") {
        setStatus("Unable to capture frame for recognition.");
      }
      return;
    }
    recognizingRef.current = true;
    if (mode === "manual") {
      setBusy(true);
      setStatus("Recognizing face...");
    }
    try {
      const result = await apiVisionFaceRecognize(image);
      setRecognitionResult(result);
      if (result.attributes) setLiveAttrs(result.attributes);
      if (result.session) {
        setPresenceSession(result.session);
      }
      if (result.auto_greeting?.triggered && result.auto_greeting.message) {
        setGreetingBanner(result.auto_greeting.message);
        setStatus(result.auto_greeting.message);
        setUnknownAlertBanner(null);
      }
      if (result.unknown_alert?.triggered && result.unknown_alert.message) {
        setUnknownAlertBanner(result.unknown_alert.message);
        if (mode === "auto") {
          setStatus(result.unknown_alert.message);
        }
      }
      if (result.error === "facial_recognition_disabled") {
        setFacialRecognitionEnabled(false);
      }
      if (mode === "manual") {
        setStatus(result.response || result.error || "Recognition completed.");
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "unknown error";
      if (mode === "manual") {
        setStatus(`Recognition failed: ${message}`);
        setRecognitionResult({
          ok: false,
          error: message,
        });
      }
    } finally {
      recognizingRef.current = false;
      if (mode === "manual") {
        setBusy(false);
      }
    }
  }, [captureFrame, setFacialRecognitionEnabled]);

  const deleteProfile = useCallback(async (profileId: string, profileName: string) => {
    if (!window.confirm(`Delete face profile "${profileName}"? This cannot be undone.`)) return;
    setDeletingProfileId(profileId);
    try {
      const result = await apiVisionFaceDeleteProfile(profileId);
      if (result.ok) {
        setStatus(`Deleted profile: ${profileName}`);
        await refreshProfiles();
      } else {
        setStatus(`Delete failed: ${result.error || "unknown error"}`);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "unknown error";
      setStatus(`Delete failed: ${message}`);
    } finally {
      setDeletingProfileId(null);
    }
  }, [refreshProfiles]);

  useEffect(() => {
    refreshProfiles();
  }, [refreshProfiles]);

  useEffect(() => {
    refreshVoiceProfiles();
  }, [refreshVoiceProfiles]);

  useEffect(() => {
    apiGetFacialRecognition()
      .then((res) => setFacialRecognitionEnabled(!!res.enabled))
      .catch(() => {});
  }, [setFacialRecognitionEnabled]);

  useEffect(() => {
    apiVisionFaceSession()
      .then((res) => {
        if (res.ok && res.session) {
          setPresenceSession(res.session);
        }
      })
      .catch(() => {});
  }, []);

  const toggleFacialRecognition = useCallback(async () => {
    const next = !facialRecognitionEnabled;
    setFacialRecognitionEnabled(next);
    try {
      const res = await apiSetFacialRecognition(next);
      setFacialRecognitionEnabled(!!res.enabled);
      if (!res.enabled) {
        setReadyStreak(0);
        setStatus("Facial recognition disabled.");
        setPresenceSession(EMPTY_FACE_SESSION);
        setGreetingBanner(null);
        setUnknownAlertBanner(null);
      }
    } catch {
      setFacialRecognitionEnabled(!next);
    }
  }, [facialRecognitionEnabled, setFacialRecognitionEnabled]);

  useEffect(() => {
    if (!cameraOn) return;
    runFrameAnalysis();
    const timer = window.setInterval(runFrameAnalysis, ANALYSIS_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [cameraOn, runFrameAnalysis]);

  useEffect(() => {
    if (!cameraOn || !facialRecognitionEnabled || !autoRecognizeEnabled) return;
    const timer = window.setInterval(() => {
      void recognizeFace("auto");
    }, AUTO_RECOGNIZE_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [autoRecognizeEnabled, cameraOn, facialRecognitionEnabled, recognizeFace]);

  useEffect(() => {
    return () => stopCamera();
  }, [stopCamera]);

  useEffect(() => {
    return () => {
      if (voiceCaptureRef.current) {
        void voiceCaptureRef.current.stop();
        voiceCaptureRef.current = null;
      }
    };
  }, []);

  const guidanceList = useMemo(() => {
    if (!analysis.guidance || analysis.guidance.length === 0) {
      return ["Stay still and keep your full face visible."];
    }
    return analysis.guidance;
  }, [analysis.guidance]);

  const voiceProfileByName = useMemo(() => {
    const map = new Map<string, VoiceSpeakerProfile>();
    for (const profile of voiceProfiles) {
      const key = profile.name.trim().toLowerCase();
      if (!key) continue;
      map.set(key, profile);
    }
    return map;
  }, [voiceProfiles]);

  const faceProfileByName = useMemo(() => {
    const map = new Map<string, FaceProfileSummary>();
    for (const profile of profiles) {
      const key = profile.name.trim().toLowerCase();
      if (!key) continue;
      map.set(key, profile);
    }
    return map;
  }, [profiles]);

  const stableReady = analysis.ready_for_enrollment && readyStreak >= REQUIRED_READY_STREAK;

  const box = analysis.bbox;
  const overlayStyle = box
    ? {
        left: toPercent((box.x || 0) / Math.max(1, box.frame_w || 1)),
        top: toPercent((box.y || 0) / Math.max(1, box.frame_h || 1)),
        width: toPercent((box.w || 0) / Math.max(1, box.frame_w || 1)),
        height: toPercent((box.h || 0) / Math.max(1, box.frame_h || 1)),
      }
    : undefined;

  return (
    <div className="flex flex-col h-full">
      <div className="px-5 sm:px-8 py-6 border-b border-border flex-shrink-0">
        <div className="flex items-center gap-2">
          <Eye size={18} className="text-nova-orange" />
          <div>
            <p className="nova-panel-heading mb-1">Visual workspace</p>
            <h2 className="font-display font-medium text-2xl text-text-primary">Vision</h2>
          </div>
        </div>
      </div>

      <div className="flex-1 min-h-0 grid grid-cols-1 xl:grid-cols-[1.3fr_1fr] gap-6 px-5 sm:px-8 py-6 overflow-auto">
        <section className="min-w-0">
          <div className="flex flex-wrap gap-3 items-center justify-between mb-4">
            <h3 className="font-display font-semibold text-text-primary">Live Camera</h3>
            <div className="flex flex-wrap items-center gap-2">
              <label className="flex items-center gap-2 text-xs text-text-secondary"><input type="checkbox" checked={autoRecognizeEnabled} onChange={() => setAutoRecognizeEnabled(previous => !previous)} className="accent-nova-orange" />Auto recognize</label>
              <label className="flex items-center gap-2 text-xs text-text-secondary"><input type="checkbox" checked={facialRecognitionEnabled} onChange={() => void toggleFacialRecognition()} className="accent-nova-orange" />Face ID</label>
              {!cameraOn ? (
                <button
                  type="button"
                  onClick={startCamera}
                  className="px-3 py-1.5 rounded-lg bg-nova-orange text-black text-sm font-semibold"
                >
                  <Camera size={14} className="inline mr-1" /> Start Camera
                </button>
              ) : (
                <button
                  type="button"
                  onClick={stopCamera}
                  className="px-3 py-1.5 rounded-lg border border-border text-text-primary text-sm"
                >
                  Stop Camera
                </button>
              )}
            </div>
          </div>

          <div className="relative w-full overflow-hidden rounded-lg border border-border bg-bg-secondary aspect-video">
            <video ref={videoRef} className="w-full h-full object-cover" muted playsInline autoPlay />
            {!cameraOn && <div className="absolute inset-0 flex flex-col items-center justify-center text-text-muted gap-3"><Camera size={32} strokeWidth={1.2} /><span className="text-sm">Camera off</span></div>}
            {overlayStyle ? (
              <div
                className={`absolute border-2 ${analysis.ready_for_enrollment ? "border-emerald-400" : "border-amber-400"} rounded-lg transition-all duration-200`}
                style={overlayStyle}
              />
            ) : null}
            <div className="absolute bottom-2 left-2 right-2 rounded-lg bg-black/60 border border-white/10 px-3 py-2">
              <p className="text-sm text-white font-semibold">{status}</p>
            </div>
          </div>

          <canvas ref={canvasRef} className="hidden" />
        </section>

        <section className="min-w-0 border-t xl:border-t-0 xl:border-l border-border pt-6 xl:pt-0 xl:pl-6 space-y-5">
          <div>
            <h3 className="font-display font-semibold text-text-primary mb-2">Guidance</h3>
            <p className={`text-sm font-semibold ${analysis.ready_for_enrollment ? "text-emerald-400" : "text-amber-300"}`}>
              {stableReady ? "Ready for enrollment" : analysis.ready_for_enrollment ? "Hold still to stabilize" : "Adjust your face position"}
            </p>
            <p className="mt-1 text-xs text-text-muted">
              Stable frames: {readyStreak}/{REQUIRED_READY_STREAK}
            </p>
            <div className="mt-2 space-y-1 text-sm text-text-muted">
              {guidanceList.map((step, idx) => (
                <p key={`${step}-${idx}`}>• {step}</p>
              ))}
            </div>
            <div className="mt-3 text-xs text-text-muted">
              Brightness: {analysis.quality?.brightness ?? "-"} | Sharpness: {analysis.quality?.sharpness ?? "-"}
            </div>
          </div>

          <div className="grid grid-cols-1 gap-2">
            <label className="text-xs uppercase tracking-wider text-text-muted">Person name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="bg-[#101318] border border-border rounded-lg px-3 py-2 text-sm text-text-primary"
              placeholder="Deekshith"
            />
            <label className="text-xs uppercase tracking-wider text-text-muted">Role</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value === "admin" ? "admin" : "user")}
              className="bg-[#101318] border border-border rounded-lg px-3 py-2 text-sm text-text-primary"
            >
              <option value="admin">Admin</option>
              <option value="user">User</option>
            </select>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <button
              type="button"
              onClick={enrollFace}
              disabled={!cameraOn || busy || !stableReady}
              className="px-3 py-2 rounded-lg bg-emerald-500/90 text-black font-semibold disabled:opacity-50"
            >
              {busy ? <Loader2 className="inline mr-1 animate-spin" size={14} /> : <UserRoundCheck className="inline mr-1" size={14} />}
              Enroll Face
            </button>
            <button
              type="button"
              onClick={() => recognizeFace("manual")}
              disabled={!cameraOn || busy}
              className="px-3 py-2 rounded-lg border border-border text-text-primary font-semibold disabled:opacity-50"
            >
              Recognize Now
            </button>
          </div>
          <p className="text-[11px] text-sky-400/80">
            Tip: Enroll 5+ times from different angles, distances, and lighting to improve accuracy. Each enroll merges into the same profile automatically.
          </p>

          <div className="rounded-lg border border-border px-3 py-2 bg-[#0f1319]">
            <p className="text-xs uppercase tracking-wider text-text-muted">Presence Session</p>
            <p className={`text-sm font-semibold mt-1 ${presenceSession.present ? "text-emerald-300" : "text-text-primary"}`}>
              {presenceSession.present
                ? `Detected: ${presenceSession.active_identity?.name || "Unknown"} (${presenceSession.active_identity?.role || "user"})`
                : "No active recognized face"}
            </p>
            <p className="text-xs text-text-muted mt-1">
              Last seen: {formatAgo(presenceSession.last_seen_at)}
            </p>
            {presenceSession.last_recognition ? (
              <p className="text-xs text-text-muted mt-1">
                Last recognition: {presenceSession.last_recognition.recognized ? "matched" : "not matched"} via {presenceSession.last_recognition.backend || "unknown"}
              </p>
            ) : null}
          </div>

        {liveAttrs ? (
          <div className="rounded-lg border border-border px-3 py-2 bg-[#0c1015] space-y-1">
            <p className="text-xs uppercase tracking-wider text-text-muted">Live Face Attributes</p>
            <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 mt-1">
              {liveAttrs.age != null && (
                <p className="text-xs text-text-muted">Age: <span className="text-text-primary font-medium">{liveAttrs.age}</span></p>
              )}
              {liveAttrs.gender && (
                <p className="text-xs text-text-muted">Gender: <span className="text-text-primary font-medium capitalize">{liveAttrs.gender}</span></p>
              )}
              {liveAttrs.pose_yaw != null && (
                <p className="text-xs text-text-muted">Yaw: <span className={`font-medium ${Math.abs(liveAttrs.pose_yaw) > 25 ? 'text-amber-400' : 'text-text-primary'}`}>{liveAttrs.pose_yaw.toFixed(1)}°</span></p>
              )}
              {liveAttrs.pose_pitch != null && (
                <p className="text-xs text-text-muted">Pitch: <span className={`font-medium ${Math.abs(liveAttrs.pose_pitch) > 20 ? 'text-amber-400' : 'text-text-primary'}`}>{liveAttrs.pose_pitch.toFixed(1)}°</span></p>
              )}
              {liveAttrs.pose_roll != null && (
                <p className="text-xs text-text-muted">Roll: <span className="text-text-primary font-medium">{liveAttrs.pose_roll.toFixed(1)}°</span></p>
              )}
              {liveAttrs.det_score != null && (
                <p className="text-xs text-text-muted">Det confidence: <span className="text-text-primary font-medium">{Math.round(liveAttrs.det_score * 100)}%</span></p>
              )}
            </div>
          </div>
        ) : null}

          {unknownAlertBanner ? (
            <div className="rounded-lg border border-rose-500/40 px-3 py-2 bg-rose-500/10">
              <p className="text-sm font-semibold text-rose-200">{unknownAlertBanner}</p>
            </div>
          ) : null}

          {recognitionResult ? (
            <div className={`rounded-lg border px-3 py-2 ${recognitionResult.ok ? "border-emerald-500/40 bg-emerald-500/10" : "border-rose-500/40 bg-rose-500/10"}`}>
              <p className="text-sm font-semibold text-text-primary">Recognition Result</p>
              <p className="text-xs text-text-muted mt-1">{recognitionResult.response || recognitionResult.error || "No response"}</p>
              {recognitionResult.result ? (
                <p className="text-xs text-text-muted mt-1">
                  Name: {recognitionResult.result.name} | Role: {recognitionResult.result.role} | Confidence: {Math.round((recognitionResult.result.confidence || 0) * 100)}% | Backend: {recognitionResult.result.backend}
                </p>
              ) : null}
            </div>
          ) : null}

          <div>
            <h4 className="font-semibold text-sm text-text-primary mb-2">Enrolled Profiles</h4>
            <div className="max-h-44 overflow-auto space-y-2 pr-1">
              {profiles.length === 0 ? (
                <p className="text-xs text-text-muted">No face profiles enrolled yet.</p>
              ) : (
                profiles.map((profile) => (
                  <div key={profile.id} className="rounded-lg border border-border px-3 py-2 bg-[#0e1116]">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <p className="text-sm text-text-primary font-medium truncate">{profile.name}</p>
                        <span className={`text-[10px] px-2 py-0.5 rounded-full flex-shrink-0 ${profile.role === "admin" ? "bg-emerald-500/20 text-emerald-300" : "bg-white/10 text-text-muted"}`}>
                          {profile.role}
                        </span>
                        {(() => {
                          const speaker = voiceProfileByName.get(profile.name.trim().toLowerCase());
                          if (!speaker) {
                            return (
                              <span className="text-[10px] px-2 py-0.5 rounded-full flex-shrink-0 bg-amber-500/20 text-amber-300">
                                voice missing
                              </span>
                            );
                          }
                          if (speaker.id === profile.id) {
                            return (
                              <span className="text-[10px] px-2 py-0.5 rounded-full flex-shrink-0 bg-sky-500/20 text-sky-300">
                                linked
                              </span>
                            );
                          }
                          return (
                            <span className="text-[10px] px-2 py-0.5 rounded-full flex-shrink-0 bg-orange-500/20 text-orange-300">
                              id mismatch
                            </span>
                          );
                        })()}
                      </div>
                      <button
                        type="button"
                        onClick={() => deleteProfile(profile.id, profile.name)}
                        disabled={deletingProfileId === profile.id}
                        className="flex-shrink-0 p-1.5 rounded-lg border border-rose-500/30 text-rose-400 hover:bg-rose-500/10 disabled:opacity-50 transition-all"
                        title={`Delete ${profile.name}`}
                      >
                        {deletingProfileId === profile.id
                          ? <Loader2 size={12} className="animate-spin" />
                          : <Trash2 size={12} />}
                      </button>
                    </div>
                    <p className="text-[11px] text-text-muted mt-1">
                      Backend: {profile.backend}
                      {profile.sample_count != null && (
                        <> · <span className="text-sky-400">{profile.sample_count} sample{profile.sample_count !== 1 ? "s" : ""}</span></>
                      )}
                      {profile.attributes?.age != null && (
                        <> · Age ~{profile.attributes.age}</>
                      )}
                      {profile.attributes?.gender && (
                        <> · <span className="capitalize">{profile.attributes.gender}</span></>
                      )}
                    </p>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="rounded-xl border border-border bg-[#0e1116] p-3 space-y-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h4 className="font-semibold text-sm text-text-primary">Voice Enrollment</h4>
                <p className="text-[11px] text-text-muted mt-0.5">
                  Enroll speaker samples here, then link face and voice identities.
                </p>
              </div>
              <button
                type="button"
                onClick={() => void linkFaceAndVoice()}
                disabled={identityLinkBusy}
                className="px-2.5 py-1 rounded-lg bg-sky-500/20 border border-sky-500/40 text-sky-300 text-[11px] font-semibold disabled:opacity-50"
              >
                {identityLinkBusy ? "Linking..." : "Link IDs"}
              </button>
            </div>

            <label className="text-xs uppercase tracking-wider text-text-muted">Person name</label>
            <input
              value={voiceName}
              onChange={(e) => setVoiceName(e.target.value)}
              className="bg-[#101318] border border-border rounded-lg px-3 py-2 text-sm text-text-primary w-full"
              placeholder="Deekshith"
            />

            <div className="text-xs text-text-muted">
              Stage: <span className="text-text-primary font-medium">{voiceEnrollmentStage}</span>
              {voiceEnrollmentRequiredSamples > 0 ? (
                <span> · Samples: <span className="text-text-primary font-medium">{voiceEnrollmentSamplesCollected}/{voiceEnrollmentRequiredSamples}</span></span>
              ) : null}
            </div>
            <p className="text-xs text-text-secondary">{voiceEnrollmentStatus}</p>
            {identityLinkSummary ? (
              <p className="text-xs text-sky-300">{identityLinkSummary}</p>
            ) : null}

            <textarea
              value={voiceSampleText}
              onChange={(e) => setVoiceSampleText(e.target.value)}
              rows={2}
              className="bg-[#101318] border border-border rounded-lg px-3 py-2 text-sm text-text-primary w-full"
              placeholder="Read the prompted phrase clearly"
            />

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => void startVoiceEnrollment()}
                disabled={voiceEnrollmentBusy || voiceEnrollmentRecording}
                className="px-3 py-2 rounded-lg bg-emerald-500/90 text-black font-semibold disabled:opacity-50"
              >
                {voiceEnrollmentBusy ? <Loader2 className="inline mr-1 animate-spin" size={14} /> : null}
                Start Voice Enrollment
              </button>

              {!voiceEnrollmentRecording ? (
                <button
                  type="button"
                  onClick={() => void startVoiceSampleRecording()}
                  disabled={voiceEnrollmentBusy || !voiceEnrollmentSessionId || voiceEnrollmentStage !== "await_sample"}
                  className="px-3 py-2 rounded-lg border border-border text-text-primary font-semibold disabled:opacity-50"
                >
                  <Mic className="inline mr-1" size={14} /> Start Recording
                </button>
              ) : (
                <div className="flex items-center gap-2">
                  <div className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-rose-500/10 border border-rose-500/30">
                    <Mic
                      size={16}
                      className="text-rose-400"
                      style={{
                        transform: `scale(${1 + micLevel * 0.5})`,
                        opacity: 0.5 + micLevel * 0.5,
                        transition: "transform 0.08s ease-out, opacity 0.08s ease-out",
                      }}
                    />
                    <div className="flex items-end gap-[2px] h-4">
                      {[0.15, 0.3, 0.5, 0.7, 0.85].map((threshold, i) => (
                        <div
                          key={i}
                          className="w-[3px] rounded-full transition-all duration-75"
                          style={{
                            height: `${Math.max(4, micLevel > threshold ? (micLevel - threshold) * 60 + 6 : 4)}px`,
                            backgroundColor: micLevel > threshold ? "#f87171" : "#3f3f46",
                          }}
                        />
                      ))}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => void stopAndSubmitVoiceSample()}
                    disabled={voiceEnrollmentBusy}
                    className="flex-1 px-3 py-2 rounded-lg border border-rose-500/40 text-rose-300 font-semibold disabled:opacity-50"
                  >
                    <Square className="inline mr-1" size={14} /> Stop & Submit
                  </button>
                </div>
              )}
            </div>

            {voiceEnrollmentStage === "confirm_admin" ? (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                <button
                  type="button"
                  onClick={() => void submitVoiceEnrollmentAnswer("yes")}
                  disabled={voiceEnrollmentBusy}
                  className="px-3 py-2 rounded-lg bg-nova-orange text-black font-semibold disabled:opacity-50"
                >
                  Set as Admin Voice
                </button>
                <button
                  type="button"
                  onClick={() => void submitVoiceEnrollmentAnswer("no")}
                  disabled={voiceEnrollmentBusy}
                  className="px-3 py-2 rounded-lg border border-border text-text-primary font-semibold disabled:opacity-50"
                >
                  Keep as User
                </button>
                <button
                  type="button"
                  onClick={() => void submitVoiceEnrollmentAnswer("cancel enrollment")}
                  disabled={voiceEnrollmentBusy}
                  className="px-3 py-2 rounded-lg border border-rose-500/40 text-rose-300 font-semibold disabled:opacity-50"
                >
                  Cancel
                </button>
              </div>
            ) : null}

            <div>
              <p className="text-xs uppercase tracking-wider text-text-muted mb-1">Enrolled Voice Profiles</p>
              <div className="max-h-28 overflow-auto space-y-1 pr-1">
                {voiceProfiles.length === 0 ? (
                  <p className="text-xs text-text-muted">No speaker profiles enrolled yet.</p>
                ) : (
                  voiceProfiles.map((profile) => (
                    <div key={profile.id} className="text-xs text-text-secondary flex items-center gap-2">
                      <span>
                        {profile.name} · {profile.role} · {profile.samples} sample{profile.samples !== 1 ? "s" : ""}
                      </span>
                      {(() => {
                        const face = faceProfileByName.get(profile.name.trim().toLowerCase());
                        if (!face) {
                          return <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-500/20 text-amber-300">face missing</span>;
                        }
                        if (face.id === profile.id) {
                          return <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-sky-500/20 text-sky-300">linked</span>;
                        }
                        return <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-orange-500/20 text-orange-300">id mismatch</span>;
                      })()}
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>

          <p className="text-xs text-text-muted">Tip: For best results, keep one face in frame, eyes visible, and hold still when the box turns ready.</p>
        </section>
      </div>
    </div>
  );
}
