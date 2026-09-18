"""SpeechBrain ECAPA-TDNN speaker embedding engine.

Replaces Resemblyzer's 2019 GE2E d-vector model with ECAPA-TDNN,
which achieves ~2-4% EER vs Resemblyzer's ~7-12% in noise.

The model is loaded once and kept resident in memory — no subprocess
spawning per utterance.
"""

from __future__ import annotations

import math
import struct
import threading
from pathlib import Path
from typing import Optional

from packages.common import logger


_MODEL_LOCK = threading.Lock()
_ENCODER = None
_BACKEND = "none"


def _load_encoder():
    """Load the best available speaker encoder, preferring SpeechBrain ECAPA-TDNN."""
    global _ENCODER, _BACKEND

    with _MODEL_LOCK:
        if _ENCODER is not None:
            return _ENCODER, _BACKEND

        # Try SpeechBrain ECAPA-TDNN first
        try:
            # Work around corporate/macOS SSL certificate issues for model download
            import os
            os.environ.setdefault("HF_HUB_DISABLE_SSL_VERIFY", "1")

            from speechbrain.inference.speaker import EncoderClassifier
            _ENCODER = EncoderClassifier.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb",
                run_opts={"device": "cpu"},
            )
            _BACKEND = "ecapa-tdnn"
            logger.info("Speaker encoder loaded: SpeechBrain ECAPA-TDNN (192-dim)")
            return _ENCODER, _BACKEND
        except ImportError:
            logger.info("SpeechBrain not available, trying Resemblyzer fallback")
        except Exception as ex:
            logger.warning(f"SpeechBrain load failed: {ex}, trying Resemblyzer")

        # Fallback to Resemblyzer
        try:
            from resemblyzer import VoiceEncoder
            _ENCODER = VoiceEncoder()
            _BACKEND = "resemblyzer"
            logger.info("Speaker encoder loaded: Resemblyzer GE2E (256-dim)")
            return _ENCODER, _BACKEND
        except ImportError:
            logger.warning("Resemblyzer not available either")
        except Exception as ex:
            logger.warning(f"Resemblyzer load failed: {ex}")

        _BACKEND = "none"
        return None, _BACKEND


def embed_utterance(audio_path: str) -> Optional[list[float]]:
    """Compute a speaker embedding from a single audio file."""
    encoder, backend = _load_encoder()
    if encoder is None:
        return None

    p = Path(audio_path)
    if not p.exists():
        logger.warning("embed_utterance: file not found", path=audio_path)
        return None

    try:
        if backend == "ecapa-tdnn":
            embedding = encoder.encode_batch(
                encoder.load_audio(str(p)).unsqueeze(0)
            )
            return embedding.squeeze().tolist()
        elif backend == "resemblyzer":
            from resemblyzer import preprocess_wav
            wav = preprocess_wav(p)
            emb = encoder.embed_utterance(wav)
            return emb.tolist()
    except Exception as ex:
        logger.warning(f"embed_utterance failed: {ex}", path=audio_path)
    return None


def embed_batch(audio_paths: list[str]) -> Optional[list[float]]:
    """Compute a mean embedding from multiple audio files."""
    embeddings = []
    for path in audio_paths:
        emb = embed_utterance(path)
        if emb is not None:
            embeddings.append(emb)

    if not embeddings:
        return None

    try:
        import numpy as np
        mean_emb = np.mean(embeddings, axis=0)
        return mean_emb.tolist()
    except ImportError:
        # Pure-python fallback
        dim = len(embeddings[0])
        mean = [0.0] * dim
        for emb in embeddings:
            for i in range(dim):
                mean[i] += emb[i]
        n = len(embeddings)
        return [x / n for x in mean]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def vec_to_hex(vec: list[float]) -> str:
    return struct.pack(f"{len(vec)}f", *vec).hex()


def hex_to_vec(hex_str: str) -> Optional[list[float]]:
    try:
        raw = bytes.fromhex(hex_str)
        count = len(raw) // 4
        if count < 64:
            return None
        return list(struct.unpack(f"{count}f", raw))
    except Exception:
        return None


def is_audio_embedding(hex_str: str) -> bool:
    vec = hex_to_vec(hex_str)
    return bool(vec and len(vec) >= 64)


def intra_speaker_variance(embeddings: list[list[float]]) -> float:
    """Compute mean pairwise cosine distance among a set of embeddings.
    Lower is better — high variance means inconsistent enrollment samples."""
    if len(embeddings) < 2:
        return 0.0
    n = len(embeddings)
    total = 0.0
    count = 0
    for i in range(n):
        for j in range(i + 1, n):
            total += 1.0 - cosine_similarity(embeddings[i], embeddings[j])
            count += 1
    return total / count if count > 0 else 0.0


def get_backend() -> str:
    """Return the name of the loaded backend without triggering a load."""
    return _BACKEND
