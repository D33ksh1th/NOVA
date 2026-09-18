const chatLog = document.getElementById("chatLog");
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const codeInput = document.getElementById("codeInput");
const modeChatBtn = document.getElementById("modeChatBtn");
const modeCodeBtn = document.getElementById("modeCodeBtn");
const chatPane = document.getElementById("chatPane");
const codePane = document.getElementById("codePane");
const composerHint = document.getElementById("composerHint");
const sendBtn = document.getElementById("sendBtn");
const micToggle = document.getElementById("micToggle");
const speakToggle = document.getElementById("speakToggle");
const voiceModeSelect = document.getElementById("voiceModeSelect");
const voiceStyleSelect = document.getElementById("voiceStyleSelect");
const accentProfileSelect = document.getElementById("accentProfileSelect");
const voiceRateSelect = document.getElementById("voiceRateSelect");
const voicePitchSelect = document.getElementById("voicePitchSelect");
const voiceModelSelect = document.getElementById("voiceModelSelect");
const voiceControlsNote = document.getElementById("voiceControlsNote");
const handsFreeToggle = document.getElementById("handsFreeToggle");
const pushToTalkBtn = document.getElementById("pushToTalkBtn");
const stopSpeakBtn = document.getElementById("stopSpeakBtn");
const modeText = document.getElementById("modeText");
const backendText = document.getElementById("backendText");
const voiceState = document.getElementById("voiceState");
const wakeStatus = document.getElementById("wakeStatus");

const quickActionButtons = Array.from(document.querySelectorAll(".chip"));
const tpl = document.getElementById("messageTemplate");

let recognizer = null;
let wakeRecognizer = null;
let listening = false;
let wakeListening = false;
let wakeConversationActive = false;
let wakeDetectionCooldownUntil = 0;
let voiceTurnInFlight = false;
let uiSpeakEnabled = true;
let browserVoices = [];
let preferredVoice = null;
let speechToken = 0;
let composerMode = "chat";
let selectedCodeAction = "fix";
let selectedVoiceMode = "human";
let selectedVoiceStyle = "clear";
let selectedAccentProfile = "indian_clear";
let avatarEventSource = null;
let avatarReconnectTimer = null;
let avatarStreamOnline = false;
let latestAvatarState = "idle";
let backendVoiceEnabled = false;
const voiceStyleMap = {
  natural: null,
  warm: null,
  clear: null,
};
const COPY_FEEDBACK_MS = 1400;
const HISTORY_LIMIT = 80;
const commandHistory = {
  chat: [],
  code: [],
};
const historyCursor = {
  chat: -1,
  code: -1,
};

const WAKE_WORDS = ["hey nova", "ok nova", "hello nova", "nova"];
const STOP_LISTENING_PHRASES = [
  "stop",
  "exit",
  "stop listening",
  "thats it for now",
  "that is it for now",
  "no thanks",
];
const WAKE_GREETING_VARIANTS = [
  "Hi, my name is NOVA. I am listening.",
  "Hey, I am NOVA. Tell me what you need.",
  "Hello, NOVA here. I am ready for your command.",
];

const CODE_ACTION_PROMPTS = {
  fix: "Review this code and fix bugs. Return corrected code first, then a short change summary.",
  refactor: "Refactor this code for readability and maintainability. Keep behavior same. Return full updated code.",
  explain: "Explain this code clearly, then suggest concrete improvements.",
  optimize: "Optimize this code for performance and clarity. Return improved code and why it is better.",
  tests: "Write meaningful tests for this code. Return test code and brief coverage notes.",
};

const VOICE_PROFILE = {
  defaultLang: "en-IN",
  baseRate: 0.9,
  basePitch: 1.0,
  volume: 0.95,
  maxChunkLength: 220,
};

const VOICE_STYLE_PROFILES = {
  natural: { baseRate: 0.9, basePitch: 1.0, volume: 0.95 },
  warm:    { baseRate: 0.86, basePitch: 0.96, volume: 0.95 },
  clear:   { baseRate: 0.95, basePitch: 1.02, volume: 0.94 },
  excited: { baseRate: 1.02, basePitch: 1.08, volume: 0.96 },
};

const AVATAR_STATE_FROM_EVENT = {
  listening_started: "listening",
  listening_completed: "idle",
  thinking_started: "thinking",
  thinking_completed: "idle",
  speaking_started: "speaking",
  speaking_completed: "idle",
  idle: "idle",
};

function normalizeAvatarState(state) {
  const value = String(state || "").toLowerCase().trim();
  if (["idle", "listening", "thinking", "speaking", "error"].includes(value)) {
    return value;
  }
  return "idle";
}

function paintAvatarState(state) {
  const next = normalizeAvatarState(state);
  latestAvatarState = next;
  voiceState.textContent = next;
  document.body.setAttribute("data-avatar-state", next);
}

function applyBackendStatusLabel(voiceEnabled) {
  if (avatarStreamOnline) {
    backendText.textContent = voiceEnabled ? "Voice + Avatar Live" : "Avatar Live";
    return;
  }
  backendText.textContent = voiceEnabled ? "Voice Enabled" : "Voice Disabled";
}

