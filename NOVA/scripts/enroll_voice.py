#!/usr/bin/env python3
"""Direct microphone voice enrollment — bypasses browser audio path.

Usage: python scripts/enroll_voice.py "Deekshith KR" --samples 5 --duration 4

Records audio directly from the system microphone using sounddevice,
computes ECAPA-TDNN embeddings, and enrolls the speaker profile.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf


def record_sample(duration: float, sample_rate: int = 16000, prompt: str = "") -> np.ndarray:
    """Record audio from the default mic."""
    if prompt:
        print(f"\n  📢 {prompt}")
    print(f"  🎙️  Recording for {duration}s... speak NOW")
    audio = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, dtype="float32")
    sd.wait()
    audio = audio.flatten()
    rms = float(np.sqrt(np.mean(audio ** 2)))
    print(f"  ✅ Captured {len(audio)} samples, RMS={rms:.4f}")
    return audio


def main():
    parser = argparse.ArgumentParser(description="Enroll a speaker via direct mic recording")
    parser.add_argument("name", help="Speaker name (e.g. 'Deekshith KR')")
    parser.add_argument("--samples", type=int, default=5, help="Number of samples to record")
    parser.add_argument("--duration", type=float, default=4.0, help="Duration per sample (seconds)")
    parser.add_argument("--role", default="admin", help="Role: admin or user")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  NOVA Voice Enrollment — Direct Mic")
    print(f"{'='*60}")
    print(f"  Name: {args.name}")
    print(f"  Samples: {args.samples} x {args.duration}s")
    print(f"  Role: {args.role}")
    print(f"  Device: {sd.query_devices(kind='input')['name']}")
    print(f"{'='*60}")

    prompts = [
        "Say: My voice is clear and steady.",
        "Say: Nova, please recognize my profile.",
        "Say: Security and privacy matter to me.",
        "Say: I am ready to use voice commands.",
        "Say: The quick brown fox jumps over the lazy dog.",
        "Say: Today is a good day to build something great.",
        "Say: Good morning, how are you doing today?",
        "Say: Please run a security scan on all systems.",
    ]

    # Add project root to path
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))

    import tempfile
    audio_paths = []

    for i in range(args.samples):
        prompt = prompts[i % len(prompts)]
        input(f"\n  Press ENTER when ready for sample {i+1}/{args.samples}...")
        audio = record_sample(args.duration, prompt=prompt)

        # Save to temp file
        path = Path(tempfile.mkdtemp()) / f"enroll_{i}.wav"
        sf.write(str(path), audio, 16000)
        audio_paths.append(str(path))

        # Quick quality check
        rms = float(np.sqrt(np.mean(audio ** 2)))
        duration = len(audio) / 16000
        if rms < 0.003:
            print(f"  ⚠️  Audio very quiet (RMS={rms:.4f}). Speak louder or move closer to mic.")
        if duration < 2.0:
            print(f"  ⚠️  Audio too short ({duration:.1f}s). Need at least 2s.")

    print(f"\n{'='*60}")
    print(f"  Computing embeddings...")

    # Test embeddings
    from services.voice.embedding import embed_utterance, embed_batch, cosine_similarity, intra_speaker_variance

    embeddings = []
    for path in audio_paths:
        emb = embed_utterance(path)
        if emb is not None:
            embeddings.append(emb)
            print(f"  ✅ {Path(path).name}: {len(emb)}-dim embedding")
        else:
            print(f"  ❌ {Path(path).name}: embedding failed")

    if len(embeddings) < 3:
        print(f"\n  ❌ Only {len(embeddings)} valid embeddings. Need at least 3. Try again.")
        return 1

    # Check variance
    variance = intra_speaker_variance(embeddings)
    print(f"\n  Intra-speaker variance: {variance:.4f} (threshold: 0.45)")
    if variance > 0.45:
        print(f"  ⚠️  High variance — samples may be inconsistent. Proceeding anyway.")

    # Compute centroid
    centroid = np.mean(embeddings, axis=0).tolist()

    # Cross-check: each sample vs centroid
    print(f"\n  Similarity check:")
    for i, emb in enumerate(embeddings):
        sim = cosine_similarity(emb, centroid)
        print(f"    Sample {i+1} vs centroid: {sim:.4f}")

    # Enroll
    from services.voice.speaker import SpeakerRegistry
    from services.voice.embedding import vec_to_hex

    registry = SpeakerRegistry()
    from services.voice.models import SpeakerProfile
    import uuid
    from datetime import datetime, timezone

    existing = registry.get(args.name)
    profile = SpeakerProfile(
        id=existing.id if existing else str(uuid.uuid4()),
        name=args.name,
        embedding=vec_to_hex(centroid),
        samples=len(embeddings),
        role=args.role,
        created_at=existing.created_at if existing else datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    registry._profiles[args.name.lower()] = profile
    registry._save()

    print(f"\n{'='*60}")
    print(f"  ✅ ENROLLED: {profile.name}")
    print(f"  ID: {profile.id}")
    print(f"  Role: {profile.role}")
    print(f"  Samples: {profile.samples}")
    print(f"  Embedding: {len(centroid)}-dim")
    print(f"  Variance: {variance:.4f}")
    print(f"{'='*60}")

    # Verify by testing recognition
    print(f"\n  Testing recognition...")
    input(f"  Press ENTER, then say something (4 seconds)...")
    test_audio = record_sample(4.0, prompt="Say anything naturally.")
    test_path = Path(tempfile.mkdtemp()) / "test.wav"
    sf.write(str(test_path), test_audio, 16000)

    test_emb = embed_utterance(str(test_path))
    if test_emb:
        sim = cosine_similarity(test_emb, centroid)
        print(f"\n  Test similarity: {sim:.4f} (threshold: 0.60)")
        if sim >= 0.60:
            print(f"  ✅ RECOGNITION PASSED — you would be recognized as {args.name}")
        else:
            print(f"  ⚠️  Below threshold. Try re-enrolling in a quieter environment.")
    else:
        print(f"  ❌ Test embedding failed")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
