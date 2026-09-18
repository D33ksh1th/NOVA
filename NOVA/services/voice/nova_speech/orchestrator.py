"""NOVA Orchestrator — Ties ears, greet, persona, voice, FX, and skills together.

Lifecycle:
  1. nova-ears detects wake word
  2. Chime plays (<30ms)
  3. If no speech follows: nova-greet plays instant greeting (<250ms)
  4. If speech follows: check skills first, then STT -> persona (LLM) -> voice (TTS+FX)
    5. Registered skills execute matched commands
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

import yaml

from .ears import NovaEars
from .greet import NovaGreet
from .voice import NovaVoice
from .fx import NovaFX
from .persona import NovaPersona
from .skills import NovaSkills

logger = logging.getLogger("nova.orchestrator")


class NovaOrchestrator:
    """Main coordinator for the NOVA speech layer."""

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = str(Path(__file__).parent / "config.yaml")

        with open(config_path) as f:
            self._config = yaml.safe_load(f)

        # Initialize modules
        self._fx = NovaFX(self._config)
        self._voice = NovaVoice(self._config, fx_processor=self._fx)
        self._greet = NovaGreet(self._config)
        self._persona = NovaPersona(self._config)
        self._ears = NovaEars(self._config, on_transcript=self._handle_transcript)

        # Skills
        self._skills = NovaSkills()

        # Transport (set externally if WebSocket is running)
        self._transport = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._transcript_log = self._config["logging"].get("transcript_file")

    def start(self):
        """Cold-start all modules. Target: <4s total."""
        t0 = time.time()
        logger.info("nova: starting...")

        # Load models
        self._fx.load()
        self._voice.load()
        self._greet.load_bank()

        elapsed = time.time() - t0
        logger.info("nova: ready in %.1fs", elapsed)

        # Start the event loop
        self._loop = asyncio.new_event_loop()
        try:
            self._loop.run_until_complete(self._ears.start())
        except KeyboardInterrupt:
            logger.info("nova: shutting down...")
        finally:
            self.shutdown()

    async def start_async(self):
        """Async entry point for embedding in existing event loops."""
        t0 = time.time()
        self._fx.load()
        self._voice.load()
        self._greet.load_bank()
        elapsed = time.time() - t0
        logger.info("nova: ready in %.1fs", elapsed)
        await self._ears.start()

    def shutdown(self):
        """Graceful shutdown."""
        self._ears.stop()
        self._voice.shutdown()
        logger.info("nova: shutdown complete")

    def _handle_transcript(self, transcript: str):
        """Callback from nova-ears when speech is transcribed (or empty for greeting)."""
        if not transcript:
            # No speech after wake word — play instant greeting
            t0 = time.time()
            greeting_text = self._greet.play_greeting()
            elapsed_ms = (time.time() - t0) * 1000
            logger.info("nova: greeting path — %dms, %r", int(elapsed_ms), greeting_text[:50])
            self._log_transcript("NOVA", greeting_text)
            return

        # Speech detected
        self._log_transcript("USER", transcript)

        # Check skills first (commands bypass LLM)
        skill_id = self._skills.match(transcript)
        if skill_id:
            logger.info("nova: skill detected — %s", skill_id)
            if self._loop and self._loop.is_running():
                asyncio.ensure_future(
                    self._skills.execute(skill_id, transcript), loop=self._loop
                )
            else:
                asyncio.run(self._skills.execute(skill_id, transcript))
            return

        # Normal LLM path
        t0 = time.time()
        sentences = self._persona.think(transcript)
        llm_ms = (time.time() - t0) * 1000
        logger.info("nova: LLM path — %dms for %d sentences", int(llm_ms), len(sentences))

        # Speak with streaming TTS
        if self._loop and self._loop.is_running():
            asyncio.ensure_future(self._voice.speak(sentences), loop=self._loop)
        else:
            asyncio.run(self._voice.speak(sentences))

        # Log response
        full_text = " ".join(s["text"] for s in sentences)
        self._log_transcript("NOVA", full_text)

    async def _speak_single(self, text: str, emotion: str = "neutral"):
        """Speak a single sentence (used by skills for progress updates)."""
        await self._voice.speak([{"text": text, "emotion": emotion}])
        self._log_transcript("NOVA", text)

    def _log_transcript(self, speaker: str, text: str):
        """Log transcript to file with restricted permissions."""
        if not self._transcript_log:
            return

        import os
        log_path = Path(self._transcript_log)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        with open(log_path, "a") as f:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {speaker}: {text}\n")

        # Set restricted permissions
        try:
            os.chmod(log_path, 0o600)
        except OSError:
            pass