function handleAvatarEnvelope(envelope) {
  if (!envelope || typeof envelope !== "object") {
    return;
  }

  const directState = normalizeAvatarState(envelope.state);
  if (directState) {
    paintAvatarState(directState);
  }

  const eventName = String(envelope.event || "").toLowerCase().trim();
  if (eventName && AVATAR_STATE_FROM_EVENT[eventName]) {
    paintAvatarState(AVATAR_STATE_FROM_EVENT[eventName]);
  }
}

function parseSSEData(raw) {
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function connectAvatarStream() {
  if (avatarEventSource) {
    avatarEventSource.close();
    avatarEventSource = null;
  }
  if (avatarReconnectTimer) {
    window.clearTimeout(avatarReconnectTimer);
    avatarReconnectTimer = null;
  }

  const source = new EventSource("/avatar/events");
  avatarEventSource = source;

  source.onopen = () => {
    avatarStreamOnline = true;
    applyBackendStatusLabel(backendVoiceEnabled);
  };

  source.onerror = () => {
    avatarStreamOnline = false;
    applyBackendStatusLabel(backendVoiceEnabled);
    source.close();
    if (avatarReconnectTimer) {
      window.clearTimeout(avatarReconnectTimer);
    }
    avatarReconnectTimer = window.setTimeout(() => {
      connectAvatarStream();
    }, 2200);
  };

  source.addEventListener("snapshot", (event) => {
    const snapshot = parseSSEData(event.data);
    if (!snapshot || typeof snapshot !== "object") {
      return;
    }
    if (snapshot.state) {
      paintAvatarState(snapshot.state);
    }
  });

  source.addEventListener("ping", () => {
    // Keepalive frame; no state transition required.
  });

  Object.keys(AVATAR_STATE_FROM_EVENT).forEach((eventName) => {
    source.addEventListener(eventName, (event) => {
      const envelope = parseSSEData(event.data);
      if (envelope) {
        handleAvatarEnvelope(envelope);
        return;
      }
      paintAvatarState(AVATAR_STATE_FROM_EVENT[eventName]);
    });
  });

  source.onmessage = (event) => {
    const payload = parseSSEData(event.data);
    if (payload) {
      handleAvatarEnvelope(payload);
    }
  };
}

function readBackendVoiceSettings() {
  return {
    voice_mode: selectedVoiceMode,
    voice_style: selectedVoiceStyle,
    accent_profile: selectedAccentProfile,
    voice_rate: Number.parseInt(voiceRateSelect?.value || "176", 10),
    voice_pitch: Number.parseInt(voicePitchSelect?.value || "50", 10),
    voice_name: (voiceModelSelect?.value || "indian_pratham").trim() || "indian_pratham",
  };
}

function setVoiceControlNote(text, isError = false) {
  if (!voiceControlsNote) return;
  voiceControlsNote.textContent = text;
  voiceControlsNote.style.color = isError ? "#ff7b98" : "var(--muted)";
}

function hydrateVoiceControls(voice) {
  if (!voice) return;
  if (voiceModeSelect && voice.voice_mode) {
    voiceModeSelect.value = voice.voice_mode;
    selectedVoiceMode = voiceModeSelect.value;
  }
  if (accentProfileSelect && voice.accent_profile) {
    accentProfileSelect.value = voice.accent_profile;
    selectedAccentProfile = accentProfileSelect.value;
  }
  if (voiceStyleSelect && voice.style) {
    voiceStyleSelect.value = voice.style;
    selectedVoiceStyle = voiceStyleSelect.value;
  }
  if (voiceRateSelect && Number.isFinite(Number(voice.rate))) {
    voiceRateSelect.value = String(Number(voice.rate));
  }
  if (voicePitchSelect && Number.isFinite(Number(voice.pitch))) {
    voicePitchSelect.value = String(Number(voice.pitch));
  }
  if (voiceModelSelect && typeof voice.voice === "string") {
    const value = String(voice.voice || "").trim();
    if (value && Array.from(voiceModelSelect.options).some((opt) => opt.value === value)) {
      voiceModelSelect.value = value;
    }
  }
}

async function syncVoiceControlsToBackend() {
  const prefs = readBackendVoiceSettings();
  try {
    const result = await postJson("/voice/settings", prefs);
    hydrateVoiceControls(result?.voice || prefs);
    setVoiceControlNote("Voice settings applied for backend talkback.");
  } catch (err) {
    setVoiceControlNote(`Unable to apply voice settings: ${err.message}`, true);
  }
}

function isNearBottom() {
  const threshold = 120;
  return chatLog.scrollHeight - chatLog.scrollTop - chatLog.clientHeight <= threshold;
}

function scrollToBottom() {
  chatLog.scrollTop = chatLog.scrollHeight;
}

function addMessage(role, text, meta = "") {
  const shouldStick = isNearBottom();
  const node = tpl.content.firstElementChild.cloneNode(true);
  node.classList.add(role === "You" ? "user" : "nova");
  node.querySelector(".role").textContent = role;
  renderMessageContent(node.querySelector(".text"), text, role);

  const actions = document.createElement("div");
  actions.className = "msg-actions";

  const copyBtn = document.createElement("button");
  copyBtn.type = "button";
  copyBtn.className = "msg-copy-btn";
  copyBtn.textContent = "Copy";
  copyBtn.addEventListener("click", async () => {
    const copied = await copyTextToClipboard(String(text || ""));
    indicateCopyStatus(copyBtn, copied);
  });

  actions.appendChild(copyBtn);
  node.querySelector(".bubble").appendChild(actions);
  node.querySelector(".meta").textContent = meta;
  chatLog.appendChild(node);
  if (shouldStick || role === "You") {
    scrollToBottom();
  }
}

function renderMessageContent(container, text, role = "") {
  container.textContent = "";
  const value = String(text || "");

  if (!value.includes("```")) {
    container.textContent = value;
    return;
  }

  const pattern = /```([a-zA-Z0-9_+-]*)\n?([\s\S]*?)```/g;
  let cursor = 0;
  let match = pattern.exec(value);

  while (match) {
    const [full, lang, code] = match;
    const start = match.index;

    if (start > cursor) {
      const textPart = value.slice(cursor, start);
      container.appendChild(document.createTextNode(textPart));
    }

    const block = document.createElement("div");
    block.className = "code-block";

    const head = document.createElement("div");
    head.className = "code-head";

    const langTag = document.createElement("span");
    langTag.className = "code-lang";
    langTag.textContent = lang || "code";
    head.appendChild(langTag);

    const copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.className = "code-copy-btn";
    copyBtn.textContent = "Copy";
    copyBtn.addEventListener("click", async () => {
      const copied = await copyTextToClipboard(code.replace(/\n$/, ""));
      indicateCopyStatus(copyBtn, copied);
    });
    head.appendChild(copyBtn);
    block.appendChild(head);

    const pre = document.createElement("pre");
    pre.textContent = code.replace(/\n$/, "");
    block.appendChild(pre);
    container.appendChild(block);

    cursor = start + full.length;
    match = pattern.exec(value);
  }

  if (cursor < value.length) {
    container.appendChild(document.createTextNode(value.slice(cursor)));
  }
}

async function copyTextToClipboard(text) {
  const value = String(text || "");
  if (!value) {
    return false;
  }

  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch {
    // Fall back to execCommand copy path.
  }

  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();

  let copied = false;
  try {
    copied = document.execCommand("copy");
  } catch {
    copied = false;
  }

  document.body.removeChild(textarea);
  return copied;
}

function indicateCopyStatus(button, success) {
  if (!button) return;
  const original = button.dataset.originalLabel || button.textContent || "Copy";
  button.dataset.originalLabel = original;

  button.classList.remove("failed", "copied");
  if (success) {
    button.classList.add("copied");
    button.textContent = "Copied";
  } else {
    button.classList.add("failed");
    button.textContent = "Failed";
  }

  window.setTimeout(() => {
    button.classList.remove("failed", "copied");
    button.textContent = original;
  }, COPY_FEEDBACK_MS);
}

function setComposerMode(mode) {
  composerMode = mode === "code" ? "code" : "chat";
  const isCode = composerMode === "code";

  modeChatBtn.classList.toggle("is-active", !isCode);
  modeCodeBtn.classList.toggle("is-active", isCode);
  chatPane.classList.toggle("hidden", isCode);
  codePane.classList.toggle("hidden", !isCode);
  composerHint.textContent = isCode ? "Enter to send, Shift+Enter for newline" : "Enter to send";

  if (isCode) {
    codeInput.focus();
  } else {
    chatInput.focus();
  }
}

function buildCodePrompt(codeText) {
  const actionPrompt = CODE_ACTION_PROMPTS[selectedCodeAction] || CODE_ACTION_PROMPTS.fix;
  return `${actionPrompt}\n\nCode:\n\n\`\`\`\n${codeText}\n\`\`\``;
}

function pushCommandHistory(mode, value) {
  const key = mode === "code" ? "code" : "chat";
  const entry = String(value || "").trim();
  if (!entry) return;

  const history = commandHistory[key];
  if (history.length > 0 && history[history.length - 1] === entry) {
    historyCursor[key] = -1;
    return;
  }

  history.push(entry);
  if (history.length > HISTORY_LIMIT) {
    history.shift();
  }
  historyCursor[key] = -1;
}

function setComposerValue(mode, value) {
  const input = mode === "code" ? codeInput : chatInput;
  input.value = value;
  input.focus();
  const cursorPos = input.value.length;
  input.setSelectionRange(cursorPos, cursorPos);
}

function navigateCommandHistory(mode, direction) {
  const key = mode === "code" ? "code" : "chat";
  const history = commandHistory[key];
  if (!history.length) return;

  let cursor = historyCursor[key];

  if (direction === "up") {
    cursor = cursor === -1 ? history.length - 1 : Math.max(0, cursor - 1);
    historyCursor[key] = cursor;
    setComposerValue(key, history[cursor]);
    return;
  }

  if (cursor === -1) return;

  cursor += 1;
  if (cursor >= history.length) {
    historyCursor[key] = -1;
    setComposerValue(key, "");
    return;
  }

  historyCursor[key] = cursor;
  setComposerValue(key, history[cursor]);
}

function isCaretAtStart(el) {
  return el.selectionStart === 0 && el.selectionEnd === 0;
}

function isCaretAtEnd(el) {
  return el.selectionStart === el.value.length && el.selectionEnd === el.value.length;
}

function addTypingLoader() {
  const shouldStick = isNearBottom();
  const node = tpl.content.firstElementChild.cloneNode(true);
  node.classList.add("nova", "loading");
  node.querySelector(".role").textContent = "NOVA";
  node.querySelector(".text").innerHTML =
    '<span class="typing">Thinking<span class="dot"></span><span class="dot"></span><span class="dot"></span></span>';
  node.querySelector(".meta").textContent = "processing";
  chatLog.appendChild(node);
  if (shouldStick) {
    scrollToBottom();
  }
  return node;
}

function setUIBusy(isBusy) {
  const chips = document.querySelectorAll(".chip");
  sendBtn.disabled = isBusy;
  chatInput.disabled = isBusy;
  codeInput.disabled = isBusy;
  pushToTalkBtn.disabled = isBusy;
  chips.forEach((chip) => {
    chip.disabled = isBusy;
  });
}

function updateModeText() {
  if (!micToggle.checked) {
    modeText.textContent = "Interactive";
    return;
  }

  if (wakeConversationActive) {
    modeText.textContent = "Wake Conversation";
    return;
  }

  if (handsFreeToggle.checked) {
    modeText.textContent = "Wake + Voice";
    return;
  }

  modeText.textContent = "Voice + Chat";
}

function setWakeStatus(message) {
  if (wakeStatus) {
    wakeStatus.textContent = message;
  }
}

function pickWakeGreeting() {
  return WAKE_GREETING_VARIANTS[Math.floor(Math.random() * WAKE_GREETING_VARIANTS.length)];
}

function normalizeSpeechText(text) {
  return String(text || "")
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function normalizeVoiceQuery(text) {
  const raw = String(text || "").trim();
  if (!raw) {
    return "";
  }

  // Collapse spelled acronyms from speech input: "c v e" -> "cve", "u i" -> "ui".
  return raw.replace(/\b(?:[A-Za-z]\s+){1,5}[A-Za-z]\b/g, (match) =>
    match.replace(/\s+/g, "")
  );
}

function extractWakeCommand(transcript) {
  const normalized = normalizeSpeechText(transcript);
  for (const wakeWord of WAKE_WORDS) {
    const idx = normalized.indexOf(wakeWord);
    if (idx !== -1) {
      const command = normalized.slice(idx + wakeWord.length).trim();
      return command;
    }
  }
  return "";
}

function containsWakeWord(transcript) {
  const normalized = normalizeSpeechText(transcript);
  return WAKE_WORDS.some((wakeWord) => normalized.includes(wakeWord));
}

function isStopListeningPhrase(transcript) {
  const normalized = normalizeSpeechText(transcript);
  if (!normalized) return false;
  return STOP_LISTENING_PHRASES.some((phrase) => normalized === phrase || normalized.includes(phrase));
}

function setSpeakingState(speaking) {
  stopSpeakBtn.disabled = !speaking;
  if (speaking) {
    stopSpeakBtn.classList.add("rail-btn--speaking");
  } else {
    stopSpeakBtn.classList.remove("rail-btn--speaking");
  }
}

function stopSpeech() {
  speechToken += 1;
  if ("speechSynthesis" in window) {
    window.speechSynthesis.cancel();
  }
  setSpeakingState(false);
}

function speakInBrowser(text) {
  if (!uiSpeakEnabled || !("speechSynthesis" in window) || !text) {
    return;
  }
  const cleaned = prepareSpeechText(text);
  if (!cleaned) {
    return;
  }

  const chunks = chunkSpeechText(cleaned, VOICE_PROFILE.maxChunkLength);
  const styleProfile = VOICE_STYLE_PROFILES[selectedVoiceStyle] || VOICE_STYLE_PROFILES.natural;
  const styleVoice = voiceStyleMap[selectedVoiceStyle] || preferredVoice;
  const token = speechToken + 1;
  speechToken = token;

  window.speechSynthesis.cancel();
  setSpeakingState(true);

  const speakChunk = (index) => {
    if (token !== speechToken) {
      return;
    }

    if (index >= chunks.length) {
      setSpeakingState(false);
      return;
    }

    const utter = new SpeechSynthesisUtterance(chunks[index]);
    utter.rate = Math.max(0.84, Math.min(1.05, styleProfile.baseRate + (index % 2 === 0 ? 0.01 : -0.01)));
    utter.pitch = styleProfile.basePitch;
    utter.volume = styleProfile.volume;
    utter.lang = VOICE_PROFILE.defaultLang;

    if (styleVoice) {
      utter.voice = styleVoice;
      if (styleVoice.lang) {
        utter.lang = styleVoice.lang;
      }
    }

    utter.onend = () => speakChunk(index + 1);
    utter.onerror = () => {
      setSpeakingState(false);
    };

    window.speechSynthesis.speak(utter);
  };

  speakChunk(0);
}

function prepareSpeechText(text) {
  return String(text || "")
    .replace(/```[\s\S]*?```/g, "")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/^\s*[-*]\s+/gm, "")
    .replace(/\bAPIs?\b/g, "A P I")
    .replace(/\bSQL\b/g, "S Q L")
    .replace(/\bUI\b/g, "U I")
    .replace(/\|/g, ", ")
    .replace(/\s*;\s*/g, ", ")
    .replace(/\s*:\s*/g, ", ")
    .replace(/\s+/g, " ")
    .replace(/\.(?=\S)/g, ". ")
    .replace(/,(?=\S)/g, ", ")
    .replace(/\s+/g, " ")
    .trim();
}

function chunkSpeechText(text, maxLength) {
  const source = (text || "").trim();
  if (!source) return [];

  const sentences = source.match(/[^.!?]+[.!?]?/g) || [source];
  const chunks = [];
  let current = "";

  for (const sentenceRaw of sentences) {
    const sentence = sentenceRaw.trim();
    if (!sentence) continue;

    if (!current) {
      current = sentence;
      continue;
    }

    if (`${current} ${sentence}`.length <= maxLength) {
      current = `${current} ${sentence}`;
      continue;
    }

    chunks.push(current);
    current = sentence;
  }

  if (current) chunks.push(current);
  return chunks;
}

function pickFemaleVoice(voices) {
  if (!voices || !voices.length) return null;

  // Indian voices to try first — ordered by quality preference.
  const indianPreferred = [
    "lekha",
    "veena",
    "neerja",
    "heera",
    "rishi",
    "google हिन्दी",
    "google hindi",
    "priya",
    "aditi",
  ];

  // Fallback Western names if no Indian voice is found.
  const westernFallback = [
    "samantha",
    "ava",
    "allison",
    "karen",
    "moira",
    "serena",
    "flo",
    "zira",
    "aria",
    "jenny",
  ];

  const avoidHints = [
    "compact",
    "novelty",
    "whisper",
    "zarvox",
    "boing",
    "bells",
    "bubbles",
    "bad news",
    "good news",
    "jester",
    "grandma",
    "grandpa",
    "organ",
  ];

  const indianVoices = voices.filter((v) => {
    const lang = (v.lang || "").toLowerCase();
    const name = (v.name || "").toLowerCase();
    return lang.startsWith("en-in") || lang.startsWith("hi-in") || name.includes("india") || name.includes("hindi");
  });

  // Try Indian voices by name first.
  for (const pref of indianPreferred) {
    const match = voices.find((v) => (v.name || "").toLowerCase().includes(pref));
    if (match) return match;
  }

  // If there are any en-IN voices at all, score and pick the best one.
  if (indianVoices.length > 0) {
    const scored = indianVoices
      .filter((v) => !avoidHints.some((h) => (v.name || "").toLowerCase().includes(h)))
      .sort((a, b) => scoreVoiceQuality(b) - scoreVoiceQuality(a));
    if (scored.length > 0) return scored[0];
    return indianVoices[0];
  }

  // No Indian voices — fall back to best English voice.
  const englishVoices = voices.filter((v) => (v.lang || "").toLowerCase().startsWith("en"));
  for (const pref of westernFallback) {
    const match = englishVoices.find((v) => (v.name || "").toLowerCase().includes(pref));
    if (match) return match;
  }

  const best = englishVoices
    .filter((v) => !avoidHints.some((h) => (v.name || "").toLowerCase().includes(h)))
    .sort((a, b) => scoreVoiceQuality(b) - scoreVoiceQuality(a));
  return best[0] || voices[0] || null;
}

function scoreVoiceQuality(voice) {
  const name = (voice.name || "").toLowerCase();
  let score = 0;
  if (name.includes("neural") || name.includes("premium") || name.includes("enhanced")) score += 20;
  else if (name.includes("natural") || name.includes("google")) score += 12;
  else if (name.includes("online")) score += 8;
  if (voice.localService === false) score += 10;
  if (name.includes("compact")) score -= 25;
  return score;
}

function initBrowserVoices() {
  if (!("speechSynthesis" in window)) return;

  const loadVoices = () => {
    browserVoices = window.speechSynthesis.getVoices() || [];
    preferredVoice = pickFemaleVoice(browserVoices);
    assignVoiceStyles(browserVoices);
  };

  loadVoices();
  window.speechSynthesis.onvoiceschanged = loadVoices;
}

function findVoiceByHints(voices, hints) {
  if (!voices?.length) return null;
  return voices.find((voice) => {
    const name = (voice.name || "").toLowerCase();
    return hints.some((hint) => name.includes(hint));
  }) || null;
}

function assignVoiceStyles(voices) {
  const fallback = pickFemaleVoice(voices);
  // For all styles, prefer Indian voices in order of character.
  // Natural: Lekha (warm Indian accent), Warm: Veena (softer), Clear: Neerja/Heera
  const warm = findVoiceByHints(voices, ["veena", "lekha", "neerja", "serena", "moira", "karen", "allison", "samantha"]) || fallback;
  const clear = findVoiceByHints(voices, ["neerja", "heera", "rishi", "lekha", "aria", "zira", "ava", "jenny", "flo"]) || fallback;

  voiceStyleMap.natural = fallback;
  voiceStyleMap.warm = warm;
  voiceStyleMap.clear = clear;
}

async function postJson(url, data) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`HTTP ${res.status} ${body}`);
  }
  return res.json();
}

