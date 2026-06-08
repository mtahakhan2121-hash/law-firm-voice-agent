"""
Law Firm Voice Agent — entry point.

Run modes:
    python main.py                          # live mic
    python main.py --file demo_audio/x.wav  # audio file input (single turn)
    python main.py --text "Hello there"     # typed text (good for quick testing)
    python main.py --chat                   # multi-turn typed chat (no mic needed)
"""

import argparse
import os
import sys
import threading
import time

from pipeline.audio import capture_from_mic, load_audio_file
from pipeline.stt import transcribe, is_no_speech, has_uncertain_words
from pipeline.tts import speak, speak_filler
from pipeline.confidence import build_confidence_signal
from pipeline.latency import LatencyTracker
from agent.session import SessionState
from agent.agent import respond
from agent.handoff import build_handoff_summary

# LLM calls that take longer than this will be preceded by a filler phrase
FILLER_THRESHOLD_S = 1.5


def log(label: str, value: str = "", ms: float | None = None) -> None:
    if ms is not None:
        print(f"  [{label}] {value}{ms:.0f}ms")
    else:
        print(f"  [{label}] {value}")


def respond_with_filler(message: str, session: SessionState) -> tuple[str, float]:
    """
    Run the LLM in a background thread. If it hasn't responded within
    FILLER_THRESHOLD_S seconds, play a short filler phrase to prevent
    dead air — then wait for the real reply.
    """
    result: dict = {}

    def _run():
        reply, ms = respond(message, session)
        result["reply"] = reply
        result["ms"] = ms

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=FILLER_THRESHOLD_S)

    if t.is_alive():
        speak_filler()
        t.join()

    return result["reply"], result["ms"]


def run_call(audio_file: str | None = None, text_input: str | None = None, single_turn: bool = False) -> None:
    session = SessionState()
    tracker = LatencyTracker()

    print("\n=== Law Firm Voice Agent ===")
    if text_input:
        print("Mode: text input  |  Say 'quit' to stop\n")
    elif audio_file:
        print(f"Mode: audio file ({audio_file})\n")
    else:
        print("Mode: live mic  |  Say 'quit' or 'exit' to stop\n")

    # Opening greeting (no user input — agent speaks first)
    greeting, llm_ms = respond("[CALL_START]", session)
    log("llm", ms=llm_ms)
    print(f"  [agent] \"{greeting}\"\n")
    speak(greeting)

    turn = 0

    while not session.transferred and not session.booking_confirmed:
        turn += 1
        print(f"--- Turn {turn} ---")

        # ── 1. Get user input ─────────────────────────────────────────────
        if text_input == "__interactive__":
            transcript_text = input("  [you] ").strip()
            if not transcript_text:
                continue
            stt_ms = 0.0
            result = None
        elif text_input:
            transcript_text = text_input
            stt_ms = 0.0
            result = None
            print(f"  [text] {transcript_text}")
        elif audio_file:
            audio = load_audio_file(audio_file)
            result = transcribe(audio)
            log("stt", ms=result.elapsed_ms)
            if is_no_speech(result):
                print("  [stt] no speech in file")
                break
            transcript_text = result.transcript
            stt_ms = result.elapsed_ms
            audio_file = None
        else:
            audio = capture_from_mic()
            result = transcribe(audio)
            log("stt", f"{result.audio_duration_s:.1f}s audio — ", result.elapsed_ms)
            stt_ms = result.elapsed_ms

            if is_no_speech(result):
                speak("Sorry, I didn't catch that. Could you say that again?")
                continue

            transcript_text = result.transcript

        conf_info = ""
        if result and has_uncertain_words(result):
            conf_info = f" (uncertain: {', '.join(result.uncertain_words)})"
        print(f"  [caller] \"{transcript_text}\"{conf_info}")

        # ── 2. Exit commands ──────────────────────────────────────────────
        if transcript_text.strip().lower() in ("quit", "exit", "stop"):
            speak("Thank you for calling Carter and Mills Solicitors. Goodbye.")
            break

        # ── 3. Build message with optional STT confidence signal ──────────
        if text_input:
            message_to_agent = transcript_text
        else:
            signal = build_confidence_signal(result)
            message_to_agent = signal + transcript_text
            if signal:
                log("confidence", "signal injected — uncertain words flagged to agent")

        # ── 4. LLM (with filler audio if slow) ───────────────────────────
        reply, llm_ms = respond_with_filler(message_to_agent, session)
        log("llm", ms=llm_ms)
        print(f"  [agent] \"{reply}\"")

        # ── 5. Speak the response ─────────────────────────────────────────
        tts_ms = speak(reply)
        log("tts", ms=tts_ms)

        total_ms = (stt_ms or 0) + llm_ms + tts_ms
        print(f"  [latency] STT: {stt_ms:.0f}ms | LLM: {llm_ms:.0f}ms | TTS: {tts_ms:.0f}ms | Total: {total_ms:.0f}ms\n")

        tracker.record(turn, stt_ms, llm_ms, tts_ms)

        if single_turn:
            break

    # ── End-of-call summary ───────────────────────────────────────────────
    print("\n=== Call ended ===")
    if session.booking_confirmed:
        print(f"  Booking ref : {session.booking_reference}")
        print(f"  Name        : {session.collected.name}")
        print(f"  Email       : {session.collected.email}")
        print(f"  Phone       : {session.collected.phone}")
        print(f"  Slot        : {session.collected.preferred_slot}")
        print(f"  Law area    : {session.law_area or 'not identified'}")
        print(f"  Turns       : {turn}")
    elif session.transferred:
        print(build_handoff_summary(session))

    tracker.print_summary()


def main() -> None:
    parser = argparse.ArgumentParser(description="Law Firm Voice Agent")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--file", metavar="PATH", help="Audio file to use as input")
    group.add_argument("--text", metavar="TEXT", help="Single typed turn instead of mic")
    group.add_argument("--chat", action="store_true", help="Multi-turn typed chat (no mic needed)")
    args = parser.parse_args()

    try:
        run_call(
            audio_file=args.file,
            text_input="__interactive__" if args.chat else args.text,
            single_turn=bool(args.text),
        )
    except KeyboardInterrupt:
        print("\n[interrupted]")
        sys.exit(0)


if __name__ == "__main__":
    main()
