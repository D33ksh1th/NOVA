/* ================================================================
   NOVA Companion 2 — JavaScript runtime
   • SSE avatar state sync
   • Full chat (text + voice) with wake-word listener
   • Settings panel controls wired to /voice/* APIs
   • Eye tracking, pet animation, media avatar
   ================================================================ */
"use strict";

// ── DOM refs ─────────────────────────────────────────────────────
const cat         = document.getElementById("cat");
const headGroup   = document.getElementById("headGroup");
const pupilL      = document.getElementById("pupilL");
const pupilR      = document.getElementById("pupilR");
const stage       = document.getElementById("stage");
const voiceRing   = document.getElementById("voiceRing");

const stateLabel  = document.getElementById("stateLabel");
const wakeTag     = document.getElementById("wakeTag");
const micTag      = document.getElementById("micTag");
const avDot       = document.getElementById("avDot");

const connDot     = document.getElementById("connDot");
const connText    = document.getElementById("connText");

const chatLog     = document.getElementById("chatLog");
const chatInput   = document.getElementById("chatInput");
const sendBtn     = document.getElementById("sendBtn");
const micBtn      = document.getElementById("micBtn");
const typingIndicator = document.getElementById("typingIndicator");
const micStatus   = document.getElementById("micStatus");

const petBtn      = document.getElementById("petBtn");
const loadMediaBtn= document.getElementById("loadMediaBtn");
const useBuiltinBtn= document.getElementById("useBuiltinBtn");
const mediaInput  = document.getElementById("mediaInput");
const mediaLayer  = document.getElementById("mediaLayer");
const catVideo    = document.getElementById("catVideo");
const catImage    = document.getElementById("catImage");

const fabSettings = document.getElementById("fabSettings");
const settingsPanel= document.getElementById("settingsPanel");
const settingsClose= document.getElementById("settingsClose");
const layout      = document.querySelector(".layout");

const micToggle       = document.getElementById("micToggle");
const handsFreeToggle = document.getElementById("handsFreeToggle");
const speakToggle     = document.getElementById("speakToggle");
const voiceModeSelect = document.getElementById("voiceModeSelect");
const voiceStyleSelect= document.getElementById("voiceStyleSelect");
const accentProfileSelect= document.getElementById("accentProfileSelect");
const voiceRateSelect = document.getElementById("voiceRateSelect");
const voicePitchSelect= document.getElementById("voicePitchSelect");
const voiceModelSelect= document.getElementById("voiceModelSelect");
const voiceNote       = document.getElementById("voiceNote");
const syncVoiceBtn    = document.getElementById("syncVoiceBtn");
const stopSpeakBtn    = document.getElementById("stopSpeakBtn");
const wakeStatusBox   = document.getElementById("wakeStatusBox");
const openConsoleBtn  = document.getElementById("openConsoleBtn");

// ── state vars ────────────────────────────────────────────────────
let avatarSource = null;
let avatarReconnectTimer = null;
let pointerResetTimer = null;
let currentObjectUrl = "";
let mediaMode = false;

let recognizer = null;
let wakeRecognizer = null;
let isListening = false;
let isWakeListen = false;
let wakeConversationActive = false;
let wakeDetectionCooldownUntil = 0;
let voiceTurnInFlight = false;

let browserVoices = [];
let preferredVoice = null;
let speechToken = 0;
let uiSpeakEnabled = true;

let selectedVoiceStyle = "clear";
let selectedVoiceMode = "human";
let selectedAccentProfile = "indian_clear";

const voiceStyleMap = { natural: null, warm: null, clear: null, excited: null };

const VOICE_STYLE_PROFILES = {
  natural: { baseRate: 0.90, basePitch: 1.00, volume: 0.95 },
  warm:    { baseRate: 0.86, basePitch: 0.96, volume: 0.95 },
  clear:   { baseRate: 0.95, basePitch: 1.02, volume: 0.94 },
  excited: { baseRate: 1.02, basePitch: 1.08, volume: 0.96 },
};

const VOICE_PROFILE = { defaultLang: "en-IN", maxChunkLength: 220 };

const WAKE_WORDS = ["hey nova", "ok nova", "hello nova", "nova"];
const STOP_PHRASES = ["stop", "exit", "stop listening", "thats it for now", "that is it for now", "no thanks"];