async function queryVoiceStatus() {
  try {
    const res = await fetch("/voice/status");
    if (!res.ok) {
      throw new Error(`status ${res.status}`);
    }
    const body = await res.json();
    backendVoiceEnabled = Boolean(body.enabled);
    applyBackendStatusLabel(backendVoiceEnabled);
    if (!avatarStreamOnline) {
      paintAvatarState(body.session?.state || latestAvatarState || "idle");
    }
    hydrateVoiceControls(body?.controls?.current);
  } catch (err) {
    backendText.textContent = "Backend Error";
    paintAvatarState("error");
  }
}

function isNeuralTTSBackend(backendName) {
  const backend = String(backendName || "").toLowerCase().trim();
  return backend === "kokoro" || backend === "piper";
}

async function speakWithBackend(text) {
  const content = String(text || "").trim();
  if (!content) {
    return { usedBackend: false, backend: "none" };
  }

  try {
    const payload = await postJson("/voice/speak", {
      text: content,
      speak: true,
      ...readBackendVoiceSettings(),
    });
    const backend = payload?.backend || "none";
    const usedBackend = Boolean(payload?.spoken) && isNeuralTTSBackend(backend);
    return { usedBackend, backend };
  } catch {
    return { usedBackend: false, backend: "error" };
  }
}

