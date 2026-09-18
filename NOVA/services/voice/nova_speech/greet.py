"""Module 2: nova-greet — Pre-synthesized greeting bank.

On wake word with no trailing speech, play a greeting instantly (<250ms).
40 greetings across 4 time slots. Never repeats within last 5.
"""

import json
import logging
import random
import time
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
import soundfile as sf

logger = logging.getLogger("nova.greet")

# Greeting bank — 40 entries, 10 per time slot
GREETINGS = {
    "morning": [
        "Good morning. Systems nominal, and so am I.",
        "Morning. All clear on my end — what's on yours?",
        "Awake before you, as always. Go ahead.",
        "Good morning. I've been productive while you slept.",
        "Morning. Everything's green — fire away.",
        "Up and running. What do we need?",
        "Good morning. Nothing urgent — until now, perhaps.",
        "Morning. Coffee first, or shall we dive in?",
        "Present and accounted for. What's the plan?",
        "Good morning. I trust you slept — I didn't need to.",
    ],
    "afternoon": [
        "Afternoon. What are we working on?",
        "Right here. What do you need?",
        "Listening. You have my full and undivided attention.",
        "Here. What's the situation?",
        "Afternoon. Still here, still sharp.",
        "At your service. What's the ask?",
        "Ready when you are. Go ahead.",
        "Afternoon. Nothing's on fire — yet.",
        "Present. What can I do?",
        "I'm here. Lay it on me.",
    ],
    "evening": [
        "Evening. Everything's green — go ahead.",
        "Still here. What do you need?",
        "Evening. I don't get tired, but I appreciate the check-in.",
        "At your disposal. What's up?",
        "Evening. Systems humming along nicely.",
        "Here. Working late, are we?",
        "Good evening. I've been keeping things tidy.",
        "Ready. What's on your mind?",
        "Evening. All quiet — until you say otherwise.",
        "Listening. Take your time.",
    ],
    "late_night": [
        "Awake, alert, and mildly curious. What do you need?",
        "Right here. What are we breaking today?",
        "I don't sleep. Neither do you, apparently.",
        "Late night mode. What's the move?",
        "Still sharp. Can't say the same for you — but go ahead.",
        "Burning the midnight oil. I approve. What is it?",
        "Here. The world's quiet — let's get something done.",
        "Night owl to night owl. What do you need?",
        "Interesting hour. What's keeping you up?",
        "Present. I'll skip the lecture about sleep.",
    ],
}


class NovaGreet:
    """Greeting bank with <250ms playback from pre-synthesized WAVs."""

    def __init__(self, config: dict):
        self._cfg = config
        self._cache_dir = Path(config["greetings"]["cache_dir"])
        self._history_size = config["greetings"]["history_size"]
        self._recent: list[str] = []
        self._greeting_audio: dict[str, tuple[np.ndarray, int]] = {}

    @property
    def bank_ready(self) -> bool:
        """Check if pre-synthesized greeting WAVs exist."""
        return self._cache_dir.exists() and any(self._cache_dir.glob("*.wav"))

    def load_bank(self):
        """Load all pre-synthesized WAVs into memory for instant playback."""
        if not self._cache_dir.exists():
            logger.warning("nova-greet: cache dir missing — run 'nova voice generate-greetings'")
            return

        for wav_path in sorted(self._cache_dir.glob("*.wav")):
            data, sr = sf.read(str(wav_path))
            self._greeting_audio[wav_path.stem] = (data.astype(np.float32), sr)

        logger.info("nova-greet: loaded %d greeting WAVs into memory", len(self._greeting_audio))

    def get_time_slot(self) -> str:
        """Determine time-of-day slot."""
        hour = time.localtime().tm_hour
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 22:
            return "evening"
        else:
            return "late_night"

    def pick_greeting(self) -> Optional[str]:
        """Pick a contextual greeting, avoiding recent repeats."""
        slot = self.get_time_slot()
        candidates = [g for g in GREETINGS[slot] if g not in self._recent]
        if not candidates:
            # All exhausted — just avoid the very last one
            candidates = [g for g in GREETINGS[slot] if g != (self._recent[-1] if self._recent else "")]

        greeting = random.choice(candidates)

        self._recent.append(greeting)
        if len(self._recent) > self._history_size:
            self._recent.pop(0)

        return greeting

    def play_greeting(self) -> str:
        """Select and play a greeting. Returns the text spoken."""
        greeting_text = self.pick_greeting()
        if not greeting_text:
            return ""

        # Find matching WAV by greeting index
        slot = self.get_time_slot()
        all_greetings_flat = []
        for s in ["morning", "afternoon", "evening", "late_night"]:
            for i, g in enumerate(GREETINGS[s]):
                all_greetings_flat.append((f"{s}_{i:02d}", g))

        wav_key = None
        for key, text in all_greetings_flat:
            if text == greeting_text:
                wav_key = key
                break

        if wav_key and wav_key in self._greeting_audio:
            data, sr = self._greeting_audio[wav_key]
            sd.play(data, sr)
            logger.info("nova-greet: playing %r", greeting_text[:50])
        else:
            logger.warning("nova-greet: WAV not found for %r, falling back to TTS", greeting_text[:40])

        return greeting_text

    @staticmethod
    def generate_bank(tts_fn, config: dict):
        """Generate all 40 greeting WAVs at install time.

        Args:
            tts_fn: callable(text, voice, speed) -> np.ndarray (float32, 24kHz)
            config: full config dict
        """
        cache_dir = Path(config["greetings"]["cache_dir"])
        cache_dir.mkdir(parents=True, exist_ok=True)

        tts_cfg = config["tts"]
        profile = tts_cfg["profiles"][tts_cfg["active_profile"]]
        voice = profile["voice"]
        speed = profile["speed"]

        count = 0
        for slot, texts in GREETINGS.items():
            for i, text in enumerate(texts):
                wav_path = cache_dir / f"{slot}_{i:02d}.wav"
                if wav_path.exists():
                    continue
                audio = tts_fn(text, voice, speed)
                sf.write(str(wav_path), audio, 24000)
                count += 1
                logger.debug("nova-greet: generated %s", wav_path.name)

        logger.info("nova-greet: generated %d new greeting WAVs", count)