const EVENT_TO_STATE = {
  listening_started: "listening",
  listening_completed: "idle",
  thinking_started: "thinking",
  thinking_completed: "idle",
  speaking_started: "speaking",
  speaking_completed: "idle",
  idle: "idle",
};

const GREETINGS = [
  "Hi! I'm NOVA. What do you need?",
  "Hey there — NOVA is listening.",
  "Hello! I'm ready for your command.",
];

// ── avatar state ─────────────────────────────────────────────────
function setAvatarState(state) {
  const s = (state || "idle").toLowerCase();
  cat.dataset.state = s;
  mediaLayer.dataset.state = s;
  stateLabel.textContent = s;
  voiceRing.classList.toggle("active", s === "speaking");
}

// ── SSE connection ────────────────────────────────────────────────
function connectAvatarSSE() {
  if (avatarSource) { avatarSource.close(); avatarSource = null; }
  if (avatarReconnectTimer) { clearTimeout(avatarReconnectTimer); }

  const src = new EventSource("/avatar/events");
  avatarSource = src;

  src.onopen = () => {
    connDot.className = "status-dot on";
    connText.textContent = "Connected to NOVA";
  };

  src.onerror = () => {
    connDot.className = "status-dot err";
    connText.textContent = "Reconnecting…";
    src.close();
    avatarReconnectTimer = setTimeout(connectAvatarSSE, 2200);
  };

  src.addEventListener("snapshot", (e) => {
    const p = tryParse(e.data);
    if (p?.state) setAvatarState(p.state);
  });

  Object.keys(EVENT_TO_STATE).forEach((name) => {
    src.addEventListener(name, (e) => {
      const p = tryParse(e.data);
      setAvatarState(p?.state || EVENT_TO_STATE[name]);
    });
  });

  src.onmessage = (e) => {
    const p = tryParse(e.data);
    if (p) setAvatarState(p.state || EVENT_TO_STATE[p.event] || "idle");
  };
}

// ── chat UI ───────────────────────────────────────────────────────
function scrollToBottom() {
  chatLog.scrollTop = chatLog.scrollHeight;
}

function appendMessage(role, text, meta = "") {
  const isUser = role === "You";
  const wrap = document.createElement("div");
  wrap.className = `msg ${isUser ? "user" : "nova"}`;

  const ava = document.createElement("div");
  ava.className = "msg-avatar";
  ava.textContent = isUser ? "👤" : "🐱";

  const bub = document.createElement("div");
  bub.className = "bubble";

  const roleEl = document.createElement("p");
  roleEl.className = "msg-role";
  roleEl.textContent = role;

  const textEl = document.createElement("div");
  renderContent(textEl, String(text || ""));

  bub.appendChild(roleEl);
  bub.appendChild(textEl);

  if (meta) {
    const metaEl = document.createElement("p");
    metaEl.className = "msg-meta";
    metaEl.textContent = meta;
    bub.appendChild(metaEl);
  }

  wrap.appendChild(ava);
  wrap.appendChild(bub);
  chatLog.appendChild(wrap);
  scrollToBottom();
  return wrap;
}

function renderContent(container, text) {
  if (!text.includes("```")) {
    container.textContent = text;
    return;
  }
  const pattern = /```([a-zA-Z0-9_+-]*)\n?([\s\S]*?)```/g;
  let cursor = 0;
  let match = pattern.exec(text);
  while (match) {
    const [full, lang, code] = match;
    if (match.index > cursor) {
      container.appendChild(document.createTextNode(text.slice(cursor, match.index)));
    }
    const block = document.createElement("div");
    block.className = "code-block";
    const head = document.createElement("div");
    head.className = "code-head";
    const langTag = document.createElement("span");
    langTag.textContent = lang || "code";
    const copyBtn = document.createElement("button");
    copyBtn.className = "code-copy-btn";
    copyBtn.textContent = "Copy";
    copyBtn.addEventListener("click", () => copyText(code.trim(), copyBtn));
    head.appendChild(langTag);
    head.appendChild(copyBtn);
    const pre = document.createElement("pre");
    pre.textContent = code.replace(/\n$/, "");
    block.appendChild(head);
    block.appendChild(pre);
    container.appendChild(block);
    cursor = match.index + full.length;
    match = pattern.exec(text);
  }
  if (cursor < text.length) {
    container.appendChild(document.createTextNode(text.slice(cursor)));
  }
}

