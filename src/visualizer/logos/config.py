"""Environment-backed runtime settings for Logos.

Invalid values stop the process at import rather than being coerced to a
default: silently keeping one revision when the operator asked for a hundred is
the kind of setting whose failure only shows up when someone needs the history.
"""

import os

DEFAULT_SECTION_REVISIONS_KEEP = 20


def get_section_revisions_keep() -> int:
    raw = os.environ.get("LOGOS_SECTION_REVISIONS_KEEP")
    if raw is None or not raw.strip():
        return DEFAULT_SECTION_REVISIONS_KEEP
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"LOGOS_SECTION_REVISIONS_KEEP must be a whole number, got {raw!r}."
        ) from exc
    if value < 1:
        raise RuntimeError("LOGOS_SECTION_REVISIONS_KEEP must be at least 1.")
    return value
