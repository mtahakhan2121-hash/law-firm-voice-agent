"""
Phase 5 test — all four escalation triggers.

Trigger 1: Explicit request  — caller asks for a real person
Trigger 2: Out of scope      — legal matter the firm doesn't handle
Trigger 3: Urgent/emergency  — caller has a hearing today
Trigger 4: Clarification fail— already tested in Phase 4; included here for completeness

Run: python test_phase5.py
"""

import os, sys
sys.path.insert(0, ".")

from agent.session import SessionState
from agent.agent import respond
from agent.handoff import build_handoff_summary
from pipeline.stt import TranscriptionResult
from pipeline.confidence import build_confidence_signal


def reset_db():
    from config import DB_PATH
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    from booking.db import init_db, seed_slots
    init_db()
    seed_slots()


def fake_stt(transcript: str, uncertain: list[str] = None) -> TranscriptionResult:
    return TranscriptionResult(
        transcript=transcript,
        avg_confidence=0.45 if uncertain else 0.95,
        uncertain_words=uncertain or [],
        audio_duration_s=2.0,
        elapsed_ms=600.0,
    )


def run_scenario(title: str, turns: list, expect_transfer: bool = True) -> SessionState:
    reset_db()
    session = SessionState()

    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

    reply, _ = respond("[CALL_START]", session)
    print(f"\n[agent] {reply}")

    for turn in turns:
        if isinstance(turn, tuple):
            transcript, uncertain = turn
            result = fake_stt(transcript, uncertain)
            signal = build_confidence_signal(result)
            message = signal + transcript
        else:
            transcript = turn
            message = transcript

        print(f"\n[caller] {transcript}")
        reply, ms = respond(message, session)
        print(f"[agent]  {reply}  ({ms:.0f}ms)")

        if session.transferred or session.booking_confirmed:
            break

    print(f"\n--- Result ---")
    if session.transferred:
        print(f"  TRANSFERRED  reason='{session.transfer_reason}'")
        print(build_handoff_summary(session))
    elif session.booking_confirmed:
        print(f"  BOOKING  ref={session.booking_reference}")
    else:
        print(f"  No transfer or booking after {len(turns)} turns")

    return session


# ── Trigger 1: Explicit request ───────────────────────────────────────────────
t1 = run_scenario(
    "TRIGGER 1 — Explicit request: caller asks for a human",
    [
        "I have a question about my employment contract",
        "I was put on a performance improvement plan and I think it is unfair",
        "Actually can I just speak to a real solicitor please",
    ]
)

# ── Trigger 2: Out of scope ───────────────────────────────────────────────────
t2 = run_scenario(
    "TRIGGER 2 — Out of scope: criminal matter the firm doesn't handle",
    [
        "I need legal advice urgently",
        "I have been charged with fraud and my trial starts next week",
    ]
)

# ── Trigger 3: Urgent / emergency ────────────────────────────────────────────
t3 = run_scenario(
    "TRIGGER 3 — Urgent: caller has a court hearing today",
    [
        "I need help with a family matter",
        "I have a custody hearing in court today at 2pm and I have no representation",
    ]
)

# ── Trigger 4: Clarification failure (recap from Phase 4) ────────────────────
t4 = run_scenario(
    "TRIGGER 4 — Clarification failure: email cannot be confirmed after 3 attempts",
    [
        "I need to book about a tenancy dispute",
        "I am the tenant, deposit not returned, private rental",
        "Yes please book me in",
        "Alex Novak",
        ("My email is alex at nvk dot io", ["nvk"]),
        ("No its nvk dot io",              ["nvk"]),
        ("n-v-k dot io",                   ["nvk"]),
    ]
)

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("  TEST SUMMARY")
print(f"{'='*60}")
results = [
    ("Trigger 1 — explicit request  ", t1.transferred),
    ("Trigger 2 — out of scope      ", t2.transferred),
    ("Trigger 3 — urgent emergency  ", t3.transferred),
    ("Trigger 4 — clarification fail", t4.transferred),
]
all_pass = True
for label, passed in results:
    status = "PASS" if passed else "FAIL"
    if not passed:
        all_pass = False
    print(f"  {label}: {status}")
print(f"\n  Overall: {'ALL PASS' if all_pass else 'SOME FAILED'}")
