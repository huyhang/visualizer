"""Pure validation for Logos identifiers, metadata and ordering.

Nothing here touches the database or Flask, and nothing mutates what it is
given: every function builds and returns a fresh record, so a rejected request
leaves no trace and an accepted one shares no structure with the request body.

Metadata is deliberately small. A volume has a title and an optional overview; a
section adds its kind and the Chronos events it realises. Anything that can be
derived from order or content -- numbers, counts, links -- is computed on read
rather than stored, so it cannot fall out of date.
"""

import re
from typing import Any

from .errors import (
    InvalidIdentifier,
    InvalidOrder,
    InvalidSection,
    InvalidVolume,
)
from .models import Section, Volume
from .richtext import validate_document

SECTION_KINDS = ("prologue", "chapter", "epilogue", "glossary")
# One prologue, one epilogue and one glossary per volume; chapters are the
# sequence, so they are the only kind a volume may hold many of.
SINGLETON_SECTION_KINDS = frozenset({"prologue", "epilogue", "glossary"})
NUMBERED_SECTION_KIND = "chapter"

MAX_TITLE_LENGTH = 300
MAX_OVERVIEW_LENGTH = 10_000

# A volume or section id becomes a URL path segment, so it is kept to characters
# that need no escaping and cannot be confused with the store's key separator.
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def validate_identifier(value: Any, what: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise InvalidIdentifier(
            f"A {what} id must be 1-128 letters, digits, dots, underscores or "
            "hyphens, starting with a letter or digit.",
            evidence={what: value},
        )
    return value


def validate_volume_payload(volume_id: str, payload: Any) -> Volume:
    validate_identifier(volume_id, "volume")
    body = _mapping(payload, InvalidVolume, "A volume body")
    _only(body, {"title", "overview"}, InvalidVolume, "volume")
    return Volume(
        volume_id,
        _required_text(body.get("title"), "title", MAX_TITLE_LENGTH, InvalidVolume),
        _optional_text(
            body.get("overview", ""), "overview", MAX_OVERVIEW_LENGTH, InvalidVolume
        ),
    )


def validate_section_payload(section_id: str, payload: Any) -> Section:
    validate_identifier(section_id, "section")
    body = _mapping(payload, InvalidSection, "A section body")
    _only(
        body,
        {"kind", "title", "overview", "event_ids", "document"},
        InvalidSection,
        "section",
    )
    kind = body.get("kind")
    if kind not in SECTION_KINDS:
        raise InvalidSection(
            "'kind' must name a supported section kind.",
            evidence={"kind": kind, "supported": list(SECTION_KINDS)},
        )
    if "document" not in body:
        raise InvalidSection("A section requires a 'document'.")
    return Section(
        section_id,
        kind,
        validate_document(body["document"]),
        _title(body.get("title")),
        _optional_text(
            body.get("overview", ""), "overview", MAX_OVERVIEW_LENGTH, InvalidSection
        ),
        _id_list(body.get("event_ids", []), "event_ids", InvalidSection),
    )


def validate_order(payload: Any, field: str, known: list[str]) -> list[str]:
    """Read a reordering: the same ids as ``known``, in a new arrangement."""
    body = _mapping(payload, InvalidOrder, "An order body")
    _only(body, {field}, InvalidOrder, "order")
    requested = _id_list(body.get(field), field, InvalidOrder)
    missing = sorted(set(known) - set(requested))
    unknown = sorted(set(requested) - set(known))
    if missing or unknown:
        raise InvalidOrder(
            f"'{field}' must list every current id exactly once.",
            evidence={"missing": missing, "unknown": unknown},
        )
    return requested


def _title(value: Any) -> str | None:
    if value is None:
        return None
    title = _optional_text(value, "title", MAX_TITLE_LENGTH, InvalidSection)
    return title.strip() or None


def _mapping(value: Any, error, what: str) -> dict:
    if not isinstance(value, dict):
        raise error(f"{what} must be a JSON object.")
    return value


def _only(body: dict, allowed: set[str], error, what: str) -> None:
    unexpected = sorted(set(body) - allowed)
    if unexpected:
        raise error(
            f"A {what} body contains unsupported fields.",
            evidence={"unexpected": unexpected},
        )


def _required_text(value: Any, field: str, maximum: int, error) -> str:
    if not isinstance(value, str) or not value.strip():
        raise error(f"'{field}' must be a non-empty string.")
    text = value.strip()
    if len(text) > maximum:
        raise error(
            f"'{field}' must be at most {maximum} characters.",
            evidence={"characters": len(text), "max": maximum},
        )
    return text


def _optional_text(value: Any, field: str, maximum: int, error) -> str:
    if not isinstance(value, str):
        raise error(f"'{field}' must be a string.")
    if len(value) > maximum:
        raise error(
            f"'{field}' must be at most {maximum} characters.",
            evidence={"characters": len(value), "max": maximum},
        )
    return value


def _id_list(value: Any, field: str, error) -> list[str]:
    if not isinstance(value, list):
        raise error(f"'{field}' must be a list of ids.")
    if not all(isinstance(item, str) and item for item in value):
        raise error(f"'{field}' must be a list of non-empty ids.")
    seen: set[str] = set()
    repeated: set[str] = set()
    for item in value:
        if item in seen:
            repeated.add(item)
        seen.add(item)
    duplicates = sorted(repeated)
    if duplicates:
        raise error(
            f"'{field}' contains duplicate ids.", evidence={"duplicates": duplicates}
        )
    return list(value)