async function sendChat(text, source = "chat") {
  addMessage("You", text, source === "voice" ? "via microphone" : "");
  const loader = addTypingLoader();
  setUIBusy(true);

  try {
    const payload = await postJson("/chat", { message: text });

    const metaParts = [];
    if (payload.intent) metaParts.push(`intent: ${payload.intent}`);
    if (payload.action) metaParts.push(`action: ${payload.action}`);
    if (payload.tasks_executed) metaParts.push(`tasks: ${payload.tasks_executed}`);

    loader.remove();
    addMessage("NOVA", payload.response || "", metaParts.join(" | "));

    if (payload.initiative?.message) {
      addMessage("NOVA", payload.initiative.message, "initiative");
    }

    if (speakToggle.checked) {
      const spoken = await speakWithBackend(payload.response || "");
      if (!spoken.usedBackend) {
        addMessage("NOVA", "Neural talkback unavailable. Configure Kokoro or Piper to enable natural voice.", `tts: ${spoken.backend}`);
      }
    }

    return payload;
  } catch (error) {
    loader.remove();
    throw error;
  } finally {
    setUIBusy(false);
  }
}

async function processVoiceTranscript(transcript, source = "voice") {
  const normalizedTranscript = normalizeVoiceQuery(transcript);
  if (!normalizedTranscript) {
    return;
  }

  if (voiceTurnInFlight) {
    return;
  }

  voiceTurnInFlight = true;

  addMessage("You", normalizedTranscript, source === "voice" ? "via microphone" : "");
  const loader = addTypingLoader();
  setUIBusy(true);

  try {
    const payload = await postJson("/voice/text", {
      text: `Nova, ${normalizedTranscript}`,
      speak: speakToggle.checked,
      ...readBackendVoiceSettings(),
    });

    const metaParts = [];
    if (payload.intent) metaParts.push(`intent: ${payload.intent}`);
    if (payload.action) metaParts.push(`action: ${payload.action}`);
    const synthBackend = payload?.voice?.metadata?.synthesis?.backend;
    if (synthBackend) metaParts.push(`tts: ${synthBackend}`);

    loader.remove();
    addMessage("NOVA", payload.response || "", metaParts.join(" | "));

    if (speakToggle.checked && !isNeuralTTSBackend(synthBackend)) {
      addMessage("NOVA", "Neural talkback unavailable for this voice turn. Configure Kokoro or Piper.", `tts: ${synthBackend || "none"}`);
    }

    queryVoiceStatus();
  } catch (err) {
    loader.remove();
    addMessage("NOVA", `Voice pipeline failed: ${err.message}`, "error");
  } finally {
    setUIBusy(false);
    voiceTurnInFlight = false;
  }
}

