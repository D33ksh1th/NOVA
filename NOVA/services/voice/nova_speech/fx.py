"""Module 4: nova-fx — Audio post-processing chain.

Applied to every synthesized chunk before playback:
  1. Highpass 110Hz
  2. Presence EQ +2.5dB @ 4kHz
  3. High shelf -1.5dB @ 8kHz
  4. Compressor 3:1
  5. Plate reverb (room 0.25, wet 0.10)
  6. Loudness normalize -16 LUFS

All values configurable. --no-fx flag bypasses entirely.
"""

import logging

import numpy as np

logger = logging.getLogger("nova.fx")


class NovaFX:
    """Audio post-processing chain for NOVA voice output."""

    def __init__(self, config: dict):
        self._cfg = config["fx"]
        self._enabled = self._cfg.get("enabled", True)
        self._board = None

    def load(self):
        """Initialize pedalboard effects chain."""
        if not self._enabled:
            logger.info("nova-fx: disabled (--no-fx)")
            return

        try:
            from pedalboard import (
                Pedalboard,
                HighpassFilter,
                Compressor,
                Reverb,
                Gain,
            )
            from pedalboard import PeakFilter, HighShelfFilter
        except ImportError:
            logger.warning("nova-fx: pedalboard not installed, FX disabled")
            self._enabled = False
            return

        chain_cfg = self._cfg["chain"]

        self._board = Pedalboard([
            # 1. Highpass — remove muddy low end
            HighpassFilter(cutoff_frequency_hz=chain_cfg["highpass_hz"]),

            # 2. Presence EQ — intelligibility boost
            PeakFilter(
                cutoff_frequency_hz=chain_cfg["presence_eq"]["freq_hz"],
                gain_db=chain_cfg["presence_eq"]["gain_db"],
                q=chain_cfg["presence_eq"]["q"],
            ),

            # 3. High shelf — tame digital fizz
            HighShelfFilter(
                cutoff_frequency_hz=chain_cfg["high_shelf"]["freq_hz"],
                gain_db=chain_cfg["high_shelf"]["gain_db"],
            ),

            # 4. Compressor — even out dynamics
            Compressor(
                ratio=chain_cfg["compressor"]["ratio"],
                threshold_db=chain_cfg["compressor"]["threshold_db"],
                attack_ms=chain_cfg["compressor"]["attack_ms"],
                release_ms=chain_cfg["compressor"]["release_ms"],
            ),

            # 5. Plate reverb — "AI in a room" cue
            Reverb(
                room_size=chain_cfg["reverb"]["room_size"],
                wet_level=chain_cfg["reverb"]["wet"],
                dry_level=1.0 - chain_cfg["reverb"]["wet"],
            ),
        ])

        logger.info("nova-fx: chain loaded (highpass=%dHz, presence=+%.1fdB@%dHz, "
                    "compress=%.0f:1, reverb=%.2f wet)",
                    chain_cfg["highpass_hz"],
                    chain_cfg["presence_eq"]["gain_db"],
                    chain_cfg["presence_eq"]["freq_hz"],
                    chain_cfg["compressor"]["ratio"],
                    chain_cfg["reverb"]["wet"])

    def process(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """Apply FX chain to audio. Returns processed float32 array."""
        if not self._enabled or self._board is None:
            return audio

        # Pedalboard expects (channels, samples) or (samples,) for mono
        if audio.ndim == 1:
            audio_2d = audio.reshape(1, -1)
        else:
            audio_2d = audio

        processed = self._board(audio_2d, sample_rate)

        # Loudness normalization
        processed = self._normalize_loudness(
            processed.flatten(),
            sample_rate,
            target_lufs=self._cfg["chain"]["loudness"]["target_lufs"],
            true_peak_dbtp=self._cfg["chain"]["loudness"]["true_peak_dbtp"],
        )

        return processed

    def _normalize_loudness(
        self,
        audio: np.ndarray,
        sample_rate: int,
        target_lufs: float = -16.0,
        true_peak_dbtp: float = -1.0,
    ) -> np.ndarray:
        """Normalize to target LUFS with true-peak limiting."""
        # Measure current loudness (simplified integrated LUFS)
        # RMS-based approximation for speed
        rms = np.sqrt(np.mean(audio ** 2))
        if rms < 1e-10:
            return audio

        current_lufs_approx = 20 * np.log10(rms) - 0.691
        gain_db = target_lufs - current_lufs_approx
        gain_linear = 10 ** (gain_db / 20)

        normalized = audio * gain_linear

        # True-peak limiting
        peak = np.max(np.abs(normalized))
        peak_limit = 10 ** (true_peak_dbtp / 20)
        if peak > peak_limit:
            normalized *= peak_limit / peak

        return normalized.astype(np.float32)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value
