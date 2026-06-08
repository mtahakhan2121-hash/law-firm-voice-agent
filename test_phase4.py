"""
Phase 4 test — confidence handling and detail capture under uncertainty.

Scenario A: Low-confidence name — agent spells it back, caller corrects it
Scenario B: Low-confidence email — agent reads it character by character
Scenario C: Repeated failure — agent escalates to human after 3 failed clarifications

Run: python test_phase4.py
"""

import os, sys
sys.path.insert(0, ".")

from agent.session import SessionState
from agent.agent import respond
from pipeline.confidence import build_confidence_signal
from pipeline.stt import TranscriptionResult


def reset_db():
    from config import DB_PATH
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    from booking.db import init_db, seed_slots
    init_db()
    seed_slots()


def fake_stt(transcript: str, uncertain_words: list[str] = None) -> TranscriptionResult:
    """Simulate an STT result with optional uncertain words for testing."""
    uncertain = uncertain_words or []
    avg_conf = 0.45 if uncertain else 0.95
    return TranscriptionResult(
        transcript=transcript,
        avg_confidence=avg_conf,
        uncertain_words=uncertain,
        audio_duration_s=2.0,
        elapsed_ms=600.0,
    )


def run_scenario(title: str, turns: list) -> SessionState:
    """
    turns: list of either:
      - str: plain text (no STT signal)
      - (str, list[str]): transcript + uncertain words (STT signal injected)
    """
    reset_db()
    session = SessionState()

    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

    reply, _ = respond("[CALL_START]", session)
    print(f"\n[agent] {reply}")

    for turn in turns:
        if isinstance(turn, tuple):
            transcript, uncertain_words = turn
            result = fake_stt(transcript, uncertain_words)
            signal = build_confidence_signal(result)
            message = signal + transcript
            conf_tag = f" [STT uncertain: {uncertain_words}]" if uncertain_words else ""
        else:
            transcript = turn
            message = transcript
            conf_tag = ""

        print(f"\n[caller] {transcript}{conf_tag}")
        if conf_tag:
            print(f"         → injecting signal to agent: {message[:80]}...")

        reply, ms = respond(message, session)

        # Show clarification counts if any
        if session.clarification_counts:
            counts = ", ".join(f"{k}={v}" for k, v in session.clarification_counts.items())
            print(f"  [clarification counts] {counts}")

        print(f"[agent]  {reply}  ({ms:.0f}ms)")

        if session.transferred or session.booking_confirmed:
            break

    print(f"\n--- Result ---")
    if session.booking_confirmed:
        print(f"  BOOKING CONFIRMED  ref={session.booking_reference}")
        print(f"  Name : {session.collected.name}")
        print(f"  Email: {session.collected.email}")
        print(f"  Phone: {session.collected.phone}")
    elif session.transferred:
        print(f"  TRANSFERRED — {session.transfer_reason}")
    else:
        print(f"  Ended — clarification counts: {session.clarification_counts}")

    return session


# ── Scenario A: Low-confidence name ──────────────────────────────────────────
# Caller says "Musa Amperr" but whisper is uncertain about "Amperr"
# Agent should spell it back; caller corrects to "Ampero"
scenario_a = run_scenario(
    "SCENARIO A — Low-confidence name: caller corrects the spelling",
    [
        "I need to book a consultation about an employment matter",
        "I was made redundant last week without proper notice",
        "Yes I would like to book a consultation",
        ("My name is Musa Amperr", ["Amperr"]),          # uncertain surname
        "No it is Ampero, A-M-P-E-R-O",                  # caller corrects
        "musa@amperortech.com",
        "07700900123",
        "Wednesday at 2pm please",
        "Yes that is all correct",
    ]
)


# ── Scenario B: Low-confidence email ─────────────────────────────────────────
# Whisper mishears the email domain
scenario_b = run_scenario(
    "SCENARIO B — Low-confidence email: agent confirms character by character",
    [
        "I need help with a tenancy dispute, my landlord evicted me illegally",
        "I am the tenant, private rental, no court proceedings",
        "Yes please book me in",
        "David Chen",
        ("My email is david at chenlaw dot co dot uk", ["chenlaw", "co"]),  # uncertain domain
        "Yes that is correct, david at chenlaw dot co dot uk",
        "07911223344",
        "Thursday at 9am",
        "Yes go ahead",
    ]
)


# ── Scenario C: Repeated failure → escalation ────────────────────────────────
# Agent cannot confirm the email after 3 attempts → should transfer to human
scenario_c = run_scenario(
    "SCENARIO C — Repeated failure: escalates after 3 clarification attempts",
    [
        "I need to book a family law consultation about a divorce",
        "It is about financial arrangements, no court proceedings",
        "Yes I want to book",
        "My name is Tom Richards",
        ("My email is t dot richrdz at gmial dot com", ["richrdz", "gmial"]),  # badly garbled
        ("No it is richrdz at gmial dot com",           ["richrdz", "gmial"]),  # still unclear
        ("Sorry, r-i-c-h-r-d-z at gmial",               ["richrdz", "gmial"]),  # 3rd failure
    ]
)


# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("  TEST SUMMARY")
print(f"{'='*60}")
print(f"  Scenario A (low-conf name, corrected)  : {'PASS — booking confirmed' if scenario_a.booking_confirmed else 'FAIL'}")
print(f"  Scenario B (low-conf email, confirmed) : {'PASS — booking confirmed' if scenario_b.booking_confirmed else 'FAIL'}")
print(f"  Scenario C (3 failures → escalation)   : {'PASS — transferred' if scenario_c.transferred else 'FAIL — not transferred'}")
