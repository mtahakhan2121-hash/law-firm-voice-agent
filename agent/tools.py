"""
Tool definitions and execution for the law firm voice agent.

Each tool has:
  - A JSON schema (sent to OpenAI so the model knows when/how to call it)
  - An execute function (called locally when the model requests it)
"""

import json
from agent.session import SessionState
from agent.prompts import LAW_AREA_QUESTIONS


# ── Tool schemas (sent to OpenAI) ─────────────────────────────────────────────

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "route_to_law_area",
            "description": (
                "Call this as soon as you know what area of law the caller needs. "
                "It sets the routing and returns the specific follow-up questions to ask."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "area": {
                        "type": "string",
                        "enum": ["employment", "tenancy", "family", "personal_injury", "other"],
                        "description": "The area of law identified from the caller's description.",
                    },
                    "brief_summary": {
                        "type": "string",
                        "description": "One sentence summary of the caller's situation.",
                    },
                },
                "required": ["area", "brief_summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_slot_availability",
            "description": "Check if a requested consultation slot is available. Always call this before confirming a booking.",
            "parameters": {
                "type": "object",
                "properties": {
                    "requested_slot": {
                        "type": "string",
                        "description": "The date and time the caller requested, e.g. 'Monday 10am' or '2024-06-10 14:00'.",
                    },
                },
                "required": ["requested_slot"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_consultation",
            "description": "Book a consultation once all details are collected and confirmed with the caller.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Caller's full name."},
                    "email": {"type": "string", "description": "Caller's email address."},
                    "phone": {"type": "string", "description": "Caller's phone number."},
                    "matter_type": {"type": "string", "description": "Brief description of the legal matter."},
                    "slot": {"type": "string", "description": "The confirmed date and time for the consultation."},
                },
                "required": ["name", "email", "phone", "matter_type", "slot"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "transfer_to_human",
            "description": (
                "End the AI call and transfer the caller to a human team member. "
                "Use when the caller asks for a person, the matter is out of scope, "
                "there is an urgent situation, or you cannot confirm a detail after 3 attempts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Why the call is being transferred.",
                    },
                },
                "required": ["reason"],
            },
        },
    },
]


# ── Tool execution ─────────────────────────────────────────────────────────────

def execute_tool(name: str, arguments: str, session: SessionState) -> str:
    """Dispatch a tool call by name and return the result as a string."""
    args = json.loads(arguments)

    if name == "route_to_law_area":
        return _route_to_law_area(args, session)
    elif name == "check_slot_availability":
        return _check_slot_availability(args, session)
    elif name == "book_consultation":
        return _book_consultation(args, session)
    elif name == "transfer_to_human":
        return _transfer_to_human(args, session)
    else:
        return f"Unknown tool: {name}"


def _route_to_law_area(args: dict, session: SessionState) -> str:
    area = args["area"]
    summary = args["brief_summary"]

    if session.law_area and session.law_area != "other":
        return (
            f"Routing already set to '{session.law_area}'. "
            "Do not call this tool again. Focus on collecting the caller's details for booking."
        )

    session.law_area = area
    session.collected.matter_type = summary

    if area == "other":
        return (
            "Area: other (out of scope). "
            "Instruct the agent to apologise, explain the firm does not cover this area, "
            "and offer to transfer to a team member who can advise further."
        )

    questions = LAW_AREA_QUESTIONS.get(area, [])
    questions_text = " | ".join(questions) if questions else "No specific questions for this area."
    return (
        f"Routing confirmed: {area}. "
        f"Summary: {summary}. "
        f"Recommended follow-up questions to ask one at a time: {questions_text}"
    )


def _check_slot_availability(args: dict, session: SessionState) -> str:
    # Import here to avoid circular issues; booking module built in Phase 3
    try:
        from booking.db import is_slot_available, get_alternative_slots
        requested = args["requested_slot"]
        available, matched_slot = is_slot_available(requested)
        if available:
            return f"Slot available: {matched_slot}. You may proceed to book."
        else:
            alternatives = get_alternative_slots(limit=3)
            alt_text = ", ".join(alternatives) if alternatives else "no alternatives currently available"
            return (
                f"Slot '{requested}' is not available. "
                f"Offer the caller these alternatives: {alt_text}"
            )
    except ImportError:
        # Booking module not built yet (Phase 3) — return a stub response
        return (
            f"Slot '{args['requested_slot']}' is available. "
            "(Stub: booking DB not yet set up — will be wired in Phase 3)"
        )


def _book_consultation(args: dict, session: SessionState) -> str:
    try:
        from booking.db import create_booking
        ref = create_booking(
            name=args["name"],
            email=args["email"],
            phone=args["phone"],
            matter_type=args["matter_type"],
            slot=args["slot"],
        )
        session.collected.name = args["name"]
        session.collected.email = args["email"]
        session.collected.phone = args["phone"]
        session.collected.preferred_slot = args["slot"]
        session.booking_confirmed = True
        session.booking_reference = ref
        return (
            f"Booking confirmed. Reference: {ref}. "
            f"Details: {args['name']}, {args['email']}, {args['phone']}, "
            f"slot: {args['slot']}, matter: {args['matter_type']}."
        )
    except ImportError:
        # Stub for Phase 2 — booking DB built in Phase 3
        import random
        ref = f"REF-{random.randint(1000, 9999)}"
        session.collected.name = args["name"]
        session.collected.email = args["email"]
        session.collected.phone = args["phone"]
        session.collected.preferred_slot = args["slot"]
        session.booking_confirmed = True
        session.booking_reference = ref
        return (
            f"Booking confirmed (stub). Reference: {ref}. "
            f"Details: {args['name']}, {args['email']}, {args['phone']}, "
            f"slot: {args['slot']}, matter: {args['matter_type']}."
        )


def _transfer_to_human(args: dict, session: SessionState) -> str:
    reason = args["reason"]
    session.transferred = True
    session.transfer_reason = reason
    return (
        f"Transfer initiated. Reason: {reason}. "
        "Tell the caller you are connecting them to a team member and to please hold."
    )
