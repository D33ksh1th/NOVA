"""
WebSocket voice streaming — real-time audio capture → STT → wake word detection.

This replaces the browser's Web Speech API (which doesn't work in Tauri/WKWebView)
with a server-side pipeline:

  1. Frontend captures mic audio via getUserMedia (works in WKWebView)
  2. Sends PCM16 chunks over WebSocket
  3. Backend runs VAD → buffers speech → STT (faster-whisper) → wake word check
  4. Sends events back: wake_detected, transcript, silence, listening, error
"""

from __future__ import annotations

import asyncio
import base64
import difflib
import io
import re
import struct
import tempfile
import time
import wave
from pathlib import Path
from typing import Optional

import numpy as np

from packages.common import logger
from packages.config.settings import settings

# ---------------------------------------------------------------------------
# Faster-whisper STT (lazy-loaded singleton)
# ---------------------------------------------------------------------------

_whisper_model = None
_whisper_lock = asyncio.Lock()


async def _get_whisper():
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model

    async with _whisper_lock:
        if _whisper_model is not None:
            return _whisper_model
        try:
            from faster_whisper import WhisperModel
            # Use local model directory if available, else try download
            local_model = Path(__file__).resolve().parents[2] / "models" / "whisper-tiny-en"
            if local_model.exists():
                model_path = str(local_model)
            else:
                model_path = getattr(settings, "WHISPER_MODEL_SIZE", "tiny.en")

            _whisper_model = WhisperModel(
                model_path,
                device="cpu",
                compute_type="int8",
            )
            logger.info(f"voice_stream: faster-whisper loaded (model={model_path})")
            return _whisper_model
        except ImportError:
            logger.error("voice_stream: faster-whisper not installed")
            return None
        except Exception as ex:
            logger.error(f"voice_stream: failed to load whisper model: {ex}")
            return None


async def transcribe_audio(audio_np: np.ndarray, sample_rate: int = 16000) -> str:
    """Transcribe numpy audio array to text using faster-whisper."""
    model = await _get_whisper()
    if model is None:
        return ""

    try:
        # faster-whisper expects float32 normalized audio
        if audio_np.dtype != np.float32:
            audio_np = audio_np.astype(np.float32) / 32768.0

        # Disable vad_filter — we already do our own VAD in AudioBuffer.
        # Whisper's internal VAD can reject short wake words like "Nova".
        def decode():
            segments, _ = model.transcribe(audio_np, beam_size=3, language="en", vad_filter=False)
            return " ".join(segment.text.strip() for segment in segments).strip()
        text = await asyncio.to_thread(decode)
        logger.info(f"voice_stream: transcription result | text='{text}' audio_len={len(audio_np)/sample_rate:.2f}s")
        return text
    except Exception as ex:
        logger.error(f"voice_stream: transcription error: {ex}")
        return ""


def _pcm16_to_wav_base64(audio_np: np.ndarray, sample_rate: int = 16000) -> str:
    """Serialize PCM16 numpy audio to a base64 WAV payload."""
    if audio_np.dtype != np.int16:
        audio_np = np.clip(audio_np, -32768, 32767).astype(np.int16)

    with io.BytesIO() as buf:
        with wave.open(buf, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_np.tobytes())
        return base64.b64encode(buf.getvalue()).decode("ascii")


# ---------------------------------------------------------------------------
# Wake word detection (text-based, fast)
# ---------------------------------------------------------------------------

def detect_wake_word(text: str) -> bool:
    """Check if text contains a wake word trigger."""
    from services.voice.wakeword import WakeWordDetector
    return WakeWordDetector("Nova").matches(text)


def get_wake_ack_phrase() -> str:
    """Return a brief acknowledgment before the user's next turn."""
    return "I'm listening."


def strip_wake_word(text: str) -> str:
    """Remove wake word prefix from transcript."""
    from services.voice.wakeword import WakeWordDetector
    return WakeWordDetector("Nova").strip(text)


# ---------------------------------------------------------------------------
# Audio buffer + VAD (energy-based, no torch needed)
# ---------------------------------------------------------------------------

