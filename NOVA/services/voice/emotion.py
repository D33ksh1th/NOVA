"""Emotion detection for voice/text turns.

Two backends, chosen by EMOTION_PROVIDER in settings:

  "heuristic"        — keyword-based text analysis. Always available.

  "wav2vec2-emotion" — real audio emotion classification via
                       transformers + SpeechBrain.
                       Requires: transformers, torch, torchaudio
                       (pip install transformers torch torchaudio)
                       Falls back to heuristic when packages are absent
                       or a non-audio string is given.

Both share the same EmotionDetector public interface.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from packages.common import logger

from .models import EmotionDetectionResult


# Emotions the pipeline understands.
EMOTIONS = ["neutral", "excited", "calm", "stressed", "sad", "angry", "happy", "fearful", "surprised"]


# ---------------------------------------------------------------------------
# Heuristic detector (text keywords, always available)
# ---------------------------------------------------------------------------

class EmotionDetector:
    BACKEND = "heuristic"

    def detect(self, text: str) -> EmotionDetectionResult:
        normalized = (text or "").lower()

        if any(w in normalized for w in ["urgent", "asap", "hurry", "immediately", "emergency"]):
            return EmotionDetectionResult(emotion="stressed", confidence=0.82, backend=self.BACKEND)
        if "!" in text or any(w in normalized for w in ["awesome", "great", "amazing", "excited", "fantastic", "love it"]):
            return EmotionDetectionResult(emotion="excited", confidence=0.84, backend=self.BACKEND)
        if any(w in normalized for w in ["calm", "relax", "slowly", "gently", "no rush", "take your time"]):
            return EmotionDetectionResult(emotion="calm", confidence=0.76, backend=self.BACKEND)
        if any(w in normalized for w in ["happy", "glad", "pleased", "wonderful"]):
            return EmotionDetectionResult(emotion="happy", confidence=0.78, backend=self.BACKEND)
        if any(w in normalized for w in ["sad", "depressed", "unhappy", "miserable"]):
            return EmotionDetectionResult(emotion="sad", confidence=0.78, backend=self.BACKEND)
        if any(w in normalized for w in ["angry", "furious", "frustrated", "annoyed", "upset"]):
            return EmotionDetectionResult(emotion="angry", confidence=0.78, backend=self.BACKEND)
        if any(w in normalized for w in ["scared", "afraid", "fearful", "terrified", "nervous"]):
            return EmotionDetectionResult(emotion="fearful", confidence=0.76, backend=self.BACKEND)
        if any(w in normalized for w in ["surprised", "shocked", "wow", "unbelievable", "no way"]):
            return EmotionDetectionResult(emotion="surprised", confidence=0.74, backend=self.BACKEND)

        return EmotionDetectionResult(emotion="neutral", confidence=0.55, backend=self.BACKEND)


# ---------------------------------------------------------------------------
# wav2vec2 / transformers emotion detector (real audio classification)
# ---------------------------------------------------------------------------

class Wav2Vec2EmotionDetector(EmotionDetector):
    """
    Emotion classification from audio via a fine-tuned wav2vec2 model.

    For audio file input: runs HuggingFace transformers pipeline
    (audio-classification) with a speech-emotion-recognition model.

    For text input: falls through to the heuristic detector.

    Safe degradation: when transformers/torch are absent or the model
    fails to load, the class falls back to keyword heuristic and logs
    a one-time warning.

    Default model: "ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition"
    Override via EMOTION_MODEL_NAME in settings.
    """

    BACKEND = "wav2vec2-emotion"
    _pipeline = None
    _available: Optional[bool] = None

    # Map model label outputs → NOVA emotion vocabulary.
    LABEL_MAP: dict[str, str] = {
        "angry": "angry",
        "anger": "angry",
        "disgust": "angry",
        "fear": "fearful",
        "fearful": "fearful",
        "happy": "happy",
        "happiness": "happy",
        "joy": "excited",
        "neutral": "neutral",
        "sad": "sad",
        "sadness": "sad",
        "surprise": "surprised",
        "surprised": "surprised",
        "calm": "calm",
        "excited": "excited",
        "ps": "surprised",   # "pleasant surprise" label in some models
        "boredom": "calm",
    }

    def __init__(
        self,
        model_name: str = "ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition",
        sampling_rate: int = 16000,
    ):
        self.model_name = model_name
        self.sampling_rate = sampling_rate
        self._heuristic = EmotionDetector()

    def detect(self, source: str) -> EmotionDetectionResult:
        """
        Detect emotion.

        If `source` is a path to an audio file and transformers are available,
        runs real audio classification.  Otherwise falls through to heuristic.
        """
        if source and Path(source).exists():
            return self._detect_audio(source)

        result = self._heuristic.detect(source)
        return EmotionDetectionResult(
            emotion=result.emotion,
            confidence=result.confidence,
            backend=f"wav2vec2/heuristic",
        )

    def _detect_audio(self, audio_path: str) -> EmotionDetectionResult:
        if not self._ensure_available():
            logger.warning(
                "Wav2Vec2EmotionDetector: transformers/torch not installed — "
                "falling back to heuristic. "
                "Run: pip install transformers torch torchaudio"
            )
            return EmotionDetectionResult(emotion="neutral", confidence=0.5, backend="wav2vec2/fallback")

        try:
            return self._run_pipeline(audio_path)
        except Exception as ex:
            logger.error(f"Wav2Vec2EmotionDetector failed: {ex}")
            return EmotionDetectionResult(emotion="neutral", confidence=0.5, backend="wav2vec2/error")

    def _run_pipeline(self, audio_path: str) -> EmotionDetectionResult:
        pipe = self._get_pipeline()
        results = pipe(audio_path)
        if not results:
            return EmotionDetectionResult(emotion="neutral", confidence=0.5, backend=self.BACKEND)

        # Pick highest score.
        top = max(results, key=lambda r: r["score"])
        raw_label = top["label"].lower().strip()
        emotion = self.LABEL_MAP.get(raw_label, "neutral")
        return EmotionDetectionResult(emotion=emotion, confidence=round(top["score"], 3), backend=self.BACKEND)

    def _ensure_available(self) -> bool:
        if self.__class__._available is not None:
            return self.__class__._available
        try:
            import transformers  # noqa: F401
            import torch  # noqa: F401
            self.__class__._available = True
        except ImportError:
            self.__class__._available = False
        return self.__class__._available

    def _get_pipeline(self):
        if self.__class__._pipeline is not None:
            return self.__class__._pipeline

        from transformers import pipeline as hf_pipeline

        logger.info(f"Wav2Vec2EmotionDetector: loading model {self.model_name}")
        pipe = hf_pipeline(
            "audio-classification",
            model=self.model_name,
            return_all_scores=True,
        )
        self.__class__._pipeline = pipe
        return pipe
