const cat = document.getElementById("cat");
const head = document.getElementById("head");
const pupilL = document.getElementById("pupilL");
const pupilR = document.getElementById("pupilR");
const stateChip = document.getElementById("stateChip");
const eventChip = document.getElementById("eventChip");
const connectionText = document.getElementById("connectionText");
const stage = document.getElementById("stage");
const petBtn = document.getElementById("petBtn");
const resetViewBtn = document.getElementById("resetViewBtn");
const talkForm = document.getElementById("talkForm");
const talkInput = document.getElementById("talkInput");
const speakBack = document.getElementById("speakBack");
const loadMediaBtn = document.getElementById("loadMediaBtn");
const useBuiltInBtn = document.getElementById("useBuiltInBtn");
const mediaInput = document.getElementById("mediaInput");
const mediaAvatar = document.getElementById("mediaAvatar");
const catVideo = document.getElementById("catVideo");
const catImage = document.getElementById("catImage");

let reconnectTimer = null;
let pointerResetTimer = null;
let currentObjectUrl = "";

const EVENT_TO_STATE = {
  listening_started: "listening",
  listening_completed: "idle",
  thinking_started: "thinking",
  thinking_completed: "idle",
  speaking_started: "speaking",
  speaking_completed: "idle",
  idle: "idle",
};

function setState(nextState, eventName = "snapshot") {
  const state = String(nextState || "idle").toLowerCase();
  cat.dataset.state = state;
  mediaAvatar.dataset.state = state;
  stateChip.textContent = state;
  eventChip.textContent = String(eventName || "snapshot");
}

function setConnection(connected) {
  connectionText.textContent = connected
    ? "Connected to /avatar/events"
    : "Reconnecting to avatar stream...";
}

function parsePayload(raw) {
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function connectSSE() {
  const source = new EventSource("/avatar/events");

  source.onopen = () => {
    setConnection(true);
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  };

  source.onerror = () => {
    setConnection(false);
    source.close();
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
    }
    reconnectTimer = setTimeout(connectSSE, 2200);
  };

  source.addEventListener("snapshot", (event) => {
    const payload = parsePayload(event.data);
    if (payload?.state) {
      setState(payload.state, "snapshot");
    }
  });

  Object.keys(EVENT_TO_STATE).forEach((name) => {
    source.addEventListener(name, (event) => {
      const payload = parsePayload(event.data);
      const state = payload?.state || EVENT_TO_STATE[name];
      setState(state, name);
    });
  });

  source.onmessage = (event) => {
    const payload = parsePayload(event.data);
    if (!payload) return;
    const state = payload.state || EVENT_TO_STATE[payload.event] || "idle";
    setState(state, payload.event || "message");
  };
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function moveEyes(clientX, clientY) {
  const rect = head.getBoundingClientRect();
  const rx = clamp((clientX - (rect.left + rect.width / 2)) / rect.width, -0.5, 0.5);
  const ry = clamp((clientY - (rect.top + rect.height / 2)) / rect.height, -0.5, 0.5);

  const dx = rx * 5;
  const dy = ry * 4;
  pupilL.style.transform = `translate(${dx}px, ${dy}px)`;
  pupilR.style.transform = `translate(${dx}px, ${dy}px)`;
}

function resetLook() {
  pupilL.style.transform = "translate(0, 0)";
  pupilR.style.transform = "translate(0, 0)";
}

function setBuiltInMode() {
  mediaAvatar.classList.add("hidden");
  cat.classList.remove("hidden");
  connectionText.textContent = "Using built-in cat avatar";
}

function setMediaMode() {
  mediaAvatar.classList.remove("hidden");
  cat.classList.add("hidden");
}

function clearExistingMedia() {
  if (currentObjectUrl) {
    URL.revokeObjectURL(currentObjectUrl);
    currentObjectUrl = "";
  }
  catVideo.pause();
  catVideo.removeAttribute("src");
  catImage.removeAttribute("src");
  mediaAvatar.classList.remove("has-video", "has-image");
}

function loadMediaFile(file) {
  if (!file) return;
  clearExistingMedia();

  const url = URL.createObjectURL(file);
  currentObjectUrl = url;

  if (file.type.startsWith("video/")) {
    mediaAvatar.classList.add("has-video");
    catVideo.src = url;
    catVideo.play().catch(() => {});
    connectionText.textContent = `Loaded video: ${file.name}`;
  } else if (file.type.startsWith("image/")) {
    mediaAvatar.classList.add("has-image");
    catImage.src = url;
    connectionText.textContent = `Loaded image: ${file.name}`;
  } else {
    connectionText.textContent = "Unsupported media type. Use image or video.";
    return;
  }

  setMediaMode();
}

async function postJson(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return res.json();
}

document.querySelectorAll("button[data-event]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const event = btn.getAttribute("data-event");
    if (!event) return;

    try {
      await postJson("/avatar/emit", {
        event,
        payload: { source: "web_companion_manual" },
      });
    } catch (err) {
      connectionText.textContent = `Emit failed: ${err.message}`;
    }
  });
});

petBtn.addEventListener("click", async () => {
  cat.style.setProperty("--y", "-8px");
  setTimeout(() => cat.style.setProperty("--y", "0px"), 180);

  try {
    await postJson("/avatar/emit", {
      event: "speaking_started",
      payload: { source: "pet_button" },
    });
    setTimeout(() => {
      postJson("/avatar/emit", {
        event: "idle",
        payload: { source: "pet_button_done" },
      }).catch(() => {});
    }, 900);
  } catch {
    // Visual interaction should still work even if backend emit fails.
  }
});

resetViewBtn.addEventListener("click", resetLook);

loadMediaBtn.addEventListener("click", () => {
  mediaInput.click();
});

useBuiltInBtn.addEventListener("click", () => {
  setBuiltInMode();
});

mediaInput.addEventListener("change", () => {
  const file = mediaInput.files?.[0];
  loadMediaFile(file);
  mediaInput.value = "";
});

stage.addEventListener("pointermove", (event) => {
  moveEyes(event.clientX, event.clientY);
  if (pointerResetTimer) {
    clearTimeout(pointerResetTimer);
  }
  pointerResetTimer = setTimeout(resetLook, 1200);
});

talkForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = talkInput.value.trim();
  if (!text) return;

  try {
    await postJson("/voice/text", {
      text,
      speak: Boolean(speakBack.checked),
    });
    talkInput.value = "";
  } catch (err) {
    connectionText.textContent = `Voice request failed: ${err.message}`;
  }
});

setState("idle", "snapshot");
setBuiltInMode();
connectSSE();
