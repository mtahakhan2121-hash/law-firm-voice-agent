"""
Phase 3 test script — runs three booking scenarios automatically.

Scenario A: Happy path — full booking completes successfully
Scenario B: Unavailable slot — agent offers alternatives, caller picks one
Scenario C: Human transfer — caller asks to speak to a person

Run: python test_phase3.py
"""

import os
import sys
sys.path.insert(0, ".")

# Reset and re-seed DB before each scenario
def reset_db():
    from config import DB_PATH
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    from booking.db import init_db, seed_slots
    init_db()
    seed_slots()


from agent.session import SessionState
from agent.agent import respond


def run_scenario(title: str, turns: list[str]) -> SessionState:
    reset_db()
    session = SessionState()

    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

    # Opening greeting
    reply, ms = respond("[CALL_START]", session)
    print(f"\n[agent] {reply}")

    for user_input in turns:
        print(f"\n[caller] {user_input}")
        reply, ms = respond(user_input, session)

        # Print any tool calls from history
        for msg in session.history[-3:]:
            if msg.get("role") == "tool":
                print(f"  [tool result] {msg['content'][:100]}...")

        print(f"[agent]  {reply}  ({ms:.0f}ms)")

        if session.transferred or session.booking_confirmed:
            break

    print(f"\n--- Result ---")
    if session.booking_confirmed:
        print(f"  BOOKING CONFIRMED")
        print(f"  Reference : {session.booking_reference}")
        print(f"  Name      : {session.collected.name}")
        print(f"  Email     : {session.collected.email}")
        print(f"  Phone     : {session.collected.phone}")
        print(f"  Slot      : {session.collected.preferred_slot}")
    elif session.transferred:
        print(f"  TRANSFERRED TO HUMAN")
        print(f"  Reason    : {session.transfer_reason}")
    else:
        print(f"  Call ended without booking or transfer")
        print(f"  Law area  : {session.law_area}")
        print(f"  Collected : {session.collected}")

    return session


# ── Scenario A: Happy path ────────────────────────────────────────────────────
scenario_a = run_scenario(
    "SCENARIO A — Happy path: full booking",
    [
        "I need to book a consultation about a tenancy dispute",
        "I am the tenant, my landlord is refusing to return my deposit",
        "It is a private rental",
        "No court proceedings yet",
        "Yes I would like to book a consultation",
        "My name is James Miller",
        "My email is james.miller@gmail.com",
        "My phone number is 07712345678",
        "Tuesday at 11am please",
        "Yes those details are correct, please go ahead",   # confirm → agent should call book_consultation
    ]
)


# ── Scenario B: Unavailable slot ──────────────────────────────────────────────
scenario_b = run_scenario(
    "SCENARIO B — Unavailable slot: caller picks alternative",
    [
        "I was unfairly dismissed from my job and want to book a consultation",
        "I was dismissed last month, it was definitely unfair dismissal",
        "I am no longer employed there",
        "Yes please book me in",
        "Sarah Johnson",
        "sarah.j@outlook.com",
        "07798001234",
        "Tuesday at 10am",               # pre-booked — should trigger alternatives
        "Okay Tuesday at 11am then",     # available slot — should succeed
        "Yes that's all correct please book it",
    ]
)


# ── Scenario C: Human transfer ────────────────────────────────────────────────
scenario_c = run_scenario(
    "SCENARIO C — Human transfer: caller asks for a real person",
    [
        "I have a family law matter",
        "I am going through a divorce and there are children involved",
        "I really need to speak to an actual solicitor right now, not a bot",
    ]
)


# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("  TEST SUMMARY")
print(f"{'='*60}")
print(f"  Scenario A (happy path)      : {'PASS — booking confirmed' if scenario_a.booking_confirmed else 'FAIL'}")
print(f"  Scenario B (unavailable slot): {'PASS — booking confirmed' if scenario_b.booking_confirmed else 'FAIL — no booking'}")
print(f"  Scenario C (human transfer)  : {'PASS — transferred' if scenario_c.transferred else 'FAIL'}")