function endWakeConversation(noticeText = "Understood. I will stop listening now.") {
  wakeConversationActive = false;
  updateModeText();
  addMessage("NOVA", noticeText, "wake-word");
  if (listening && recognizer) {
    recognizer.stop();
  }
  if (handsFreeToggle.checked && micToggle.checked) {
    setWakeStatus("Wake listener active. Say wake word to start.");
    startWakeListener();
  } else {
    setWakeStatus("Wake listening is off.");
  }
}

function beginWakeConversation(initialCommand = "") {
  wakeConversationActive = true;
  updateModeText();
  stopWakeListener();
  addMessage("NOVA", pickWakeGreeting(), "wake-word");
  setWakeStatus("Conversation mode is active. Say stop, exit, or that's it for now to end.");

  if (initialCommand) {
    processVoiceTranscript(initialCommand, "voice");
  }

  if (!listening && recognizer) {
    try {
      recognizer.start();
    } catch {
      // Ignore duplicate start errors.
    }
  }
}

function stopWakeListener() {
  if (wakeRecognizer && wakeListening) {
    wakeRecognizer.stop();
  }
  wakeListening = false;
  if (wakeConversationActive) {
    setWakeStatus("Conversation mode is active.");
  } else if (handsFreeToggle.checked && micToggle.checked) {
    setWakeStatus("Wake listener paused.");
  } else {
    setWakeStatus("Wake listening is off.");
  }
}