async function copyText(text, btn) {
  try { await navigator.clipboard.writeText(text); } catch { return; }
  const orig = btn.textContent;
  btn.textContent = "Copied!";
  setTimeout(() => { btn.textContent = orig; }, 1400);
}

function showTyping() {
  const wrap = document.createElement("div");
  wrap.className = "msg nova";
  wrap.id = "typingBubble";
  const ava = document.createElement("div");
  ava.className = "msg-avatar";
  ava.textContent = "🐱";
  const bub = document.createElement("div");
  bub.className = "bubble";
  bub.innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div>';
  wrap.appendChild(ava);
  wrap.appendChild(bub);
  chatLog.appendChild(wrap);
  typingIndicator.classList.remove("hidden");
  scrollToBottom();
  return wrap;
}

function removeTyping(el) {
  if (el) el.remove();
  typingIndicator.classList.add("hidden");
}

function setBusy(busy) {
  sendBtn.disabled = busy;
  chatInput.disabled = busy;
}

// ── API helpers ───────────────────────────────────────────────────
async function postJson(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function tryParse(raw) {
  try { return JSON.parse(raw); } catch { return null; }
}

function readVoiceSettings() {
  return {
    voice_mode:     selectedVoiceMode,
    voice_style:    selectedVoiceStyle,
    accent_profile: selectedAccentProfile,
    voice_rate:     parseInt(voiceRateSelect?.value || "176", 10),
    voice_pitch:    parseInt(voicePitchSelect?.value || "50", 10),
    voice_name:     voiceModelSelect?.value || "indian_pratham",
  };
}

// ── send chat ─────────────────────────────────────────────────────
async function sendChat(text, source = "chat") {
  const trimmed = text.trim();
  if (!trimmed) return;
  appendMessage("You", trimmed, source === "voice" ? "via microphone" : "");
  const loader = showTyping();
  setBusy(true);
  setAvatarState("thinking");

  try {
    const payload = await postJson("/chat", { message: trimmed });
    removeTyping(loader);
    const meta = [payload.intent && `intent: ${payload.intent}`, payload.action && `action: ${payload.action}`].filter(Boolean).join(" | ");
    appendMessage("NOVA", payload.response || "(no response)", meta);

    if (payload.initiative?.message) {
      appendMessage("NOVA", payload.initiative.message, "initiative");
    }

    setAvatarState("speaking");
    if (speakToggle.checked) {
      await speakWithBackend(payload.response || "");
    }
    setAvatarState("idle");
  } catch (err) {
    removeTyping(loader);
    appendMessage("NOVA", `Request failed: ${err.message}`, "error");
    setAvatarState("idle");
  } finally {
    setBusy(false);
  }
}

// ── voice pipeline ────────────────────────────────────────────────
async function sendVoice(text) {
  if (!text.trim() || voiceTurnInFlight) return;
  voiceTurnInFlight = true;
  appendMessage("You", text, "via microphone");
  const loader = showTyping();
  setBusy(true);
  setAvatarState("thinking");

  try {
    const payload = await postJson("/voice/text", {
      text: `Nova, ${text}`,
      speak: speakToggle.checked,
      ...readVoiceSettings(),
    });
    removeTyping(loader);
    const meta = [payload.intent && `intent: ${payload.intent}`, payload.action && `action: ${payload.action}`].filter(Boolean).join(" | ");
    appendMessage("NOVA", payload.response || "(no response)", meta);
    setAvatarState("speaking");
    if (speakToggle.checked && !isNeuralBackend(payload?.voice?.metadata?.synthesis?.backend)) {
      speakInBrowser(payload.response || "");
    }
    setAvatarState("idle");
  } catch (err) {
    removeTyping(loader);
    appendMessage("NOVA", `Voice failed: ${err.message}`, "error");
    setAvatarState("idle");
  } finally {
    setBusy(false);
    voiceTurnInFlight = false;
  }
}

async function speakWithBackend(text) {
  if (!text) return;
  try {
    await postJson("/voice/speak", { text, speak: true, ...readVoiceSettings() });
  } catch { /* backend TTS unavailable, ignore */ }
}

function isNeuralBackend(name) {
  const n = (name || "").toLowerCase();
  return n === "kokoro" || n === "piper";
}

// ── browser TTS fallback ──────────────────────────────────────────
function speakInBrowser(text) {
  if (!uiSpeakEnabled || !("speechSynthesis" in window) || !text) return;
  const cleaned = cleanSpeechText(text);
  if (!cleaned) return;
  const chunks = chunkText(cleaned, VOICE_PROFILE.maxChunkLength);
  const profile = VOICE_STYLE_PROFILES[selectedVoiceStyle] || VOICE_STYLE_PROFILES.clear;
  const voice = voiceStyleMap[selectedVoiceStyle] || preferredVoice;
  const token = ++speechToken;
  window.speechSynthesis.cancel();
  stopSpeakBtn.disabled = false;

  const speakChunk = (i) => {
    if (token !== speechToken || i >= chunks.length) { stopSpeakBtn.disabled = true; return; }
    const u = new SpeechSynthesisUtterance(chunks[i]);
    u.rate   = Math.max(0.84, Math.min(1.05, profile.baseRate));
    u.pitch  = profile.basePitch;
    u.volume = profile.volume;
    u.lang   = VOICE_PROFILE.defaultLang;
    if (voice) { u.voice = voice; if (voice.lang) u.lang = voice.lang; }
    u.onend = () => speakChunk(i + 1);
    u.onerror = () => { stopSpeakBtn.disabled = true; };
    window.speechSynthesis.speak(u);
  };
  speakChunk(0);
}

function cleanSpeechText(t) {
  return String(t || "")
    .replace(/```[\s\S]*?```/g, "")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\|/g, ", ").replace(/\s+/g, " ").trim();
}

