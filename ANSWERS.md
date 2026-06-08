# Assessment Written Questions

---

## Q1 — Latency and pipeline design

**How did you approach minimising latency, and what further changes would you make if this needed to work in production at scale?**

### What was implemented

The pipeline runs three sequential stages per turn: STT → LLM → TTS. The main levers were:

1. **Model selection.** Whisper `base` (not `large`) and `gpt-4o-mini` (not GPT-4o or GPT-4) were chosen because they are meaningfully faster for this task with acceptable accuracy. A caller's utterance is a short sentence, not a document — a 74M-parameter STT model handles it well.

2. **Local STT.** Running `faster-whisper` locally eliminates one round-trip to a cloud STT service. Observed STT latency: 600–700 ms for a 3-second utterance on CPU. On a GPU instance this drops below 200 ms.

3. **Filler audio on slow LLM turns.** The LLM call runs in a background thread. If it has not returned within 1.5 seconds, a short phrase ("One moment please") is played through TTS. This prevents dead air without changing the actual latency — it just hides it perceptually. Implemented in `main.py:respond_with_filler()`.

4. **Short max tokens.** `max_tokens=300` prevents the model from generating verbose responses that then take longer to synthesise and speak.

5. **Low temperature.** `temperature=0.3` produces more consistent, shorter responses — the model is less likely to write a monologue.

Observed total per-turn latency: typically 1.7–2.5 seconds.

### What production would require

- **Streaming TTS.** Piper's `synthesize()` already returns a generator of chunks. A production implementation would pipe each chunk to the audio output as soon as it arrives rather than waiting for the full audio array. This cuts perceived TTS latency from ~400 ms to the time it takes to generate the first 50–100 ms of audio.
- **Streaming LLM output.** OpenAI supports token streaming. Combined with streaming TTS, the agent could start speaking its first words before it has even generated the last sentence of its reply — cutting total time-to-first-audio from 1.5+ s to under 500 ms.
- **Managed STT.** AssemblyAI, Deepgram, or Google Speech-to-Text return results in 200–400 ms via WebSocket, with no server to maintain. Worth the round-trip if the deployment environment lacks a GPU.
- **Response caching.** The greeting, slot-full message, and transfer acknowledgement are deterministic. Pre-generating their audio removes TTS latency for the most common agent turns.
- **End-of-speech detection tuning.** The current VAD uses a fixed RMS threshold and a 0.8-second silence window. In production, this needs per-caller calibration (ambient noise varies significantly between phone lines, headsets, and speakerphones) and likely a learned model like Silero VAD.

---

## Q2 — Turn-taking and interruptions

**How does the system decide when the caller has finished speaking, and how would you handle barge-in (caller interrupting the agent)?**

### Current approach

End-of-utterance detection is purely energy-based (see `pipeline/audio.py`):

1. Audio is captured in 30 ms chunks via `sounddevice`.
2. Each chunk's RMS amplitude is computed and normalised to a 0–1 scale.
3. When the RMS falls below `SILENCE_THRESHOLD_RMS = 0.015` for `SILENCE_DURATION_S = 0.8` consecutive seconds, the utterance is considered complete.
4. A hard `MAX_RECORDING_S = 30` cap prevents runaway captures.

The threshold was calibrated against real ambient RMS values (silence floor: 0.003–0.009; voice: 0.03–0.10) rather than guessing.

### Problems with this approach

- **Natural pauses inside an utterance.** A caller who says "I was dismissed — well, let me explain from the beginning" will trigger end-of-utterance at the pause. The 0.8 s window partially mitigates this but does not eliminate it.
- **Noisy environments.** Consistent background noise above 0.015 means silence is never detected and the recording runs to the 30-second cap.
- **No barge-in.** The current loop plays TTS synchronously (`sd.wait()` blocks until audio finishes). The caller cannot interrupt. If they speak during playback their audio is discarded.

### How barge-in would work in production

Barge-in requires the TTS playback and mic capture to run concurrently:

1. TTS audio is played in a non-blocking thread.
2. A lightweight VAD (e.g. Silero VAD, which runs at < 5 ms per 30 ms chunk) monitors the mic in parallel.
3. When the VAD detects voice above a threshold, the TTS thread is signalled to stop and the capture pipeline starts immediately.
4. The partial agent utterance is discarded and a new STT → LLM → TTS cycle begins.

A delay of 200–400 ms after the TTS ends is preserved before VAD starts listening — this prevents the agent's own voice from triggering a false barge-in. On a phone system this is simpler because the mic and speaker are on separate audio channels.

---

## Q3 — Iteration and scaling

**How would you test and iterate on this in a real team environment, and what would need to change to go from prototype to production?**

### Testing strategy

- **Unit tests for each pipeline stage.** STT is tested against short known utterances; the expected transcript and confidence distribution are asserted. LLM tool dispatch is tested with mock OpenAI responses. Booking DB operations are tested with a fresh in-memory SQLite instance per test.
- **Scenario regression tests.** The three `test_phase*.py` scripts in this repo are the seed of a scenario regression suite. Each scenario is a list of caller turn texts and the expected outcome (booking confirmed, transferred, etc.). New failure modes found in production are added as regression scenarios.
- **Prompt evaluation.** LLM prompts degrade as edge cases accumulate. A prompt evaluation harness runs the full scenario suite after any prompt change and compares pass/fail against the baseline. A prompt change that breaks an existing scenario is blocked from merging.
- **Call recording review.** In production, a random sample of calls (with consent) is reviewed weekly. Reviewers annotate the calls with the first turn where the agent's response was suboptimal. These turns become new training scenarios.

### What production requires

| Area | Change required |
|---|---|
| **State management** | Session state is currently in-memory per process. For concurrent calls across multiple workers, state must move to Redis or a managed session store. Session ID is passed on every request. |
| **Telephony integration** | Replace `sounddevice` with a SIP/WebRTC adapter (Twilio, Vonage, or Signalwire). The media stream comes in as µ-law or OPUS; it needs to be decoded to 16 kHz PCM before Whisper. |
| **Streaming pipeline** | LLM output and TTS synthesis must stream concurrently to hit < 1 s time-to-first-audio. The current synchronous pipeline cannot achieve this. |
| **Observability** | Each turn's STT/LLM/TTS latency, tool calls, and escalation events should be logged to a structured sink (Datadog, Grafana). Alert on P95 total latency > 3 s or escalation rate > 15%. |
| **A/B prompt testing** | Wrap the system prompt in a feature-flag layer. Run two variants concurrently on real traffic and compare booking rate, escalation rate, and average turns to resolution. |
| **Model upgrades** | `gpt-4o-mini` will be superseded. The LLM interface is already decoupled from the rest of the pipeline (only `agent.py` touches it), so swapping models requires changing one constant in `config.py` and re-running the scenario suite. |
| **Safety and compliance** | Callers may share sensitive personal details (medical, legal, financial). All call recordings and transcripts must be encrypted at rest, access-controlled, and subject to a retention policy (GDPR in the UK). The agent must not log or store PII beyond the session lifetime. |
| **Fallback and error handling** | If OpenAI is unavailable, the agent should fail gracefully ("I'm sorry, we're having a technical difficulty — let me connect you to a member of staff") rather than hanging silently. |