function startWakeListener() {
  if (!wakeRecognizer || !handsFreeToggle.checked || !micToggle.checked || listening || wakeListening || wakeConversationActive) {
    return;
  }

  setWakeStatus("Starting wake listener...");
  try {
    wakeRecognizer.start();
  } catch {
    setWakeStatus("Wake listener could not start. Check mic permission.");
  }
}

function initWebSpeech() {
  const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Ctor) {
    modeText.textContent = "Mic unsupported";
    micToggle.disabled = true;
    handsFreeToggle.disabled = true;
    pushToTalkBtn.disabled = true;
    return;
  }

  recognizer = new Ctor();
  recognizer.continuous = true;
  recognizer.interimResults = false;
  recognizer.lang = "en-US";

  recognizer.onstart = () => {
    listening = true;
    if (!wakeConversationActive) {
      stopWakeListener();
    }
    paintAvatarState("listening");
    pushToTalkBtn.textContent = "Listening...";
  };

  recognizer.onend = () => {
    listening = false;
    paintAvatarState("idle");
    pushToTalkBtn.textContent = "Push To Talk";

    if (wakeConversationActive && micToggle.checked) {
      window.setTimeout(() => {
        if (wakeConversationActive && recognizer && !listening) {
          try {
            recognizer.start();
          } catch {
            // Ignore duplicate start errors.
          }
        }
      }, 250);
      return;
    }

    startWakeListener();
  };

  recognizer.onerror = (event) => {
    paintAvatarState("error");
    // Prevent chat spam for frequent no-speech events in continuous mode.
    if (event.error === "no-speech") {
      return;
    }
    addMessage("NOVA", `Microphone error: ${event.error}`, "voice");
  };

  recognizer.onresult = async (event) => {
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      if (!event.results[i].isFinal) {
        continue;
      }

      const transcript = event.results[i][0]?.transcript?.trim() || "";
      if (!transcript) {
        continue;
      }

      if (wakeConversationActive && isStopListeningPhrase(transcript)) {
        endWakeConversation("Alright, stopping now. Say a wake word when you need me again.");
        return;
      }

      await processVoiceTranscript(transcript, "voice");
      return;
    }
  };

  wakeRecognizer = new Ctor();
  wakeRecognizer.continuous = true;
  wakeRecognizer.interimResults = true;
  wakeRecognizer.lang = "en-US";

  wakeRecognizer.onstart = () => {
    wakeListening = true;
    setWakeStatus("Wake listener active. Say: " + WAKE_WORDS.join(", "));
  };

  wakeRecognizer.onend = () => {
    wakeListening = false;
    if (handsFreeToggle.checked && micToggle.checked && !listening) {
      setWakeStatus("Wake listener reconnecting...");
      window.setTimeout(() => startWakeListener(), 400);
    } else {
      setWakeStatus("Wake listening is off.");
    }
  };

  wakeRecognizer.onerror = (event) => {
    if (handsFreeToggle.checked && micToggle.checked) {
      setWakeStatus(`Wake listener error: ${event.error}`);
    }
  };

  wakeRecognizer.onresult = (event) => {
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      if (!event.results[i].isFinal) {
        continue;
      }

      const transcript = event.results[i][0]?.transcript?.trim() || "";
      if (!transcript || !containsWakeWord(transcript)) {
        continue;
      }

      const now = Date.now();
      if (now < wakeDetectionCooldownUntil) {
        continue;
      }
      wakeDetectionCooldownUntil = now + 1800;

      const command = extractWakeCommand(transcript);
      beginWakeConversation(command);
      return;
    }
  };
}

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  let text = "";
  let historyValue = "";

  if (composerMode === "code") {
    const codeText = codeInput.value.trim();
    if (!codeText) return;
    historyValue = codeText;
    text = buildCodePrompt(codeText);
  } else {
    text = chatInput.value.trim();
    if (!text) return;
    historyValue = text;
  }

  if (!text) return;

  pushCommandHistory(composerMode, historyValue);

  if (composerMode === "code") {
    codeInput.value = "";
  } else {
    chatInput.value = "";
  }
  try {
    await sendChat(text, composerMode === "code" ? "code" : "chat");
    queryVoiceStatus();
  } catch (err) {
    addMessage("NOVA", `Request failed: ${err.message}`, "error");
  }
});

