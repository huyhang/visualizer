"""Pure validation helpers for the auth layer.

No dependency on Flask or MongoDB, so this unit-tests in isolation.
"""

import re
from typing import Any

from .errors import InvalidEmail

# Deliberately permissive: one "@", a non-empty local part, and a dotted domain.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_email(email: Any) -> str:
    """Return a normalised (trimmed, lower-cased) email or raise ``InvalidEmail``."""
    if not isinstance(email, str) or not email.strip():
        raise InvalidEmail("An email address is required.")
    normalised = email.strip().lower()
    if not _EMAIL_RE.match(normalised):
        raise InvalidEmail("Enter a valid email address.")
    return normalised