function chunkText(t, max) {
  const sentences = (t || "").match(/[^.!?]+[.!?]?/g) || [t];
  const result = [];
  let cur = "";
  for (const s of sentences) {
    const sentence = s.trim();
    if (!sentence) continue;
    if (!cur) { cur = sentence; continue; }
    if (`${cur} ${sentence}`.length <= max) { cur += " " + sentence; continue; }
    result.push(cur);
    cur = sentence;
  }
  if (cur) result.push(cur);
  return result;
}

function initBrowserVoices() {
  if (!("speechSynthesis" in window)) return;
  const load = () => {
    browserVoices = window.speechSynthesis.getVoices() || [];
    preferredVoice = pickVoice(browserVoices);
    assignVoiceStyles(browserVoices);
  };
  load();
  window.speechSynthesis.onvoiceschanged = load;
}

function pickVoice(voices) {
  if (!voices?.length) return null;
  const indian = voices.filter(v => (v.lang||"").startsWith("en-IN") || (v.name||"").toLowerCase().includes("india"));
  const preferred = ["lekha","neerja","heera","rishi","aditi","priya"];
  for (const h of preferred) {
    const m = voices.find(v => (v.name||"").toLowerCase().includes(h));
    if (m) return m;
  }
  return indian[0] || voices.find(v => (v.lang||"").startsWith("en")) || voices[0] || null;
}

function assignVoiceStyles(voices) {
  const warm  = voices.find(v => /veena|lekha|serena/i.test(v.name||"")) || preferredVoice;
  const clear = voices.find(v => /neerja|heera|aria|ava/i.test(v.name||"")) || preferredVoice;
  voiceStyleMap.natural = preferredVoice;
  voiceStyleMap.warm    = warm;
  voiceStyleMap.clear   = clear;
  voiceStyleMap.excited = preferredVoice;
}

// ── Web Speech (STT) ──────────────────────────────────────────────
function normalizeSpeech(t) {
  return String(t||"").toLowerCase().replace(/[^a-z0-9\s]/g," ").replace(/\s+/g," ").trim();
}
function hasWakeWord(t) {
  const n = normalizeSpeech(t);
  return WAKE_WORDS.some(w => n.includes(w));
}
function extractAfterWake(t) {
  const n = normalizeSpeech(t);
  for (const w of WAKE_WORDS) {
    const i = n.indexOf(w);
    if (i !== -1) return n.slice(i + w.length).trim();
  }
  return "";
}
function isStopPhrase(t) {
  const n = normalizeSpeech(t);
  return STOP_PHRASES.some(p => n === p || n.includes(p));
}

