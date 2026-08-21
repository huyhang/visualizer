"""Pure checks on the identifiers and bodies Prithvi accepts.

No Flask, no Mongo, no SVG parsing (that has its own module). Everything here
takes plain values and either returns a value object or raises the one error
that names what was wrong.
"""

import math
import re
from typing import Any

from .errors import (
    InvalidArticleAddress,
    InvalidMapName,
    InvalidPosition,
    InvalidScale,
    InvalidWorld,
    PositionOutOfBounds,
)
from .models import Position, Scale, ViewBox

# Map names appear in URLs, in Mongo keys and in the composite key's separator
# space, so they are kept to the boring characters. Akasha's own database and
# article names are validated by Akasha; Prithvi only has to refuse the ones it
# would itself mangle.
_MAP_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

MAX_ADDRESS_LENGTH = 255
MAX_UNIT_LENGTH = 32


def validate_world(world: str) -> str:
    """A world is an Akasha database; the reserved ones are not addressable."""
    if not world or world.startswith("_"):
        raise InvalidWorld("The world name is missing or reserved.")
    return world


def validate_map_name(name: str) -> str:
    if not _MAP_NAME.fullmatch(name or ""):
        raise InvalidMapName(
            "A map name is 1-128 characters of letters, digits, dots, "
            "underscores or hyphens, starting with a letter or digit.",
            evidence={"name": name},
        )
    return name


def validate_article_address(collection: str, article_id: str) -> None:
    if not collection or not article_id:
        raise InvalidArticleAddress("Collection and article id must be non-empty.")
    if len(collection) > MAX_ADDRESS_LENGTH or len(article_id) > MAX_ADDRESS_LENGTH:
        raise InvalidArticleAddress(
            f"Collection and article id are at most {MAX_ADDRESS_LENGTH} characters."
        )


def validate_position(payload: Any, view_box: ViewBox) -> Position:
    """A pin body is exactly ``x`` and ``y``, inside the map's own rectangle.

    Unknown keys are refused rather than ignored: a client that sends ``lat`` and
    ``lng`` has misunderstood something, and silently storing nothing would let
    it keep misunderstanding for a while.
    """
    numbers = _exactly(payload, ("x", "y"), InvalidPosition, "A pin body")
    position = Position(numbers["x"], numbers["y"])
    if not view_box.contains(position):
        raise PositionOutOfBounds(
            "A pin must sit inside its map's viewBox.",
            evidence={"position": position.to_dict(), "view_box": view_box.to_list()},
        )
    return position


def validate_scale(payload: Any) -> Scale:
    """A scale is a positive distance across the map, and what to call it."""
    if not isinstance(payload, dict):
        raise InvalidScale("A scale body must be a JSON object.")
    unexpected = sorted(set(payload) - {"across", "unit"})
    if unexpected or "across" not in payload or "unit" not in payload:
        raise InvalidScale(
            "A scale body must contain exactly 'across' and 'unit'.",
            evidence={"unexpected": unexpected},
        )
    across = _finite_number(payload["across"], "across", InvalidScale)
    if across <= 0:
        raise InvalidScale("'across' must be greater than zero.")
    unit = payload["unit"]
    if not isinstance(unit, str) or not unit.strip():
        raise InvalidScale("'unit' must be a non-empty string.")
    if len(unit) > MAX_UNIT_LENGTH:
        raise InvalidScale(f"'unit' is at most {MAX_UNIT_LENGTH} characters.")
    return Scale(across, unit.strip())


def _exactly(payload: Any, keys: tuple[str, ...], error, what: str) -> dict:
    """Read exactly ``keys`` off a JSON object as finite numbers."""
    if not isinstance(payload, dict):
        raise error(f"{what} must be a JSON object.")
    missing = sorted(set(keys) - set(payload))
    unexpected = sorted(set(payload) - set(keys))
    if missing or unexpected:
        raise error(
            f"{what} must contain exactly {' and '.join(repr(k) for k in keys)}.",
            evidence={"missing": missing, "unexpected": unexpected},
        )
    return {key: _finite_number(payload[key], key, error) for key in keys}


def _finite_number(value: Any, name: str, error) -> float:
    # ``bool`` is an ``int`` in Python, and ``True`` is not a coordinate.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise error(f"'{name}' must be a finite number.")
    number = float(value)
    if not math.isfinite(number):
        raise error(f"'{name}' must be a finite number.")
    return number