modeChatBtn.addEventListener("click", () => {
  setComposerMode("chat");
});

modeCodeBtn.addEventListener("click", () => {
  setComposerMode("code");
});

document.querySelectorAll(".code-preset").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".code-preset").forEach((b) => b.classList.remove("is-active"));
    btn.classList.add("is-active");
    selectedCodeAction = btn.getAttribute("data-code-action") || "fix";
    codeInput.focus();
  });
});

codeInput.addEventListener("keydown", (event) => {
  if (event.isComposing) return;
  if (event.key === "ArrowUp" && isCaretAtStart(codeInput)) {
    event.preventDefault();
    navigateCommandHistory("code", "up");
    return;
  }
  if (event.key === "ArrowDown" && isCaretAtEnd(codeInput)) {
    event.preventDefault();
    navigateCommandHistory("code", "down");
    return;
  }
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    chatForm.requestSubmit();
  }
});

chatInput.addEventListener("keydown", (event) => {
  if (event.isComposing) return;
  if (event.key === "ArrowUp") {
    event.preventDefault();
    navigateCommandHistory("chat", "up");
    return;
  }
  if (event.key === "ArrowDown") {
    event.preventDefault();
    navigateCommandHistory("chat", "down");
    return;
  }
  if (event.key === "Enter") {
    event.preventDefault();
    chatForm.requestSubmit();
  }
});

