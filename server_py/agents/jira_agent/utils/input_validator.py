"""Input validation and sanitization for JIRA agent."""
import re
from typing import Optional

from core.logging import log_warning


# Limits
MAX_PROMPT_LENGTH = 4000
MAX_SESSION_ID_LENGTH = 128
MAX_TICKET_KEY_LENGTH = 20

# Patterns that might indicate prompt injection attempts
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"disregard\s+(all\s+)?prior",
    r"you\s+are\s+now\s+a\s+different",
    r"system\s*:\s*",
    r"<\|.*?\|>",
    r"\[INST\]",
    r"\[/INST\]",
]

_injection_regex = re.compile(
    "|".join(INJECTION_PATTERNS), re.IGNORECASE
)


class InputValidationError(Exception):
    """Raised when user input fails validation."""

    def __init__(self, message: str, field: str = "input"):
        self.field = field
        super().__init__(message)


def validate_prompt(prompt: str) -> str:
    """Validate and sanitize a user prompt.

    Args:
        prompt: Raw user input

    Returns:
        Sanitized prompt string

    Raises:
        InputValidationError: If the input is invalid or suspicious
    """
    if not prompt or not prompt.strip():
        raise InputValidationError("Prompt cannot be empty", field="prompt")

    prompt = prompt.strip()

    if len(prompt) > MAX_PROMPT_LENGTH:
        raise InputValidationError(
            f"Prompt exceeds maximum length of {MAX_PROMPT_LENGTH} characters",
            field="prompt",
        )

    if _injection_regex.search(prompt):
        log_warning(f"Potential prompt injection detected (length={len(prompt)})", "input_validator")
        raise InputValidationError(
            "Input contains disallowed patterns", field="prompt"
        )

    return prompt


def validate_session_id(session_id: Optional[str]) -> Optional[str]:
    """Validate a session ID format.

    Args:
        session_id: Session ID string or None

    Returns:
        Validated session ID or None

    Raises:
        InputValidationError: If the session ID format is invalid
    """
    if session_id is None:
        return None

    session_id = session_id.strip()

    if len(session_id) > MAX_SESSION_ID_LENGTH:
        raise InputValidationError(
            "Session ID is too long", field="session_id"
        )

    if not re.match(r"^[a-zA-Z0-9\-_]+$", session_id):
        raise InputValidationError(
            "Session ID contains invalid characters", field="session_id"
        )

    return session_id


def validate_ticket_key(ticket_key: Optional[str]) -> Optional[str]:
    """Validate a JIRA ticket key format.

    Args:
        ticket_key: Ticket key like 'PROJ-123'

    Returns:
        Validated ticket key or None

    Raises:
        InputValidationError: If the ticket key format is invalid
    """
    if ticket_key is None:
        return None

    ticket_key = ticket_key.strip().upper()

    if len(ticket_key) > MAX_TICKET_KEY_LENGTH:
        raise InputValidationError(
            "Ticket key is too long", field="ticket_key"
        )

    if not re.match(r"^[A-Z]{1,10}-\d{1,6}$", ticket_key):
        raise InputValidationError(
            f"Invalid ticket key format: {ticket_key}", field="ticket_key"
        )

    return ticket_key
