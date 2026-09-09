"""How a diorama is presented, kept apart from what it is made of.

Geometry lives in the ``.glb``; everything about *showing* it lives here, in a
small versioned document beside the model. The split earns its keep the first
time someone wants the camera a little higher: that is an edit to a few numbers,
not a re-upload of a multi-megabyte binary, and the model's bytes stay
content-addressed and immutable while the view of it is versioned like any other
article field.

Values are **refused, not clamped**. A form that silently turns a typed 250 into
100 has told the writer their input was accepted when it was replaced; saying so
costs one error message and no confusion. The editor constrains these controls
anyway, so a value arriving out of range came from a script, which is precisely
the caller that benefits from being told.

Pure: a dict in, a normalised dict out. No Flask, no Mongo, no rendering.
"""

from typing import Any

from .errors import InvalidDiorama

SCHEMA_VERSION = 1

# A still scene, viewed from a slowly turning camera. The defaults are the ones
# the Prithvi round settled on as reading well for a landmark-sized model.
DEFAULTS = {
    "camera_azimuth": 35,
    "camera_elevation": 25,
    "rotation_speed": 6,
    "auto_rotate": True,
}

MAX_TITLE = 120
MAX_DESCRIPTION = 1000
MAX_LIGHTS = 8
LIGHT_TYPES = ("point", "spot")

_ELEVATION = (-89, 89)     # ±90 puts the camera on the pole and loses its up-vector
_ROTATION_SPEED = (0, 30)  # a full turn in twelve seconds is already brisk
_INTENSITY = (0.0, 20.0)
_POSITION = (-1000.0, 1000.0)


def validate_manifest(payload: Any) -> dict:
    """Return the normalised presentation manifest, or say what is wrong."""
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise InvalidDiorama("The presentation manifest must be an object.")

    unknown = set(payload) - {
        "schema_version", "title", "description", "camera_azimuth",
        "camera_elevation", "rotation_speed", "auto_rotate", "lights",
    }
    if unknown:
        raise InvalidDiorama(
            "The manifest has fields this version does not understand: "
            + ", ".join(sorted(unknown))
        )

    version = payload.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise InvalidDiorama(
            f"This is a version {SCHEMA_VERSION} manifest, not {version!r}."
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "title": _text(payload.get("title"), "title", MAX_TITLE, required=True),
        "description": _text(
            payload.get("description"), "description", MAX_DESCRIPTION
        ),
        # Azimuth wraps rather than being refused: 370° and 10° name the same
        # camera, and there is nothing to warn a writer about.
        "camera_azimuth": _degrees(payload.get("camera_azimuth")),
        "camera_elevation": _bounded_int(
            payload.get("camera_elevation"), "camera_elevation", _ELEVATION
        ),
        "rotation_speed": _bounded_number(
            payload.get("rotation_speed"), "rotation_speed", _ROTATION_SPEED
        ),
        "auto_rotate": _flag(payload.get("auto_rotate"), "auto_rotate"),
        "lights": _lights(payload.get("lights")),
    }


def _text(value, field: str, limit: int, required: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise InvalidDiorama(f"'{field}' must be text.")
    text = " ".join(value.split()) if field == "title" else value.strip()
    if required and not text:
        raise InvalidDiorama(f"A diorama needs a {field}.")
    if len(text) > limit:
        raise InvalidDiorama(f"'{field}' must be at most {limit} characters.")
    return text


def _number(value, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidDiorama(f"'{field}' must be a number.")
    return float(value)


def _degrees(value) -> int:
    if value is None:
        return DEFAULTS["camera_azimuth"]
    return int(_number(value, "camera_azimuth")) % 360


def _bounded_int(value, field: str, bounds: tuple[int, int]) -> int:
    if value is None:
        return DEFAULTS[field]
    number = int(_number(value, field))
    return _within(number, field, bounds)


def _bounded_number(value, field: str, bounds: tuple[float, float]) -> float:
    if value is None:
        return DEFAULTS[field]
    return _within(_number(value, field), field, bounds)


def _within(number, field: str, bounds):
    low, high = bounds
    if not low <= number <= high:
        raise InvalidDiorama(f"'{field}' must be between {low} and {high}.")
    return number


def _flag(value, field: str) -> bool:
    if value is None:
        return DEFAULTS[field]
    if not isinstance(value, bool):
        raise InvalidDiorama(f"'{field}' must be true or false.")
    return value


def _lights(value) -> list[dict]:
    """Optional local lights. The scene has a sun already; these are lanterns.

    Only the two types the viewer builds are accepted. Directional lights are
    left out deliberately: a second sun fights the first and flattens the
    shadows the scene is lit for.
    """
    if value is None:
        return []
    if not isinstance(value, list):
        raise InvalidDiorama("'lights' must be a list.")
    if len(value) > MAX_LIGHTS:
        raise InvalidDiorama(f"A diorama has at most {MAX_LIGHTS} local lights.")
    return [_light(entry, index) for index, entry in enumerate(value)]


def _light(entry, index: int) -> dict:
    if not isinstance(entry, dict):
        raise InvalidDiorama(f"Light {index + 1} must be an object.")
    unknown = set(entry) - {"type", "x", "y", "z", "color", "intensity"}
    if unknown:
        raise InvalidDiorama(
            f"Light {index + 1} has unknown fields: {', '.join(sorted(unknown))}"
        )
    kind = entry.get("type")
    if kind not in LIGHT_TYPES:
        raise InvalidDiorama(
            f"Light {index + 1} must be one of: {', '.join(LIGHT_TYPES)}."
        )
    return {
        "type": kind,
        "x": _within(_number(entry.get("x", 0), "x"), "x", _POSITION),
        "y": _within(_number(entry.get("y", 0), "y"), "y", _POSITION),
        "z": _within(_number(entry.get("z", 0), "z"), "z", _POSITION),
        "color": _color(entry.get("color"), index),
        "intensity": _within(
            _number(entry.get("intensity", 1), "intensity"), "intensity", _INTENSITY
        ),
    }


def _color(value, index: int) -> str:
    if value is None:
        return "#ffffff"
    if not isinstance(value, str):
        raise InvalidDiorama(f"Light {index + 1} has a colour that is not text.")
    text = value.strip().lower()
    if not text.startswith("#"):
        text = f"#{text}"
    body = text[1:]
    if len(body) != 6 or any(character not in "0123456789abcdef" for character in body):
        raise InvalidDiorama(
            f"Light {index + 1} needs a colour like #ffcc88."
        )
    return f"#{body}"
