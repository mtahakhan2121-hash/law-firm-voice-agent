"""
Per-call session state.

Tracks conversation history and everything collected from the caller
across multiple turns. One instance lives for the duration of a call.
"""

from dataclasses import dataclass, field


@dataclass
class CollectedDetails:
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    matter_type: str | None = None
    preferred_slot: str | None = None

    def missing(self) -> list[str]:
        fields = {
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "matter_type": self.matter_type,
            "preferred_slot": self.preferred_slot,
        }
        return [k for k, v in fields.items() if not v]

    def is_complete(self) -> bool:
        return len(self.missing()) == 0


@dataclass
class SessionState:
    # Conversation history sent to the LLM (sliding window)
    history: list[dict] = field(default_factory=list)

    # Routing
    law_area: str | None = None          # e.g. "employment", "tenancy"

    # Booking details collected from the caller
    collected: CollectedDetails = field(default_factory=CollectedDetails)

    # Escalation tracking
    clarification_counts: dict[str, int] = field(default_factory=dict)
    escalation_count: int = 0
    transferred: bool = False
    transfer_reason: str | None = None

    # Booking outcome
    booking_confirmed: bool = False
    booking_reference: str | None = None

    MAX_CLARIFICATIONS = 3  # escalate to human after this many failed attempts on one field

    def record_clarification(self, field_name: str) -> int:
        """Increment and return the clarification count for a field."""
        self.clarification_counts[field_name] = self.clarification_counts.get(field_name, 0) + 1
        return self.clarification_counts[field_name]

    def should_escalate_field(self, field_name: str) -> bool:
        return self.clarification_counts.get(field_name, 0) >= self.MAX_CLARIFICATIONS

    def add_user_message(self, content: str) -> None:
        self.history.append({"role": "user", "content": content})
        self._trim_history()

    def add_assistant_message(self, content: str) -> None:
        self.history.append({"role": "assistant", "content": content})
        self._trim_history()

    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        self.history.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        })

    def _trim_history(self) -> None:
        from config import MAX_HISTORY_TURNS
        # Keep at most MAX_HISTORY_TURNS pairs (user + assistant = 2 messages each)
        max_messages = MAX_HISTORY_TURNS * 2
        if len(self.history) > max_messages:
            self.history = self.history[-max_messages:]
