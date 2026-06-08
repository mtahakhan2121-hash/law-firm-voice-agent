"""
Handoff summary generator.

When a call is transferred to a human, this builds the summary
the human agent sees when they pick up — caller details, law area,
reason for transfer, and the full conversation transcript.
"""

from datetime import datetime
from agent.session import SessionState


def build_handoff_summary(session: SessionState) -> str:
    lines = []
    lines.append("=" * 60)
    lines.append("  INCOMING TRANSFER — CALLER DETAILS")
    lines.append("=" * 60)
    lines.append(f"  Time        : {datetime.now().strftime('%d %B %Y at %H:%M')}")
    lines.append(f"  Law area    : {session.law_area or 'not identified'}")
    lines.append(f"  Transfer reason: {session.transfer_reason or 'not specified'}")
    lines.append("")
    lines.append("  Collected details:")
    lines.append(f"    Name    : {session.collected.name or 'not collected'}")
    lines.append(f"    Email   : {session.collected.email or 'not collected'}")
    lines.append(f"    Phone   : {session.collected.phone or 'not collected'}")
    lines.append(f"    Matter  : {session.collected.matter_type or 'not collected'}")

    if session.clarification_counts:
        lines.append("")
        lines.append("  Clarification attempts (fields that were difficult to capture):")
        for field, count in session.clarification_counts.items():
            lines.append(f"    {field}: {count} attempt(s)")

    lines.append("")
    lines.append("  Conversation transcript:")
    lines.append("  " + "-" * 56)
    for msg in session.history:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if not content or role == "tool":
            continue
        if role == "user" and not content.startswith("["):
            # Strip STT confidence signals for readability
            clean = content
            if content.startswith("[STT NOTE:"):
                bracket_end = content.find("] ")
                if bracket_end != -1:
                    clean = content[bracket_end + 2:]
            lines.append(f"  caller : {clean}")
        elif role == "assistant":
            lines.append(f"  agent  : {content}")

    lines.append("=" * 60)
    return "\n".join(lines)
