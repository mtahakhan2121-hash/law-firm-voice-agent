"""
Mic calibration tool — run this to find the right SILENCE_THRESHOLD_RMS for your environment.

Usage: python calibrate.py

Prints RMS energy readings from your mic in real time.
Stay silent for a few seconds to see your ambient noise floor,
then speak to see your speech level.

Set SILENCE_THRESHOLD_RMS in config.py to a value clearly
above the ambient floor but well below your speech level.
"""

import sys
import time
import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
CHUNK_DURATION_MS = 100


def rms(chunk: np.ndarray) -> float:
    normalized = chunk.astype(np.float32) / 32767.0
    return float(np.sqrt(np.mean(normalized ** 2)))


def main():
    chunk_samples = int(SAMPLE_RATE * CHUNK_DURATION_MS / 1000)
    print("Mic calibration — measuring RMS energy every 100ms.")
    print("Stay silent for 5s, then speak normally.\n")
    print(f"{'Time':>6}  {'RMS':>8}  {'Level'}")
    print("-" * 40)

    start = time.monotonic()

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as stream:
        try:
            while True:
                chunk, _ = stream.read(chunk_samples)
                r = rms(chunk)
                elapsed = time.monotonic() - start
                bar = "█" * int(r * 1000)
                marker = " ← SPEECH" if r > 0.015 else " ← ambient noise"
                print(f"{elapsed:>6.1f}s  {r:>8.4f}  {bar[:40]}{marker}")
        except KeyboardInterrupt:
            print("\nDone. Set SILENCE_THRESHOLD_RMS in config.py to a value")
            print("clearly above your silent noise floor but below your speech level.")


if __name__ == "__main__":
    main()
