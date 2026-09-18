"""Module 3: nova-voice — Kokoro TTS daemon.

Loads kokoro-onnx ONCE at startup, holds warm in memory.
Streams sentence-by-sentence with a playback queue.
Caches every synthesis by SHA-256(text + voice + speed).
Supports voice blending.
"""

import asyncio
import hashlib
import logging
import queue
import threading
import time
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
import soundfile as sf

logger = logging.getLogger("nova.voice")


class NovaVoice:
    """Persistent TTS daemon using kokoro-onnx. Never spawns per-utterance."""

    def __init__(self, config: dict, fx_processor=None):
        self._cfg = config["tts"]
        self._emotion_cfg = config["emotions"]
        self._fx = fx_processor
        self._cache_dir = Path(self._cfg["cache_dir"])
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._sample_rate = self._cfg["sample_rate"]

        # Playback queue for streaming
        self._playback_queue: queue.Queue = queue.Queue()
        self._playback_thread: Optional[threading.Thread] = None
        self._playing = False

        # Model (loaded once)
        self._kokoro = None
        self._voice_tensors: dict[str, np.ndarray] = {}

    def load(self):
        """Load kokoro-onnx model and voice tensors. Call once at startup."""
        from kokoro_onnx import Kokoro

        self._kokoro = Kokoro(
            self._cfg["model_path"],
            self._cfg["voices_path"],
        )
        logger.info("nova-voice: kokoro-onnx loaded (model=%s)", self._cfg["model_path"])

        # Start playback thread
        self._playing = True
        self._playback_thread = threading.Thread(
            target=self._playback_worker, daemon=True, name="nova-voice-playback"
        )
        self._playback_thread.start()

    def _get_blended_voice(self) -> str:
        """Get the active voice name (blending handled at synthesis time)."""
        profile_name = self._cfg["active_profile"]
        profile = self._cfg["profiles"][profile_name]
        return profile["voice"]

    def _get_blend_config(self) -> list[dict]:
        """Get blend configuration for active profile."""
        profile_name = self._cfg["active_profile"]
        profile = self._cfg["profiles"][profile_name]
        return profile.get("blend", [{"voice": profile["voice"], "weight": 1.0}])

    def _cache_key(self, text: str, voice: str, speed: float) -> str:
        """SHA-256 cache key."""
        content = f"{text}|{voice}|{speed:.3f}"
        return hashlib.sha256(content.encode()).hexdigest()

    def _cache_get(self, key: str) -> Optional[np.ndarray]:
        """Load cached audio if available."""
        path = self._cache_dir / f"{key}.wav"
        if path.exists():
            data, _ = sf.read(str(path), dtype="float32")
            return data
        return None

    def _cache_put(self, key: str, audio: np.ndarray):
        """Save audio to cache."""
        path = self._cache_dir / f"{key}.wav"
        sf.write(str(path), audio, self._sample_rate)

    def synthesize_sentence(self, text: str, voice: str, speed: float) -> np.ndarray:
        """Synthesize a single sentence. Uses cache. Returns float32 audio."""
        key = self._cache_key(text, voice, speed)
        cached = self._cache_get(key)
        if cached is not None:
            logger.debug("nova-voice: cache hit for %r", text[:40])
            return cached

        t0 = time.time()

        # Blended synthesis
        blend_cfg = self._get_blend_config()
        if len(blend_cfg) > 1:
            audio = self._synthesize_blended(text, blend_cfg, speed)
        else:
            samples, _ = self._kokoro.create(text, voice=voice, speed=speed)
            audio = samples

        elapsed_ms = (time.time() - t0) * 1000
        logger.debug("nova-voice: synthesized %r in %.0fms", text[:40], elapsed_ms)

        self._cache_put(key, audio)
        return audio

    def _synthesize_blended(self, text: str, blend_cfg: list[dict], speed: float) -> np.ndarray:
        """Synthesize with weighted voice blending."""
        outputs = []
        weights = []
        for entry in blend_cfg:
            samples, _ = self._kokoro.create(text, voice=entry["voice"], speed=speed)
            outputs.append(samples)
            weights.append(entry["weight"])

        # Align lengths (pad shorter to longest)
        max_len = max(len(o) for o in outputs)
        aligned = []
        for o in outputs:
            if len(o) < max_len:
                o = np.pad(o, (0, max_len - len(o)))
            aligned.append(o)

        # Weighted sum
        total_weight = sum(weights)
        blended = sum(a * (w / total_weight) for a, w in zip(aligned, weights))
        return blended.astype(np.float32)

    def apply_emotion(self, text: str, emotion: str) -> tuple[str, float, int]:
        """Apply emotion mapping: text preprocessing, speed modifier, pause.

        Returns: (processed_text, speed_multiplier, pause_before_ms)
        """
        emo_cfg = self._emotion_cfg.get(emotion, self._emotion_cfg["neutral"])
        speed_mult = emo_cfg["speed_multiplier"]
        pause_ms = emo_cfg["pause_before_ms"]
        rewrite = emo_cfg.get("rewrite")

        processed = text
        if rewrite == "soften":
            # Add commas around address terms
            for term in ["friend", "sir", "mate", "boss"]:
                processed = processed.replace(f" {term} ", f", {term}, ")
        elif rewrite == "punchline_pause":
            # Add ellipsis before last clause
            parts = processed.rsplit(",", 1)
            if len(parts) == 2:
                processed = f"{parts[0]},...{parts[1]}"
        elif rewrite == "strip_subordinate":
            # Remove "although", "however", "nevertheless" clauses
            for w in ["although ", "however, ", "nevertheless, ", "while "]:
                if processed.lower().startswith(w):
                    processed = processed[len(w):]
                    break
        elif rewrite == "em_dash":
            # Add em-dash before the key noun phrase (last noun cluster)
            words = processed.split()
            if len(words) > 4:
                processed = " ".join(words[:-3]) + " — " + " ".join(words[-3:])

        return processed, speed_mult, pause_ms

    async def speak(self, sentences: list[dict]):
        """Speak a list of {text, emotion} dicts with streaming playback.

        Begins playback of sentence N while synthesizing sentence N+1.
        """
        profile = self._cfg["profiles"][self._cfg["active_profile"]]
        base_speed = profile["speed"]
        voice = profile["voice"]

        for i, item in enumerate(sentences):
            text = item["text"]
            emotion = item.get("emotion", "neutral")

            # Apply emotion modifiers
            processed_text, speed_mult, pause_ms = self.apply_emotion(text, emotion)
            speed = base_speed * speed_mult

            # Insert pause
            if pause_ms > 0 and i > 0:
                silence_samples = int(self._sample_rate * pause_ms / 1000)
                silence = np.zeros(silence_samples, dtype=np.float32)
                self._playback_queue.put(silence)

            # Synthesize
            audio = self.synthesize_sentence(processed_text, voice, speed)

            # Apply FX if available
            if self._fx:
                audio = self._fx.process(audio, self._sample_rate)

            # Queue for playback (streaming: next sentence synthesizes while this plays)
            self._playback_queue.put(audio)

        # Signal end of utterance
        self._playback_queue.put(None)

    def speak_sync(self, text: str, voice: str, speed: float) -> np.ndarray:
        """Synchronous single-sentence synthesis (for greeting generation)."""
        return self.synthesize_sentence(text, voice, speed)

    def _playback_worker(self):
        """Background thread: plays audio chunks from the queue."""
        while self._playing:
            try:
                chunk = self._playback_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if chunk is None:
                # End of utterance marker
                continue

            try:
                sd.play(chunk, self._sample_rate)
                sd.wait()
            except Exception as e:
                logger.error("nova-voice: playback error: %s", e)

    def shutdown(self):
        """Stop playback thread."""
        self._playing = False
        if self._playback_thread:
            self._playback_thread.join(timeout=2)
        logger.info("nova-voice: shutdown complete")
