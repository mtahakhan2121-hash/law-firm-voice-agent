import os

# Load .env if present (so you don't need to export keys every session)
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

# STT
WHISPER_MODEL_SIZE = "base"
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE_TYPE = "int8"
CONFIDENCE_THRESHOLD = 0.75      # below this, word is flagged as uncertain
NO_SPEECH_THRESHOLD = 0.6        # above this, treat as silence/noise

# VAD / audio capture
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_DURATION_MS = 30           # ms per audio chunk during recording
SILENCE_THRESHOLD_RMS = 0.015    # RMS energy below this = silence (normalized 0.0–1.0 scale)
SILENCE_DURATION_S = 0.8         # seconds of silence before end-of-turn
MAX_RECORDING_S = 30             # hard stop — prevents infinite capture on noisy lines

# TTS
PIPER_MODEL = "en_US-lessac-medium"
PIPER_VOICE_DIR = os.path.join(os.path.dirname(__file__), "voices")

# LLM
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = "gpt-4o-mini"     # swap to "gpt-4o" for higher quality
MAX_HISTORY_TURNS = 20

# Paths
AUDIO_DEMO_DIR = os.path.join(os.path.dirname(__file__), "demo_audio")
DB_PATH = os.path.join(os.path.dirname(__file__), "booking.db")