function setMicStatus(text) { if (micStatus) micStatus.textContent = text; }
function setWakeStatus(text) { if (wakeStatusBox) wakeStatusBox.textContent = text; }
function updateWakeTags() {
  const wakeon = handsFreeToggle.checked && micToggle.checked;
  wakeTag.textContent = wakeon ? "wake: on" : "wake: off";
  wakeTag.style.color = wakeon ? "var(--green)" : "";
  micTag.className = "tag tag-mic" + (micToggle.checked ? " active" : "");
  micTag.textContent = micToggle.checked ? "mic: on" : "mic: off";
}

function initSpeechRecognition() {
  const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Ctor) {
    micBtn.disabled = true;
    setMicStatus("Speech not supported in this browser");
    return;
  }

  // Main recognizer
  recognizer = new Ctor();
  recognizer.continuous   = true;
  recognizer.interimResults = false;
  recognizer.lang         = "en-US";

  recognizer.onstart  = () => {
    isListening = true;
    setAvatarState("listening");
    micBtn.classList.add("listening");
    setMicStatus("Listening…");
  };
  recognizer.onend = () => {
    isListening = false;
    micBtn.classList.remove("listening");
    setMicStatus(wakeConversationActive ? "Voice mode active" : "Mic off");
    setAvatarState("idle");
    if (wakeConversationActive && micToggle.checked) {
      setTimeout(() => {
        if (wakeConversationActive && !isListening) {
          try { recognizer.start(); } catch { /* ignore */ }
        }
      }, 250);
      return;
    }
    startWakeListener();
  };
  recognizer.onerror = (e) => {
    if (e.error !== "no-speech") appendMessage("NOVA", `Mic error: ${e.error}`, "voice");
    setAvatarState("idle");
  };
  recognizer.onresult = async (e) => {
    for (let i = e.resultIndex; i < e.results.length; i++) {
      if (!e.results[i].isFinal) continue;
      const t = e.results[i][0]?.transcript?.trim() || "";
      if (!t) continue;
      if (wakeConversationActive && isStopPhrase(t)) {
        endWakeConversation();
        return;
      }
      await sendVoice(t);
      return;
    }
  };

  // Wake recognizer
  wakeRecognizer = new Ctor();
  wakeRecognizer.continuous    = true;
  wakeRecognizer.interimResults = true;
  wakeRecognizer.lang          = "en-US";

  wakeRecognizer.onstart  = () => { isWakeListen = true; setWakeStatus("Listening for wake word: hey nova, ok nova, nova"); };
  wakeRecognizer.onend    = () => {
    isWakeListen = false;
    if (handsFreeToggle.checked && micToggle.checked && !isListening) {
      setTimeout(startWakeListener, 400);
    } else {
      setWakeStatus("Wake listening is off.");
    }
  };
  wakeRecognizer.onerror  = (e) => { if (handsFreeToggle.checked) setWakeStatus(`Wake error: ${e.error}`); };
  wakeRecognizer.onresult = (e) => {
    for (let i = e.resultIndex; i < e.results.length; i++) {
      if (!e.results[i].isFinal) continue;
      const t = e.results[i][0]?.transcript?.trim() || "";
      if (!t || !hasWakeWord(t)) continue;
      const now = Date.now();
      if (now < wakeDetectionCooldownUntil) continue;
      wakeDetectionCooldownUntil = now + 1800;
      const cmd = extractAfterWake(t);
      beginWakeConversation(cmd);
      return;
    }
  };
}

function startWakeListener() {
  if (!wakeRecognizer || !handsFreeToggle.checked || !micToggle.checked || isListening || isWakeListen || wakeConversationActive) return;
  try { wakeRecognizer.start(); } catch { /* already running */ }
}

function stopWakeListener() {
  if (wakeRecognizer && isWakeListen) wakeRecognizer.stop();
}

function beginWakeConversation(initialCmd = "") {
  wakeConversationActive = true;
  stopWakeListener();
  const greeting = GREETINGS[Math.floor(Math.random() * GREETINGS.length)];
  appendMessage("NOVA", greeting, "wake-word");
  setWakeStatus("Conversation active. Say stop or exit to end.");
  updateWakeTags();
  if (initialCmd) sendVoice(initialCmd);
  if (!isListening && recognizer) {
    try { recognizer.start(); } catch { /* ignore */ }
  }
}

