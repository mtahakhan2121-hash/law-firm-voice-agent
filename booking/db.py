"""
SQLite-backed consultation calendar.

Schema:
  slots    — available time slots (pre-seeded)
  bookings — confirmed consultations

Slot matching is intentionally fuzzy: the caller (and LLM) will pass
natural strings like "Monday 10am" or "Tuesday afternoon". We normalise
those against our slot list and return the closest match.
"""

import re
import sqlite3
import uuid
from datetime import datetime, timedelta, date
from pathlib import Path

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import DB_PATH

# ── Helpers ───────────────────────────────────────────────────────────────────

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _slot_display(dt: datetime) -> str:
    """Human-readable slot string, e.g. 'Monday 9 June at 10:00am'"""
    return dt.strftime("%A %-d %B at %-I:%M%p").lower()


# ── Schema creation ───────────────────────────────────────────────────────────

def init_db() -> None:
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS slots (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                dt        TEXT NOT NULL UNIQUE,   -- ISO: 2026-06-09 10:00
                status    TEXT NOT NULL DEFAULT 'available'  -- available | booked
            );

            CREATE TABLE IF NOT EXISTS bookings (
                id           TEXT PRIMARY KEY,    -- UUID reference
                slot_id      INTEGER NOT NULL REFERENCES slots(id),
                name         TEXT NOT NULL,
                email        TEXT NOT NULL,
                phone        TEXT NOT NULL,
                matter_type  TEXT NOT NULL,
                booked_at    TEXT NOT NULL        -- ISO timestamp
            );
        """)


# ── Seeding ───────────────────────────────────────────────────────────────────

def seed_slots(from_date: date | None = None) -> int:
    """
    Seed weekday consultation slots (9am–4pm, on the hour) for the next 2 weeks.
    Marks a handful as already booked so the unavailable-slot path can be demoed.
    Returns the number of slots inserted.
    """
    if from_date is None:
        from_date = date.today() + timedelta(days=1)

    hours = [9, 10, 11, 14, 15, 16]   # morning + afternoon slots
    already_booked_offsets = {1, 4, 8}  # slot indices to pre-mark as booked

    slots: list[str] = []
    current = from_date
    end = from_date + timedelta(days=14)

    while current < end:
        if current.weekday() < 5:   # Monday–Friday only
            for h in hours:
                dt = datetime(current.year, current.month, current.day, h, 0)
                slots.append(dt.strftime("%Y-%m-%d %H:%M"))
        current += timedelta(days=1)

    inserted = 0
    with _connect() as conn:
        for i, slot_dt in enumerate(slots):
            status = "booked" if i in already_booked_offsets else "available"
            try:
                conn.execute(
                    "INSERT INTO slots (dt, status) VALUES (?, ?)",
                    (slot_dt, status)
                )
                inserted += 1
            except sqlite3.IntegrityError:
                pass  # slot already exists — skip on re-seed

    return inserted


def is_seeded() -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) as n FROM slots").fetchone()
        return row["n"] > 0


# ── Slot matching ─────────────────────────────────────────────────────────────

# Weekday name → number (Monday=0)
_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2,
    "thursday": 3, "friday": 4,
}

# Time-of-day keywords → hour range to search
_TIME_RANGES = {
    "morning":   (9, 12),
    "afternoon": (13, 17),
    "am":        (9, 12),
    "pm":        (13, 17),
}


def _parse_hour(text: str) -> int | None:
    """Extract an hour from strings like '10am', '2pm', '14:00', '10:00'."""
    text = text.lower().strip()

    # Match "10:00", "14:00", "11:00am", "2:00pm"
    m = re.search(r'\b(\d{1,2}):(\d{2})\s*(am|pm)?', text)
    if m:
        h = int(m.group(1))
        meridiem = m.group(3)
        if meridiem == "pm" and h < 12:
            h += 12
        if meridiem == "am" and h == 12:
            h = 0
        return h

    # Match "10am" / "2pm"
    m = re.search(r'\b(\d{1,2})\s*(am|pm)\b', text)
    if m:
        h = int(m.group(1))
        meridiem = m.group(2)
        if meridiem == "pm" and h < 12:
            h += 12
        if meridiem == "am" and h == 12:
            h = 0
        return h

    return None


def _candidate_slots(requested: str) -> list[datetime]:
    """
    Return available DB slots that best match the requested string.
    Tries exact datetime parse first, then weekday+time fuzzy match.
    """
    requested_lower = requested.lower()
    now = datetime.now()

    with _connect() as conn:
        rows = conn.execute(
            "SELECT dt FROM slots WHERE dt > ? ORDER BY dt",
            (now.strftime("%Y-%m-%d %H:%M"),)
        ).fetchall()

    available = [datetime.strptime(r["dt"], "%Y-%m-%d %H:%M") for r in rows]

    if not available:
        return []

    # 1. Try to parse as explicit date/time (e.g. "2026-06-10 10:00")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(requested.strip(), fmt)
            # Return slots on that date (or exact match)
            matches = [s for s in available if s.date() == parsed.date()]
            if fmt == "%Y-%m-%d %H:%M":
                exact = [s for s in matches if s == parsed]
                if exact:
                    return exact
            if matches:
                return matches
        except ValueError:
            pass

    # 2. Weekday match (e.g. "Monday", "next Tuesday")
    matched_weekday: list[datetime] = []
    for name, wd in _WEEKDAYS.items():
        if name in requested_lower:
            matched_weekday = [s for s in available if s.weekday() == wd]
            break

    pool = matched_weekday if matched_weekday else available

    # 3. Hour/time-of-day filter
    hour = _parse_hour(requested_lower)
    if hour is not None:
        hour_matches = [s for s in pool if s.hour == hour]
        if hour_matches:
            return hour_matches

    for keyword, (h_start, h_end) in _TIME_RANGES.items():
        if keyword in requested_lower:
            range_matches = [s for s in pool if h_start <= s.hour < h_end]
            if range_matches:
                return range_matches

    return pool


def is_slot_available(requested: str) -> tuple[bool, str]:
    """
    Check if a requested slot is available.

    Returns (True, slot_display_string) if available,
    or (False, '') if the best candidate is already booked.
    """
    candidates = _candidate_slots(requested)
    if not candidates:
        return False, ""

    best = candidates[0]
    best_str = best.strftime("%Y-%m-%d %H:%M")

    with _connect() as conn:
        row = conn.execute(
            "SELECT status FROM slots WHERE dt = ?", (best_str,)
        ).fetchone()

    if row and row["status"] == "available":
        return True, _slot_display(best)

    # Slot exists but is booked — return False with empty string
    return False, ""


def get_alternative_slots(limit: int = 3) -> list[str]:
    """Return the next N available slots as human-readable strings."""
    now = datetime.now()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT dt FROM slots WHERE status = 'available' AND dt > ? ORDER BY dt LIMIT ?",
            (now.strftime("%Y-%m-%d %H:%M"), limit)
        ).fetchall()
    return [_slot_display(datetime.strptime(r["dt"], "%Y-%m-%d %H:%M")) for r in rows]


# ── Booking ───────────────────────────────────────────────────────────────────

def create_booking(name: str, email: str, phone: str, matter_type: str, slot: str) -> str:
    """
    Write a confirmed booking to the DB and mark the slot as booked.
    Returns a short reference ID (e.g. 'REF-A3F2').
    """
    candidates = _candidate_slots(slot)
    if not candidates:
        raise ValueError(f"No matching slot found for: {slot!r}")

    best = candidates[0]
    best_str = best.strftime("%Y-%m-%d %H:%M")
    ref = "REF-" + uuid.uuid4().hex[:4].upper()

    with _connect() as conn:
        row = conn.execute("SELECT id, status FROM slots WHERE dt = ?", (best_str,)).fetchone()
        if not row:
            raise ValueError(f"Slot {best_str!r} does not exist in the calendar.")
        if row["status"] != "available":
            raise ValueError(f"Slot {best_str!r} is no longer available.")

        conn.execute("UPDATE slots SET status = 'booked' WHERE id = ?", (row["id"],))
        conn.execute(
            """INSERT INTO bookings (id, slot_id, name, email, phone, matter_type, booked_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (ref, row["id"], name, email, phone, matter_type, datetime.now().isoformat()),
        )

    return ref


def list_bookings() -> list[dict]:
    """Return all confirmed bookings (for inspection / demo)."""
    with _connect() as conn:
        rows = conn.execute("""
            SELECT b.id, b.name, b.email, b.phone, b.matter_type, s.dt, b.booked_at
            FROM bookings b JOIN slots s ON b.slot_id = s.id
            ORDER BY s.dt
        """).fetchall()
    return [dict(r) for r in rows]
