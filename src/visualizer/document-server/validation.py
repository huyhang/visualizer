"""Pure validation helpers.

These functions have no dependency on Flask or MongoDB so they can be unit
tested in isolation.
"""

from typing import Any

from errors import InvalidDocument, InvalidSearch


def validate_document(payload: Any) -> dict:
    """Return ``payload`` if it is a valid JSON dictionary.

    A document must be a JSON object (mapping). Anything else -- ``None`` from a
    body that failed to parse, a list, a string, a number -- is rejected.
    """
    if not isinstance(payload, dict):
        raise InvalidDocument("Document must be a valid JSON dictionary.")
    return payload


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
