"""Environment-backed configuration for Prithvi's production wiring.

Only the three numbers that a deployment might genuinely want to move. Every
other boundary arrives by injection, so this module is read exactly once, by
``wsgi``, and never by anything under test.

A malformed value fails at import rather than at the first request. A NAS that
will not start is a problem someone fixes in a minute; a NAS that silently
accepted ``PRITHVI_MAX_SVG_BYTES=5MB`` as a default is one they find out about
much later.
"""

import os

DEFAULT_MAX_SVG_BYTES = 5 * 1024 * 1024
DEFAULT_MAP_REVISIONS_KEEP = 5
DEFAULT_PIN_REVISIONS_KEEP = 20


def get_max_svg_bytes() -> int:
    return _positive("PRITHVI_MAX_SVG_BYTES", DEFAULT_MAX_SVG_BYTES)


def get_map_revisions_keep() -> int:
    return _positive("PRITHVI_MAP_REVISIONS_KEEP", DEFAULT_MAP_REVISIONS_KEEP)


def get_pin_revisions_keep() -> int:
    return _positive("PRITHVI_PIN_REVISIONS_KEEP", DEFAULT_PIN_REVISIONS_KEEP)


def _positive(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a whole number, got {raw!r}.") from exc
    if value < 1:
        raise RuntimeError(f"{name} must be at least 1, got {value}.")
    return value