function endWakeConversation() {
  wakeConversationActive = false;
  appendMessage("NOVA", "Stopping voice conversation. Say a wake word when you need me.", "wake-word");
  if (isListening && recognizer) recognizer.stop();
  if (handsFreeToggle.checked && micToggle.checked) {
    setWakeStatus("Wake listener active.");
    startWakeListener();
  } else {
    setWakeStatus("Wake listening is off.");
  }
  updateWakeTags();
}

// ── eye tracking ──────────────────────────────────────────────────
function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)); }

function moveEyes(cx, cy) {
  const rect = headGroup.getBoundingClientRect();
  const rx = clamp((cx - (rect.left + rect.width  / 2)) / rect.width,  -0.5, 0.5);
  const ry = clamp((cy - (rect.top  + rect.height / 2)) / rect.height, -0.5, 0.5);
  const dx = rx * 5;
  const dy = ry * 4;
  pupilL.style.transform = `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px))`;
  pupilR.style.transform = `translate(calc(-50% + ${dx}px), calc(-50% + ${dy}px))`;
}

function resetEyes() {
  pupilL.style.transform = "translate(-50%, -50%)";
  pupilR.style.transform = "translate(-50%, -50%)";
}

// ── media avatar ──────────────────────────────────────────────────
function useBuiltinMode() {
  mediaMode = false;
  mediaLayer.classList.add("hidden");
  cat.classList.remove("hidden");
  connText.textContent = "Animated cat active";
}

function activateMediaMode() {
  mediaMode = true;
  cat.classList.add("hidden");
  mediaLayer.classList.remove("hidden");
}

function clearMedia() {
  if (currentObjectUrl) { URL.revokeObjectURL(currentObjectUrl); currentObjectUrl = ""; }
  catVideo.pause();
  catVideo.removeAttribute("src");
  catImage.removeAttribute("src");
  mediaLayer.classList.remove("has-video", "has-image");
}

function loadMediaFile(file) {
  if (!file) return;
  clearMedia();
  const url = URL.createObjectURL(file);
  currentObjectUrl = url;
  if (file.type.startsWith("video/")) {
    mediaLayer.classList.add("has-video");
    catVideo.src = url;
    catVideo.play().catch(() => {});
    connText.textContent = `Video: ${file.name}`;
  } else if (file.type.startsWith("image/")) {
    mediaLayer.classList.add("has-image");
    catImage.src = url;
    connText.textContent = `Image: ${file.name}`;
  } else {
    connText.textContent = "Unsupported file type.";
    return;
  }
  activateMediaMode();
}

// ── voice settings sync ───────────────────────────────────────────
async function syncVoiceSettings() {
  voiceNote.textContent = "Syncing…";
  const prefs = readVoiceSettings();
  try {
    await postJson("/voice/settings", prefs);
    voiceNote.textContent = "Voice settings applied.";
  } catch (err) {
    voiceNote.textContent = `Error: ${err.message}`;
  }
}

// ── avatar emit ───────────────────────────────────────────────────
async function emitAvatarEvent(event) {
  try {
    await postJson("/avatar/emit", { event, payload: { source: "companion_manual" } });
  } catch { /* ignore */ }
}

// ── settings panel toggle ─────────────────────────────────────────
function openSettings() {
  layout.classList.add("settings-open");
  fabSettings.classList.add("active");
}
function closeSettings() {
  layout.classList.remove("settings-open");
  fabSettings.classList.remove("active");
}

// ── event wiring ──────────────────────────────────────────────────

// send button / enter key
sendBtn.addEventListener("click", () => {
  const text = chatInput.value.trim();
  if (!text) return;
  chatInput.value = "";
  sendChat(text);
});

chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendBtn.click();
  }
});

// mic push-to-talk
micBtn.addEventListener("click", () => {
  if (!recognizer) { appendMessage("NOVA", "Enable microphone access in your browser settings.", "voice"); return; }
  if (!micToggle.checked) { micToggle.checked = true; updateWakeTags(); }
  if (isListening) {
    recognizer.stop();
    return;
  }
  wakeConversationActive = false;
  stopWakeListener();
  recognizer.start();
});

