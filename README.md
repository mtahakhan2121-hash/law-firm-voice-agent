# Law Firm Voice Agent

A voice AI prototype for Carter & Mills Solicitors. Handles inbound calls end-to-end:
microphone → Whisper STT → GPT-4o-mini (with tool use) → Piper TTS → speaker.

---

## What it does

| Requirement | Implementation |
|---|---|
| Route across ≥ 2 law areas | Routes to employment, tenancy, family, or personal injury using a `route_to_law_area` tool call |
| Book consultations | SQLite calendar; fuzzy natural-language slot matching; handles unavailable slots by offering alternatives |
| Low-confidence STT path | Word-level Whisper confidence scores; injects `[STT NOTE:]` signal; agent confirms field-by-field |
| Human handoff | 4 triggers: explicit request, out-of-scope, urgent/emergency, clarification failure (3 strikes) |
| Filler audio | If LLM takes > 1.5 s, plays "One moment please." in a background thread before the real reply |

---

## Setup

### Prerequisites

- Python 3.11 (not 3.12+ — onnxruntime has no wheel for 3.14)
- `brew install ffmpeg pkg-config` (macOS, required for audio I/O)
- An OpenAI API key

### 1 — Create a virtual environment

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

### 2 — Install dependencies

```bash
pip install faster-whisper piper-tts sounddevice soundfile numpy openai
pip install av --no-build-isolation
```

### 3 — Download the Piper voice model

```bash
mkdir -p voices
python -c "
from piper.download import ensure_voice_exists, find_voice, get_voices
import json, pathlib
info = get_voices(pathlib.Path('voices'), update_voices=True)
ensure_voice_exists('en_US-lessac-medium', [pathlib.Path('voices')], pathlib.Path('voices'), info)
"
```

The model files (`en_US-lessac-medium.onnx` and `.onnx.json`) will appear in `voices/`.

### 4 — Add your OpenAI API key

Create a `.env` file in the project root:

```
OPENAI_API_KEY=sk-proj-...
```

The app reads this automatically via `config.py`. Never commit this file.

### 5 — Initialise the booking database

The database is created automatically on first run. To pre-seed with demo slots:

```bash
python -c "from booking.db import init_db, seed_slots; init_db(); seed_slots()"
```

---

## Running the agent

### Live microphone (primary mode)

```bash
python main.py
```

Speak when you see `--- Turn N ---`. Say "quit" or "exit" to end the call.

### Typed chat (no mic needed — good for testing)

```bash
python main.py --chat
```

### Single typed turn (for scripted testing)

```bash
python main.py --text "I was dismissed from my job last month"
```

### Audio file input (for video demo)

```bash
python main.py --file demo_audio/scenario_a_employment_booking_turn01.wav
```

---

## Demo audio files

Pre-synthesised WAV files let you record the demo without relying on mic conditions.

Generate them once:

```bash
python demo_audio/generate_demo.py
```

Three scenarios are generated:

| Scenario | Files | What it tests |
|---|---|---|
| `scenario_a_employment_booking` | turns 01–09 | Full happy path: routing + booking |
| `scenario_b_stt_confidence` | turns 01–09 | Low-confidence STT confirmation flow |
| `scenario_c_emergency_transfer` | turns 01–03 | Emergency / urgent → human handoff |

---

## Running tests

```bash
# All phases together
python test_phase3.py   # booking and slot handling
python test_phase4.py   # low-confidence STT detail capture
python test_phase5.py   # all 4 escalation triggers
```

---

## Architecture

```
main.py
  │
  ├─ pipeline/audio.py     mic capture (VAD, RMS threshold), file loading, playback
  ├─ pipeline/stt.py       faster-whisper wrapper → TranscriptionResult with word confidence
  ├─ pipeline/confidence.py  word probability → [STT NOTE:] signal injected into LLM message
  ├─ pipeline/tts.py       Piper voice synthesis → sounddevice playback (or WAV save)
  ├─ pipeline/latency.py   per-turn STT/LLM/TTS timing + end-of-call summary
  │
  ├─ agent/session.py      in-memory call state (history, collected details, clarification counts)
  ├─ agent/prompts.py      system prompt + law-area question banks
  ├─ agent/tools.py        OpenAI tool schemas + executor (route, check_slot, book, transfer)
  ├─ agent/agent.py        OpenAI chat loop with tool dispatch, filler threading, safety nets
  ├─ agent/handoff.py      structured handoff summary printed on transfer
  │
  ├─ booking/db.py         SQLite calendar — slot availability, fuzzy matching, create booking
  └─ config.py             all constants + .env loader
```

---

## Configuration

All tuneable values live in `config.py`:

| Key | Default | Purpose |
|---|---|---|
| `WHISPER_MODEL_SIZE` | `base` | STT model size (larger = slower + more accurate) |
| `CONFIDENCE_THRESHOLD` | `0.75` | Below this → word is flagged as uncertain |
| `SILENCE_THRESHOLD_RMS` | `0.015` | Normalised RMS above this → voice activity |
| `SILENCE_DURATION_S` | `0.8` | Seconds of silence before end-of-utterance |
| `OPENAI_MODEL` | `gpt-4o-mini` | LLM for all agent turns |
| `MAX_HISTORY_TURNS` | `20` | Conversation history window |

---

## Latency profile

Typical observed per-turn latency (MacBook M-series, CPU inference):

| Stage | Typical | Budget |
|---|---|---|
| STT (Whisper base, ~3s audio) | 600–700 ms | < 800 ms |
| LLM (gpt-4o-mini) | 1 000–2 000 ms | < 1 500 ms |
| TTS (Piper, ~20 words) | 60–400 ms | < 500 ms |
| **Total** | **~1.7–3.1 s** | **< 2 500 ms** |

Filler audio fires at 1.5 s to prevent dead air on slower LLM turns.
