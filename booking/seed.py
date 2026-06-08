"""
Run this once to initialise the DB and seed consultation slots.
Safe to re-run — duplicate slots are skipped.

Usage: python booking/seed.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from booking.db import init_db, seed_slots, is_seeded, list_bookings
from datetime import datetime


def main():
    print("Initialising booking database...")
    init_db()

    if is_seeded():
        print("Slots already seeded. Use --force to re-seed.")
        if "--force" not in sys.argv:
            _print_summary()
            return

    n = seed_slots()
    print(f"Seeded {n} slots (next 2 weeks, Mon–Fri, 9am–4pm).")
    print("3 slots pre-marked as booked to demo unavailable-slot handling.\n")
    _print_summary()


def _print_summary():
    import sqlite3
    from config import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    available = conn.execute("SELECT COUNT(*) as n FROM slots WHERE status='available'").fetchone()["n"]
    booked    = conn.execute("SELECT COUNT(*) as n FROM slots WHERE status='booked'").fetchone()["n"]
    total     = available + booked

    print(f"Calendar: {total} slots total — {available} available, {booked} pre-booked")
    print("\nNext 5 available slots:")
    rows = conn.execute(
        "SELECT dt FROM slots WHERE status='available' ORDER BY dt LIMIT 5"
    ).fetchall()
    for r in rows:
        dt = datetime.strptime(r["dt"], "%Y-%m-%d %H:%M")
        print(f"  {dt.strftime('%A %-d %B at %-I:%M%p').lower()}")

    print("\nPre-booked slots (to demo unavailable path):")
    rows = conn.execute(
        "SELECT dt FROM slots WHERE status='booked' ORDER BY dt"
    ).fetchall()
    for r in rows:
        dt = datetime.strptime(r["dt"], "%Y-%m-%d %H:%M")
        print(f"  {dt.strftime('%A %-d %B at %-I:%M%p').lower()}  ← already taken")

    conn.close()


if __name__ == "__main__":
    main()