def is_playback_echo(text: str, reference: str) -> bool:
    words = re.findall(r"\w+", text.lower())
    spoken = re.findall(r"\w+", reference.lower())
    if len(words) < 3 or not spoken:
        return False
    if any(words == spoken[offset:offset + len(words)] for offset in range(len(spoken))):
        return True
    return any(difflib.SequenceMatcher(None, words, spoken[offset:offset + len(words)]).ratio() >= 0.85
               for offset in range(max(1, len(spoken) - len(words) + 1)))


class AudioBuffer:
    """Collects PCM16 audio chunks and detects speech via energy threshold."""

    SAMPLE_RATE = 16000
    # Energy threshold for speech detection (RMS)
    # Calibrated for low-gain microphones (ambient ~0.001-0.002)
    SPEECH_THRESHOLD = 0.005
    # Minimum speech duration to trigger STT (ms)
    MIN_SPEECH_MS = 300
    # Silence after speech to consider utterance complete (ms)
    SILENCE_AFTER_SPEECH_MS = 1200
    # Maximum utterance length before forced flush (seconds)
    MAX_UTTERANCE_SEC = 15

    def __init__(self):
        self.chunks: list[np.ndarray] = []
        self.speech_started = False
        self.speech_start_time: float = 0
        self.last_speech_time: float = 0
        self.total_samples = 0

    def reset(self):
        self.chunks.clear()
        self.speech_started = False
        self.speech_start_time = 0
        self.last_speech_time = 0
        self.total_samples = 0

    def add_chunk(self, pcm16_bytes: bytes) -> Optional[np.ndarray]:
        """
        Add a PCM16 chunk. Returns complete utterance audio if speech ended,
        or None if still collecting.
        """
        if not pcm16_bytes:
            return None

        # Convert bytes to int16 numpy array
        audio = np.frombuffer(pcm16_bytes, dtype=np.int16)
        audio_float = audio.astype(np.float32) / 32768.0
        now = time.time()

        # Calculate RMS energy
        rms = np.sqrt(np.mean(audio_float ** 2)) if len(audio_float) > 0 else 0.0

        # Debug: log every ~2 seconds (32 chunks at 16kHz/4096)
        if not hasattr(self, '_debug_counter'):
            self._debug_counter = 0
        self._debug_counter += 1
        if self._debug_counter % 32 == 0:
            logger.info(f"voice_stream: audio_chunk | rms={rms:.4f} threshold={self.SPEECH_THRESHOLD} speech_started={self.speech_started}")

        is_speech = rms > self.SPEECH_THRESHOLD

        if is_speech:
            if not self.speech_started:
                self.speech_started = True
                self.speech_start_time = now
                # Keep a small pre-buffer (last chunk if any)
            self.last_speech_time = now
            self.chunks.append(audio)
            self.total_samples += len(audio)
        elif self.speech_started:
            # Still buffer during silence gaps within speech
            self.chunks.append(audio)
            self.total_samples += len(audio)

            # Check if silence after speech exceeds threshold
            silence_duration = (now - self.last_speech_time) * 1000
            speech_duration = (now - self.speech_start_time) * 1000
            total_duration = self.total_samples / self.SAMPLE_RATE

            if silence_duration > self.SILENCE_AFTER_SPEECH_MS and speech_duration > self.MIN_SPEECH_MS:
                # Utterance complete
                return self._flush()

        if self.total_samples >= self.MAX_UTTERANCE_SEC * self.SAMPLE_RATE:
            return self._flush()
        return None

    def _flush(self) -> np.ndarray:
        """Flush buffer and return concatenated audio."""
        if not self.chunks:
            self.reset()
            return np.array([], dtype=np.int16)

        result = np.concatenate(self.chunks)
        self.reset()
        return result

    def get_silence_duration(self) -> float:
        """Return seconds of silence since last speech."""
        if not self.speech_started and self.last_speech_time == 0:
            return 0.0
        if self.last_speech_time == 0:
            return 0.0
        return time.time() - self.last_speech_time


# ---------------------------------------------------------------------------
# WebSocket handler
# ---------------------------------------------------------------------------

