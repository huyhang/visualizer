"""Pure validation helpers.

These functions have no dependency on Flask or MongoDB so they can be unit
tested in isolation.
"""

import re
from typing import Any

from .errors import InvalidDocument, InvalidEmail, InvalidSearch

# Deliberately permissive: one "@", a non-empty local part, and a dotted domain.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# A document value must be a scalar or a flat array of scalars. ``bool`` is a
# subclass of ``int`` and is intentionally allowed as a scalar.
_SCALAR_TYPES = (str, int, float, bool, type(None))


def _is_scalar(value: Any) -> bool:
    return isinstance(value, _SCALAR_TYPES)


def _is_flat_array(value: Any) -> bool:
    return isinstance(value, list) and all(_is_scalar(v) for v in value)


def validate_document(payload: Any) -> dict:
    """Return ``payload`` if it is a valid, *flat* JSON dictionary.

    A document must be a JSON object (mapping) whose every value is either a
    scalar (``str``, ``int``, ``float``, ``bool``, ``null``) or a flat array of
    scalars. Nested objects and nested arrays are rejected -- this keeps the
    article editor and the version diff simple and intuitive. Anything that is
    not a mapping (``None`` from a body that failed to parse, a list, a string,
    a number) is rejected too.
    """
    if not isinstance(payload, dict):
        raise InvalidDocument("Document must be a valid JSON dictionary.")
    for key, value in payload.items():
        if not (_is_scalar(value) or _is_flat_array(value)):
            raise InvalidDocument(
                f"Field '{key}' must be a scalar or a flat array of scalars; "
                "nested objects and nested arrays are not allowed."
            )
    return payload


def validate_email(email: Any) -> str:
    """Return a normalised (trimmed, lower-cased) email or raise ``InvalidEmail``."""
    if not isinstance(email, str) or not email.strip():
        raise InvalidEmail("An email address is required.")
    normalised = email.strip().lower()
    if not _EMAIL_RE.match(normalised):
        raise InvalidEmail("Enter a valid email address.")
    return normalised


def validate_search_terms(key: str | None, text: str | None) -> tuple[str | None, str | None]:
    """Normalise and validate search terms.

    At least one of ``key`` or ``text`` must be a non-empty value. Empty strings
    are treated as "not provided".
    """
    key = key or None
    text = text or None
    if key is None and text is None:
        raise InvalidSearch("Provide at least one of 'key' or 'text'.")
    return key, text
