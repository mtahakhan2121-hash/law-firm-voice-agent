"""
Agent core — sends conversation to OpenAI and handles tool call dispatch.

The agent runs a loop per turn:
  1. Send history + new user message to OpenAI
  2. If the model calls a tool, execute it locally and send the result back
  3. Repeat until the model produces a plain text response
  4. Return that response to the caller
"""

import os
import time
from openai import OpenAI

from agent.session import SessionState
from agent.prompts import SYSTEM_PROMPT
from agent.tools import TOOL_SCHEMAS, execute_tool

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import OPENAI_API_KEY, OPENAI_MODEL


_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        key = OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise ValueError("OPENAI_API_KEY is not set. Export it in your shell before running.")
        _client = OpenAI(api_key=key)
    return _client


def _state_context(session: SessionState) -> str:
    """
    Appended to the system prompt each turn so the model always knows
    the current call state without needing to re-derive it from history.
    """
    lines = ["\n\n## Current call state (do not repeat information already established)"]

    if session.law_area:
        lines.append(f"- Law area: ALREADY IDENTIFIED as '{session.law_area}'. Do NOT call route_to_law_area again.")
    else:
        lines.append("- Law area: not yet identified. Call route_to_law_area once you know it.")

    if session.booking_confirmed:
        lines.append(f"- Booking already confirmed: {session.booking_reference}. Say goodbye.")
    else:
        lines.append(
            "- To book: collect name, email, phone, and preferred slot from the caller. "
            "Once you have all four AND the caller has confirmed them, call book_consultation immediately. "
            "Do not ask 'shall I proceed' — just book it once the caller confirms the details are correct."
        )

    # Clarification tracking — warn the model when approaching escalation limit
    if session.clarification_counts:
        for field_name, count in session.clarification_counts.items():
            remaining = session.MAX_CLARIFICATIONS - count
            if remaining <= 0:
                lines.append(
                    f"- ESCALATION REQUIRED: failed to confirm '{field_name}' after "
                    f"{session.MAX_CLARIFICATIONS} attempts. Call transfer_to_human now."
                )
            elif remaining == 1:
                lines.append(
                    f"- WARNING: 1 attempt left to confirm '{field_name}' before escalating to human."
                )

    return "\n".join(lines)


_TRANSFER_PHRASES = [
    "connecting you", "connect you", "transfer your call", "transferring you",
    "put you through", "team member", "one of our", "please hold",
    "human agent", "member of staff", "colleague",
]

def _sounds_like_transfer(reply: str) -> bool:
    """True if the reply contains language indicating a human transfer."""
    reply_lower = reply.lower()
    return any(phrase in reply_lower for phrase in _TRANSFER_PHRASES)


def _track_clarifications(reply: str, session: SessionState) -> None:
    """
    Detect when the agent is asking for confirmation of a specific field
    and increment the clarification counter for that field.
    """
    reply_lower = reply.lower()

    # Patterns that indicate the agent is re-confirming a field
    confirmation_phrases = [
        "is that correct", "did i get that right", "can you confirm",
        "could you repeat", "spell that", "say that again",
        "is that right", "correct?", "repeat your", "repeat that",
    ]
    is_confirming = any(p in reply_lower for p in confirmation_phrases)
    if not is_confirming:
        return

    if any(w in reply_lower for w in ["name", "surname", "first name", "last name"]):
        session.record_clarification("name")
    if any(w in reply_lower for w in ["email", "@", "address"]):
        session.record_clarification("email")
    if any(w in reply_lower for w in ["phone", "number", "mobile"]):
        session.record_clarification("phone")


def _calendar_context() -> str:
    """Inject the next few available slots so the model can suggest times naturally."""
    try:
        from booking.db import get_alternative_slots
        slots = get_alternative_slots(limit=5)
        if slots:
            slot_list = "\n".join(f"  - {s}" for s in slots)
            return f"\n\n## Next available consultation slots\n{slot_list}\nWhen the caller asks about availability, suggest from this list."
    except Exception:
        pass
    return ""


def respond(user_text: str, session: SessionState) -> tuple[str, float]:
    """
    Process one turn of the conversation.

    Adds the user message to session history, calls OpenAI (with tool use),
    resolves any tool calls, and returns the final text response + elapsed ms.
    """
    session.add_user_message(user_text)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + _state_context(session) + _calendar_context()},
    ] + session.history

    client = _get_client()
    t0 = time.monotonic()

    # Tool dispatch loop — keeps going until the model gives a plain text reply
    while True:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            temperature=0.3,   # low temp for consistent, predictable responses
            max_tokens=300,    # voice responses should be short
        )

        message = response.choices[0].message

        # No tool call — model gave a plain text response
        if not message.tool_calls:
            elapsed_ms = (time.monotonic() - t0) * 1000
            reply = message.content or ""
            session.add_assistant_message(reply)
            _track_clarifications(reply, session)

            # Safety net: model said transfer words but forgot to call the tool
            if not session.transferred and _sounds_like_transfer(reply):
                print("  [agent] transfer language detected without tool call — forcing transfer")
                execute_tool(
                    "transfer_to_human",
                    '{"reason": "Agent indicated transfer in response but tool was not called."}',
                    session,
                )

            # If any field just hit the escalation limit, force a transfer turn
            escalate_field = next(
                (f for f in session.clarification_counts if session.should_escalate_field(f)),
                None,
            )
            if escalate_field and not session.transferred:
                print(f"  [confidence] escalation limit reached for '{escalate_field}' — forcing transfer")
                transfer_reply, _ = respond(
                    f"[SYSTEM: escalate now — failed to confirm {escalate_field} after "
                    f"{session.MAX_CLARIFICATIONS} attempts]",
                    session,
                )
                return transfer_reply, (time.monotonic() - t0) * 1000

            return reply, elapsed_ms

        # One or more tool calls — execute each and feed results back
        # Append the assistant message with tool_calls to history
        messages.append(message)

        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            tool_args = tool_call.function.arguments
            print(f"  [tool] {tool_name}({tool_args})")

            result = execute_tool(tool_name, tool_args, session)
            print(f"  [tool] → {result[:120]}{'...' if len(result) > 120 else ''}")

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

            # If transfer was triggered, stop the tool loop immediately
            if session.transferred:
                elapsed_ms = (time.monotonic() - t0) * 1000
                # Let the model generate the handoff message
                break

        # If session is done, do one final LLM call to get the goodbye message
        if session.transferred or session.booking_confirmed:
            final = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                temperature=0.3,
                max_tokens=150,
            )
            elapsed_ms = (time.monotonic() - t0) * 1000
            reply = final.choices[0].message.content or ""
            session.add_assistant_message(reply)
            return reply, elapsed_ms
