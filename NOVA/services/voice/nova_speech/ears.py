"""Module 1: nova-ears — Wake word detection + VAD + STT pipeline.

openWakeWord -> confirmation chime -> Silero VAD capture -> faster-whisper STT.
Runs continuously. All audio stays on localhost.
"""

import asyncio
import hashlib
import logging
import time
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

logger = logging.getLogger("nova.ears")


class NovaEars:
    """Always-listening wake word detector with VAD-gated STT."""

    def __init__(self, config: dict, on_transcript: Callable[[str], None]):
        self._cfg = config
        self._on_transcript = on_transcript
        self._running = False
        self._last_wake_time = 0.0
        self._sample_rate = config["vad"]["sample_rate"]

        # Lazy-loaded models
        self._oww_model = None
        self._vad_model = None
        self._stt_model = None

    async def start(self):
        """Start the always-listening loop."""
        self._running = True
        self._load_models()
        logger.info("nova-ears: listening (wake word=%s, threshold=%.2f)",
                    self._cfg["wake_word"]["model"],
                    self._cfg["wake_word"]["threshold"])
        await self._listen_loop()

    def stop(self):
        self._running = False

    def _load_models(self):
        """Load wake word, VAD, and STT models."""
        from openwakeword.model import Model as OWWModel
        self._oww_model = OWWModel(
            wakeword_models=[self._cfg["wake_word"]["model"]],
            inference_framework="onnx",
        )

        import torch
        self._vad_model, vad_utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            trust_repo=True,
        )
        self._vad_get_speech_timestamps = vad_utils[0]

        from faster_whisper import WhisperModel
        stt_cfg = self._cfg["stt"]
        self._stt_model = WhisperModel(
            stt_cfg["model"],
            device=stt_cfg["device"],
            compute_type=stt_cfg["compute_type"],
        )
        logger.info("nova-ears: all models loaded")

    async def _listen_loop(self):
        """Continuous audio capture, wake word detection."""
        chunk_size = int(self._sample_rate * 0.08)  # 80ms chunks
        stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=1,
            dtype="int16",
            blocksize=chunk_size,
        )
        stream.start()

        try:
            while self._running:
                audio_chunk, _ = stream.read(chunk_size)
                audio_f32 = audio_chunk.flatten().astype(np.float32) / 32768.0

                # Feed to wake word model
                prediction = self._oww_model.predict(audio_f32)
                score = prediction.get(self._cfg["wake_word"]["model"], 0.0)

                if score >= self._cfg["wake_word"]["threshold"]:
                    now = time.time()
                    refractory = self._cfg["wake_word"]["refractory_period_s"]
                    if now - self._last_wake_time < refractory:
                        continue
                    self._last_wake_time = now
                    logger.info("nova-ears: wake word detected (score=%.3f)", score)

                    # Play confirmation chime IMMEDIATELY
                    await self._play_chime()

                    # Capture speech via VAD
                    audio_buffer = await self._vad_capture(stream, chunk_size)

                    if audio_buffer is not None and len(audio_buffer) > 0:
                        # Transcribe
                        transcript = self._transcribe(audio_buffer)
                        if transcript.strip():
                            logger.info("nova-ears: transcript=%r", transcript[:80])
                            self._on_transcript(transcript)
                    else:
                        # No speech after wake word — trigger greeting
                        self._on_transcript("")

                await asyncio.sleep(0)  # yield to event loop
        finally:
            stream.stop()
            stream.close()

    async def _play_chime(self):
        """Play 180ms rising two-tone confirmation chime."""
        chime_path = Path(self._cfg["wake_word"]["chime_path"])
        if chime_path.exists():
            import soundfile as sf
            data, sr = sf.read(str(chime_path))
            sd.play(data, sr)
        else:
            # Generate synthetic chime: rising two-tone, 180ms
            sr = 24000
            duration = 0.18
            t = np.linspace(0, duration, int(sr * duration), dtype=np.float32)
            # Two rising tones: 880Hz -> 1320Hz
            freq = np.linspace(880, 1320, len(t))
            chime = 0.3 * np.sin(2 * np.pi * freq * t)
            # Envelope: quick attack, gentle decay
            envelope = np.minimum(t / 0.01, 1.0) * np.exp(-t * 8)
            chime *= envelope
            sd.play(chime, sr)
        logger.debug("nova-ears: chime played")

    async def _vad_capture(self, stream, chunk_size: int) -> Optional[np.ndarray]:
        """Capture speech using Silero VAD until trailing silence or hard cap."""
        import torch

        trailing_silence_ms = self._cfg["vad"]["trailing_silence_ms"]
        hard_cap_s = self._cfg["vad"]["hard_cap_s"]
        sr = self._sample_rate

        buffer = []
        silence_start: Optional[float] = None
        capture_start = time.time()

        while True:
            elapsed = time.time() - capture_start
            if elapsed > hard_cap_s:
                logger.warning("nova-ears: VAD hard cap reached (%.1fs)", hard_cap_s)
                break

            audio_chunk, _ = stream.read(chunk_size)
            audio_f32 = audio_chunk.flatten().astype(np.float32) / 32768.0
            buffer.append(audio_f32)

            # Check VAD
            tensor = torch.from_numpy(audio_f32)
            speech_prob = self._vad_model(tensor, sr).item()

            if speech_prob < 0.3:
                if silence_start is None:
                    silence_start = time.time()
                elif (time.time() - silence_start) * 1000 >= trailing_silence_ms:
                    logger.debug("nova-ears: VAD trailing silence reached")
                    break
            else:
                silence_start = None

            await asyncio.sleep(0)

        if not buffer:
            return None
        return np.concatenate(buffer)

    def _transcribe(self, audio: np.ndarray) -> str:
        """Transcribe audio buffer using faster-whisper."""
        segments, _ = self._stt_model.transcribe(
            audio,
            beam_size=self._cfg["stt"]["beam_size"],
            language=self._cfg["stt"]["language"],
            vad_filter=True,
        )
        return " ".join(seg.text.strip() for seg in segments)
