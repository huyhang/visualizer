"""Pure validation helpers.

These functions have no dependency on Flask or MongoDB so they can be unit
tested in isolation.
"""

import re
from typing import Any

from .errors import InvalidDocument, InvalidName, InvalidSearch

# Characters MongoDB will not take in a database or collection name (and the
# space, which it would, but which no URL here should carry). The editor's
# dialogs refuse the same set, so this answers only callers that skip them.
_BAD_NAME = re.compile(r'[/\\. "$*<>:|?\x00]')
_SEPARATORS = re.compile(r"[-_\s]+")


def validate_namespace_name(name: str, what: str) -> None:
    """Refuse a world or category name MongoDB cannot hold, or that is reserved."""
    if not name:
        raise InvalidName(f"Give the {what} a name.")
    if name.startswith("_"):
        raise InvalidName(f"{what.capitalize()} names starting with '_' are reserved.")
    if _BAD_NAME.search(name):
        raise InvalidName(
            f"A {what} name cannot contain spaces or / \\ . \" $ * < > : | ?"
        )


def namespace_key(name: str) -> str:
    """What two names have in common when they would read as the same one.

    Case and separators are how a name is printed, not which name it is --
    ``Characters``, ``characters`` and ``CHARACTERS`` all title as
    "Characters" -- so a new name is refused when its key matches an
    existing name's.
    """
    return _SEPARATORS.sub("-", name).strip("-").casefold()

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

    The article's image fields (``gallery``, ``profile_image``) are deliberately
    *not* policed here. Field names in this store belong to the writer: an
    article that has always carried a ``gallery`` list of wing names must keep
    saving. The reader claims those two names only when their contents parse as
    image references, and ignores them otherwise, so an inconsistent document
    degrades instead of being refused.
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
