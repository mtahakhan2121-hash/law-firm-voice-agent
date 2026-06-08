"""
Confidence analysis between STT output and agent input.

Analyses which words are uncertain and whether they fall on
critical fields (name, email, phone). Builds a signal string
that is prepended to the user message so the LLM knows to
confirm rather than accept and move on.
"""

from pipeline.stt import TranscriptionResult

# Keywords that suggest the uncertain word is part of a critical field
_NAME_HINTS  = {"name", "called", "i'm", "im", "my"}
_EMAIL_HINTS = {"@", "email", "address", "dot", "gmail", "outlook", "yahoo", "hotmail"}
_PHONE_HINTS = {"number", "phone", "mobile", "call", "reach"}


def build_confidence_signal(result: TranscriptionResult) -> str:
    """
    Return a signal string to prepend to the user message when STT
    confidence is low on words that are likely critical fields.

    Returns empty string when confidence is fine.
    """
    if not result.uncertain_words:
        return ""

    uncertain = [w.strip(".,!?") for w in result.uncertain_words]
    text_lower = result.transcript.lower()

    # Check if uncertain words overlap with critical-field context
    is_name_context  = any(h in text_lower for h in _NAME_HINTS)
    is_email_context = any(h in text_lower for h in _EMAIL_HINTS) or "@" in text_lower
    is_phone_context = any(h in text_lower for h in _PHONE_HINTS) or _looks_like_phone(text_lower)

    if not (is_name_context or is_email_context or is_phone_context):
        # Uncertain words but not on a critical field — no signal needed
        return ""

    field_hints = []
    if is_name_context:
        field_hints.append("name")
    if is_email_context:
        field_hints.append("email")
    if is_phone_context:
        field_hints.append("phone number")

    uncertain_str = ", ".join(f'"{w}"' for w in uncertain)
    field_str     = " or ".join(field_hints)

    return (
        f"[STT NOTE: low confidence on {uncertain_str} — "
        f"this may be a {field_str}. "
        f"Confirm by reading it back before accepting.] "
    )


def _looks_like_phone(text: str) -> bool:
    """True if the transcript contains a run of digits that could be a phone number."""
    import re
    digits = re.sub(r"\D", "", text)
    return len(digits) >= 7
