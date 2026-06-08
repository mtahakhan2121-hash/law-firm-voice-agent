"""
Audio capture and playback.

Two input modes:
  - mic: live capture with VAD-based endpointing
  - file: read a pre-recorded WAV/MP3 for demo/testing
"""

import time
import numpy as np
import sounddevice as sd
import soundfile as sf

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import (
    SAMPLE_RATE, CHANNELS, CHUNK_DURATION_MS,
    SILENCE_THRESHOLD_RMS, SILENCE_DURATION_S, MAX_RECORDING_S,
)


def _rms(chunk: np.ndarray) -> float:
    # Normalize int16 → float32 before computing RMS so the result is 0.0–1.0
    normalized = chunk.astype(np.float32) / 32767.0
    return float(np.sqrt(np.mean(normalized ** 2)))


def capture_from_mic() -> np.ndarray:
    """
    Record from mic until the caller stops speaking.

    Waits for speech to begin, then records until SILENCE_DURATION_S
    of continuous silence is detected. Returns raw int16 PCM array.
    """
    chunk_samples = int(SAMPLE_RATE * CHUNK_DURATION_MS / 1000)
    silence_chunks_needed = int(SILENCE_DURATION_S * 1000 / CHUNK_DURATION_MS)
    max_chunks = int(MAX_RECORDING_S * 1000 / CHUNK_DURATION_MS)

    frames: list[np.ndarray] = []
    silent_chunks = 0
    total_chunks = 0
    speaking = False

    print("  [mic] listening...", end="", flush=True)

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16") as stream:
        while total_chunks < max_chunks:
            chunk, _ = stream.read(chunk_samples)
            total_chunks += 1
            rms = _rms(chunk)

            if rms > SILENCE_THRESHOLD_RMS:
                if not speaking:
                    print(" [capturing]", end="", flush=True)
                    speaking = True
                silent_chunks = 0
                frames.append(chunk.copy())
            else:
                if speaking:
                    frames.append(chunk.copy())
                    silent_chunks += 1
                    if silent_chunks >= silence_chunks_needed:
                        break
                # if not speaking yet, keep waiting

    print()

    if not frames:
        return np.zeros(chunk_samples, dtype=np.int16)

    return np.concatenate(frames, axis=0).flatten()


def load_audio_file(path: str) -> np.ndarray:
    """Load a WAV/FLAC/MP3 file and resample to SAMPLE_RATE mono int16."""
    data, sr = sf.read(path, dtype="float32", always_2d=False)

    # Mix down to mono if stereo
    if data.ndim > 1:
        data = data.mean(axis=1)

    # Resample if needed (simple linear — good enough for demos)
    if sr != SAMPLE_RATE:
        factor = SAMPLE_RATE / sr
        new_len = int(len(data) * factor)
        indices = np.linspace(0, len(data) - 1, new_len)
        data = np.interp(indices, np.arange(len(data)), data)

    # Convert to int16
    data = np.clip(data, -1.0, 1.0)
    return (data * 32767).astype(np.int16)


def play_audio(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> None:
    """Play a numpy int16 PCM array through the default output device."""
    float_audio = audio.astype(np.float32) / 32767.0
    sd.play(float_audio, samplerate=sample_rate)
    sd.wait()


def play_audio_file(path: str) -> None:
    """Play a WAV/FLAC file directly."""
    data, sr = sf.read(path, dtype="float32")
    sd.play(data, samplerate=sr)
    sd.wait()


def save_audio(audio: np.ndarray, path: str, sample_rate: int = SAMPLE_RATE) -> None:
    """Save int16 PCM array to a WAV file."""
    sf.write(path, audio, sample_rate, subtype="PCM_16")
