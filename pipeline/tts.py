"""
Text-to-speech using piper-tts.

Converts agent text responses to audio and plays them through
the default output device (or saves to file for demos).
"""

import os
import time
import sys

import numpy as np
import sounddevice as sd
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import PIPER_MODEL, PIPER_VOICE_DIR


# Module-level voice — loaded once on first use
_voice = None
_sample_rate = None


def _get_voice():
    global _voice, _sample_rate
    if _voice is None:
        from piper.voice import PiperVoice
        model_path = os.path.join(PIPER_VOICE_DIR, f"{PIPER_MODEL}.onnx")
        config_path = os.path.join(PIPER_VOICE_DIR, f"{PIPER_MODEL}.onnx.json")

        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Piper voice model not found at {model_path}\n"
                f"Run: python -m piper.download_voices {PIPER_MODEL} --download-dir {PIPER_VOICE_DIR}"
            )

        print(f"  [tts] loading piper voice '{PIPER_MODEL}'...", flush=True)
        _voice = PiperVoice.load(model_path, config_path=config_path)
        _sample_rate = _voice.config.sample_rate
        print(f"  [tts] voice ready (sample rate: {_sample_rate}Hz)")
    return _voice, _sample_rate


def speak(text: str, save_path: str | None = None) -> float:
    """
    Synthesise text and play it through speakers.
    Optionally save the audio to a WAV file at save_path.
    Returns synthesis time in milliseconds.
    """
    if not text.strip():
        return 0.0

    voice, sample_rate = _get_voice()

    t0 = time.monotonic()

    # Collect all audio chunks from the generator
    all_audio: list[np.ndarray] = []
    for chunk in voice.synthesize(text):
        all_audio.append(chunk.audio_float_array)

    elapsed_ms = (time.monotonic() - t0) * 1000

    if not all_audio:
        return elapsed_ms

    audio = np.concatenate(all_audio).astype(np.float32)

    if save_path:
        sf.write(save_path, audio, sample_rate)

    sd.play(audio, samplerate=sample_rate)
    sd.wait()

    return elapsed_ms


def speak_filler() -> None:
    """Play a short acknowledgement while LLM is thinking to prevent dead air."""
    speak("One moment please.")