// pet cat
petBtn.addEventListener("click", async () => {
  cat.style.setProperty("--fy", "-10px");
  setTimeout(() => cat.style.setProperty("--fy", "0px"), 200);
  await emitAvatarEvent("speaking_started");
  setTimeout(() => emitAvatarEvent("idle"), 900);
});

// media
loadMediaBtn.addEventListener("click", () => mediaInput.click());
useBuiltinBtn.addEventListener("click", () => { clearMedia(); useBuiltinMode(); });
mediaInput.addEventListener("change", () => {
  const f = mediaInput.files?.[0];
  loadMediaFile(f);
  mediaInput.value = "";
});

// eye tracking
document.addEventListener("pointermove", (e) => {
  if (!mediaMode) moveEyes(e.clientX, e.clientY);
  if (pointerResetTimer) clearTimeout(pointerResetTimer);
  pointerResetTimer = setTimeout(resetEyes, 1500);
});

// settings panel
fabSettings.addEventListener("click", () => {
  layout.classList.contains("settings-open") ? closeSettings() : openSettings();
});
settingsClose.addEventListener("click", closeSettings);
openConsoleBtn.addEventListener("click", () => window.open("/app", "_blank"));

// debug state buttons
document.querySelectorAll(".state-btn").forEach((btn) => {
  btn.addEventListener("click", () => emitAvatarEvent(btn.getAttribute("data-event")));
});

// toggles
micToggle.addEventListener("change", () => {
  updateWakeTags();
  if (!micToggle.checked) {
    if (isListening && recognizer) recognizer.stop();
    stopWakeListener();
    setMicStatus("Mic off");
  }
  startWakeListener();
});

handsFreeToggle.addEventListener("change", () => {
  updateWakeTags();
  if (!handsFreeToggle.checked) {
    if (wakeConversationActive) { wakeConversationActive = false; if (isListening && recognizer) recognizer.stop(); }
    stopWakeListener();
    setWakeStatus("Wake listening is off.");
  } else {
    startWakeListener();
  }
});

speakToggle.addEventListener("change", () => {
  uiSpeakEnabled = speakToggle.checked;
  if (!uiSpeakEnabled) { speechToken++; window.speechSynthesis?.cancel(); stopSpeakBtn.disabled = true; }
});

// voice setting changes
[voiceModeSelect, voiceStyleSelect, accentProfileSelect, voiceRateSelect, voicePitchSelect, voiceModelSelect]
  .forEach(el => el?.addEventListener("change", () => {
    selectedVoiceMode   = voiceModeSelect.value;
    selectedVoiceStyle  = voiceStyleSelect.value;
    selectedAccentProfile = accentProfileSelect.value;
    if (voiceModeSelect.value === "cat") {
      voiceRateSelect.value = "140";
      voicePitchSelect.value = "60";
      voiceStyleSelect.value = "excited";
      selectedVoiceStyle = "excited";
    }
  }));

syncVoiceBtn.addEventListener("click", syncVoiceSettings);

stopSpeakBtn.addEventListener("click", () => {
  speechToken++;
  window.speechSynthesis?.cancel();
  stopSpeakBtn.disabled = true;
});

// ── boot ──────────────────────────────────────────────────────────
(function boot() {
  selectedVoiceMode  = voiceModeSelect.value;
  selectedVoiceStyle = voiceStyleSelect.value;
  selectedAccentProfile = accentProfileSelect.value;

  initBrowserVoices();
  initSpeechRecognition();
  useBuiltinMode();
  setAvatarState("idle");
  resetEyes();
  connectAvatarSSE();
  updateWakeTags();
  openSettings(); // show settings on first load

  appendMessage("NOVA", "Companion is online. Chat with me here, or say 'hey nova' to start a voice conversation.", "system");

  // try to load backend voice settings
  fetch("/voice/status")
    .then(r => r.ok ? r.json() : null)
    .then(data => {
      if (data?.controls?.current) {
        const c = data.controls.current;
        if (c.voice_mode && voiceModeSelect) voiceModeSelect.value = c.voice_mode;
        if (c.accent_profile && accentProfileSelect) accentProfileSelect.value = c.accent_profile;
        voiceNote.textContent = "Loaded backend voice profile.";
      }
    })
    .catch(() => { voiceNote.textContent = "Backend voice status unavailable."; });
})();