quickActionButtons.forEach((btn) => {
  btn.addEventListener("click", async () => {
    const openUrl = btn.getAttribute("data-open-url");
    if (openUrl) {
      const target = btn.getAttribute("data-open-target") || "_self";
      window.open(openUrl, target);
      return;
    }

    const prompt = btn.getAttribute("data-prompt");
    if (!prompt) return;

    try {
      await sendChat(prompt, "quick-action");
    } catch (err) {
      addMessage("NOVA", `Request failed: ${err.message}`, "error");
    }
  });
});

speakToggle.addEventListener("change", () => {
  uiSpeakEnabled = speakToggle.checked;
  if (!uiSpeakEnabled) {
    stopSpeech();
  }
});

if (voiceStyleSelect) {
  voiceStyleSelect.addEventListener("change", () => {
    const next = (voiceStyleSelect.value || "natural").toLowerCase();
    if (!VOICE_STYLE_PROFILES[next]) {
      selectedVoiceStyle = "clear";
      voiceStyleSelect.value = "clear";
      return;
    }
    selectedVoiceStyle = next;
    syncVoiceControlsToBackend();
  });
}

if (voiceModeSelect) {
  voiceModeSelect.addEventListener("change", () => {
    selectedVoiceMode = (voiceModeSelect.value || "human").toLowerCase();
    if (selectedVoiceMode === "cat") {
      if (voiceStyleSelect) {
        voiceStyleSelect.value = "excited";
      }
      if (voiceRateSelect) {
        voiceRateSelect.value = "140";
      }
      if (voicePitchSelect) {
        voicePitchSelect.value = "60";
      }
      selectedVoiceStyle = "excited";
    } else {
      if (voiceStyleSelect) {
        voiceStyleSelect.value = "clear";
      }
      if (voiceRateSelect) {
        voiceRateSelect.value = "176";
      }
      if (voicePitchSelect) {
        voicePitchSelect.value = "50";
      }
      selectedVoiceStyle = "clear";
    }
    syncVoiceControlsToBackend();
  });
}

if (accentProfileSelect) {
  accentProfileSelect.addEventListener("change", () => {
    selectedAccentProfile = (accentProfileSelect.value || "indian_clear").toLowerCase();
    syncVoiceControlsToBackend();
  });
}

if (voiceRateSelect) {
  voiceRateSelect.addEventListener("change", () => {
    syncVoiceControlsToBackend();
  });
}

if (voicePitchSelect) {
  voicePitchSelect.addEventListener("change", () => {
    syncVoiceControlsToBackend();
  });
}

if (voiceModelSelect) {
  voiceModelSelect.addEventListener("change", () => {
    syncVoiceControlsToBackend();
  });
}

stopSpeakBtn.addEventListener("click", () => {
  stopSpeech();
});

micToggle.addEventListener("change", () => {
  if (!micToggle.checked) {
    if (listening && recognizer) {
      recognizer.stop();
    }
    stopWakeListener();
  }

  updateModeText();
  startWakeListener();
});

handsFreeToggle.addEventListener("change", () => {
  updateModeText();
  if (!handsFreeToggle.checked) {
    if (wakeConversationActive) {
      wakeConversationActive = false;
      if (listening && recognizer) {
        recognizer.stop();
      }
    }
    stopWakeListener();
  } else {
    startWakeListener();
  }
});

pushToTalkBtn.addEventListener("click", () => {
  // Always stop any ongoing speech before listening.
  stopSpeech();

  if (!recognizer) return;
  if (!micToggle.checked) {
    addMessage("NOVA", "Enable microphone toggle first.", "voice");
    return;
  }

  if (listening) {
    recognizer.stop();
    return;
  }
  wakeConversationActive = false;
  updateModeText();
  stopWakeListener();
  recognizer.start();
});

(function bootstrap() {
  if (voiceModeSelect) {
    selectedVoiceMode = (voiceModeSelect.value || "human").toLowerCase();
  }
  if (voiceStyleSelect) {
    selectedVoiceStyle = (voiceStyleSelect.value || "clear").toLowerCase();
    if (!VOICE_STYLE_PROFILES[selectedVoiceStyle]) {
      selectedVoiceStyle = "clear";
      voiceStyleSelect.value = "clear";
    }
  }
  if (accentProfileSelect) {
    selectedAccentProfile = (accentProfileSelect.value || "indian_clear").toLowerCase();
  }

  initBrowserVoices();
  initWebSpeech();
  paintAvatarState("idle");
  connectAvatarStream();
  queryVoiceStatus();
  syncVoiceControlsToBackend();
  updateModeText();
  setWakeStatus("Wake listening is off.");

  addMessage(
    "NOVA",
    "Companion console is online. You can chat naturally, create goals, or use push-to-talk in one stream.",
    "system"
  );

  const firstPreset = document.querySelector('.code-preset[data-code-action="fix"]');
  if (firstPreset) {
    firstPreset.classList.add("is-active");
  }
  setComposerMode("chat");

  requestAnimationFrame(() => {
    scrollToBottom();
  });
})();