async def handle_voice_stream(websocket):
    """
    WebSocket handler for real-time voice streaming.

    Protocol:
      Client → Server: binary frames of PCM16 audio @ 16kHz mono
                       OR JSON: {"type": "config", "sample_rate": 16000}
                       OR JSON: {"type": "stop"}

      Server → Client: JSON events:
        {"type": "listening"}           — ready for audio
        {"type": "wake_detected"}       — wake word heard, now in conversation
        {"type": "speech_start"}        — speech activity detected
        {"type": "transcript", "text": "...", "is_wake": false}
        {"type": "silence", "duration": 5.2}
        {"type": "session_end", "reason": "silence_timeout"}
        {"type": "error", "message": "..."}
    """
    from starlette.websockets import WebSocketState

    await websocket.accept()
    logger.info("voice_stream: client connected")

    buffer = AudioBuffer()
    conversation_active = False
    paused = False  # True while client TTS is playing (ignore all audio)
    duplex = False
    playback_reference = ""
    playback_active = False
    playback_until = 0.0
    last_activity = time.time()
    _last_nova_speaking_time = 0.0  # echo suppression cooldown
    silence_timeout = 30.0  # seconds of silence before auto-exit conversation
    running = True

    try:
        await websocket.send_json({"type": "listening"})

        # Pre-load whisper model in background
        asyncio.create_task(_get_whisper())

        while running:
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=0.5)
            except asyncio.TimeoutError:
                # Check silence timeout
                if conversation_active and buffer.get_silence_duration() > silence_timeout:
                    await websocket.send_json({
                        "type": "session_end",
                        "reason": "silence_timeout",
                    })
                    conversation_active = False
                    buffer.reset()
                    await websocket.send_json({"type": "listening"})
                continue

            if message.get("type") == "websocket.disconnect":
                break

            if "bytes" in message and message["bytes"]:
                # Binary audio data — skip while paused or while Nova is speaking
                if paused:
                    continue
                # Server-side echo suppression: skip mic audio while TTS is playing
                _nova_speaking = False
                try:
                    from packages.registry import registry
                    if hasattr(registry, 'voice_engine'):
                        _nova_speaking = (
                            registry.voice_engine.session.state.value == "speaking"
                        )
                        if not _nova_speaking:
                            try:
                                _nova_speaking = bool(registry.voice_engine.synthesizer.is_speaking)
                            except Exception:
                                pass
                except Exception:
                    pass
                if _nova_speaking and not duplex:
                    buffer.reset()
                    _last_nova_speaking_time = time.time()
                    continue
                # 1.5s cooldown after TTS ends to flush residual echo
                if not duplex and time.time() - _last_nova_speaking_time < 0.5:
                    buffer.reset()
                    continue
                if not hasattr(buffer, '_first_audio_logged'):
                    buffer._first_audio_logged = True
                    logger.info(f"voice_stream: first audio chunk received | len={len(message['bytes'])} conversation_active={conversation_active} paused={paused}")
                pcm_data = message["bytes"]
                utterance = buffer.add_chunk(pcm_data)

                if utterance is not None and len(utterance) > 0:
                    # Speech segment complete — transcribe
                    await websocket.send_json({"type": "processing"})

                    text = await transcribe_audio(utterance, AudioBuffer.SAMPLE_RATE)
                    audio_b64 = _pcm16_to_wav_base64(utterance, AudioBuffer.SAMPLE_RATE)

                    if duplex and (playback_active or time.monotonic() < playback_until):
                        if is_playback_echo(text, playback_reference):
                            continue
                        if text and (playback_active or _nova_speaking) and (conversation_active or detect_wake_word(text)):
                            from packages.registry import registry
                            await asyncio.to_thread(registry.voice_engine.stop_speaking)
                            playback_active = False
                            playback_until = time.monotonic() + 2
                            await websocket.send_json({"type": "barge_in"})

                    if text:
                        is_wake = detect_wake_word(text)
                        cleaned = strip_wake_word(text) if is_wake else text

                        # Check if an enrollment session is active — bypass wake word requirement
                        _enrollment_active = False
                        try:
                            from packages.registry import registry as _reg
                            if hasattr(_reg, 'voice_engine') and _reg.voice_engine.has_active_enrollment_session():
                                _enrollment_active = True
                        except Exception:
                            pass

                        if _enrollment_active:
                            # During enrollment, forward all speech as transcripts
                            last_activity = time.time()
                            conversation_active = True
                            await websocket.send_json({
                                "type": "transcript",
                                "text": text,
                                "is_wake": False,
                                "audio_base64": audio_b64,
                                "audio_mime_type": "audio/wav",
                            })
                        elif is_wake and not conversation_active:
                            conversation_active = True
                            last_activity = time.time()
                            await websocket.send_json({
                                "type": "wake_detected",
                                "text": "" if len(cleaned.strip()) >= 3 else get_wake_ack_phrase(),
                            })

                            # Ignore tiny wake leftovers like "x"/"uh" to avoid UI flicker.
                            if cleaned and len(cleaned.strip()) >= 3:
                                # Wake word + command in same utterance
                                await websocket.send_json({
                                    "type": "transcript",
                                    "text": cleaned,
                                    "is_wake": True,
                                    "audio_base64": audio_b64,
                                    "audio_mime_type": "audio/wav",
                                })
                            else:
                                # Just wake word, waiting for command
                                await websocket.send_json({"type": "listening"})
                        elif conversation_active:
                            last_activity = time.time()
                            # Check for exit commands (strip punctuation for whisper output)
                            import re as _re
                            norm = _re.sub(r'[^\w\s]', '', text.lower()).strip()
                            is_exit = norm in ("exit", "quit", "stop listening", "bye", "goodbye", "stop") or \
                                      norm in ("exit nova", "stop nova", "bye nova", "goodbye nova", "quit nova")

                            if is_exit:
                                await websocket.send_json({
                                    "type": "session_end",
                                    "reason": "exit_command",
                                    "text": text,
                                })
                                conversation_active = False
                                buffer.reset()
                                await websocket.send_json({"type": "listening"})
                            else:
                                await websocket.send_json({
                                    "type": "transcript",
                                    "text": cleaned if is_wake else text,
                                    "is_wake": is_wake,
                                    "audio_base64": audio_b64,
                                    "audio_mime_type": "audio/wav",
                                })
                        else:
                            # Not in conversation, not a wake word — ignore
                            await websocket.send_json({"type": "listening"})
                    else:
                        # No text recognized (noise/silence)
                        await websocket.send_json({"type": "listening"})

                elif buffer.speech_started and not utterance:
                    # Speech in progress — notify client
                    pass  # Don't spam, just keep buffering

            elif "text" in message and message["text"]:
                # JSON control message
                try:
                    data = __import__("json").loads(message["text"])
                    msg_type = data.get("type", "")

                    if msg_type == "stop":
                        running = False
                    elif msg_type == "config":
                        duplex = data.get("duplex") is True
                    elif msg_type == "playback_started":
                        playback_reference = str(data.get("text") or "")[:4000]
                        playback_active = True
                        playback_until = time.monotonic() + 120
                        buffer.reset()
                    elif msg_type == "playback_finished":
                        playback_active = False
                        playback_until = time.monotonic() + 2
                    elif msg_type == "start_conversation":
                        # Client initiated direct conversation (mic tap)
                        conversation_active = True
                        last_activity = time.time()
                        buffer.reset()
                        logger.info("voice_stream: manual conversation started")
                        await websocket.send_json({"type": "listening"})
                    elif msg_type == "pause":
                        # Client is about to speak TTS — flush buffer, ignore audio until resume
                        paused = True
                        buffer.reset()
                    elif msg_type == "interrupt":
                        # Client wants to barge-in (stop current response)
                        conversation_active = True
                        paused = False
                        playback_active = False
                        last_activity = time.time()
                        buffer.reset()
                        await websocket.send_json({"type": "listening"})
                    elif msg_type == "resume":
                        # Resume listening after TTS completes
                        paused = False
                        last_activity = time.time()
                        buffer.reset()
                        await websocket.send_json({"type": "listening"})
                    elif msg_type == "exit":
                        conversation_active = False
                        buffer.reset()
                        await websocket.send_json({"type": "listening"})
                except Exception:
                    pass

    except Exception as ex:
        logger.error(f"voice_stream: connection error: {ex}")
        try:
            await websocket.send_json({"type": "error", "message": str(ex)})
        except Exception:
            pass
    finally:
        logger.info("voice_stream: client disconnected")
