"""
Speech-to-text using faster-whisper.

Returns transcript, average confidence, and per-word uncertain flags
so the agent layer can decide when to re-prompt the caller.
"""

import time
from dataclasses import dataclass

import numpy as np

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import (
    WHISPER_MODEL_SIZE, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE,
    CONFIDENCE_THRESHOLD, SAMPLE_RATE,
)


@dataclass
class TranscriptionResult:
    transcript: str
    avg_confidence: float
    uncertain_words: list[str]   # words with confidence < CONFIDENCE_THRESHOLD
    audio_duration_s: float      # length of audio sent to whisper
    elapsed_ms: float            # transcription time


# Module-level model — loaded once on first use
_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        print(f"  [stt] loading whisper '{WHISPER_MODEL_SIZE}' model...", flush=True)
        _model = WhisperModel(
            WHISPER_MODEL_SIZE,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
        )
        print("  [stt] model ready")
    return _model


def transcribe(audio: np.ndarray) -> TranscriptionResult:
    """
    Transcribe int16 PCM audio to text.

    Returns TranscriptionResult with transcript, confidence details, and timing.
    """
    model = _get_model()

    audio_duration_s = len(audio) / SAMPLE_RATE

    # faster-whisper expects float32 normalised to [-1, 1]
    float_audio = audio.astype(np.float32) / 32767.0

    t0 = time.monotonic()
    segments, info = model.transcribe(
        float_audio,
        language="en",
        beam_size=5,
        word_timestamps=True,
        vad_filter=False,   # we do our own VAD at capture time
    )

    # Materialise the lazy generator before measuring elapsed time
    all_words = []
    full_text_parts = []
    for segment in segments:
        full_text_parts.append(segment.text.strip())
        if segment.words:
            all_words.extend(segment.words)

    elapsed_ms = (time.monotonic() - t0) * 1000
    transcript = " ".join(full_text_parts).strip()

    if all_words:
        confidences = [w.probability for w in all_words]
        avg_confidence = float(np.mean(confidences))
        uncertain_words = [w.word.strip() for w in all_words if w.probability < CONFIDENCE_THRESHOLD]
    else:
        avg_confidence = 0.0
        uncertain_words = []

    return TranscriptionResult(
        transcript=transcript,
        avg_confidence=avg_confidence,
        uncertain_words=uncertain_words,
        audio_duration_s=audio_duration_s,
        elapsed_ms=elapsed_ms,
    )


def is_no_speech(result: TranscriptionResult) -> bool:
    """True if whisper returned nothing useful."""
    return not result.transcript.strip()


def has_uncertain_words(result: TranscriptionResult) -> bool:
    return len(result.uncertain_words) > 0
