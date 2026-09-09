"""Guards shared by Akasha's route modules.

``app.py`` and ``media_routes.py`` both hang routes off the same
``/databases/<database>/…`` prefix, so both need the same namespace guard and
the same reading of a boolean query flag. They live here rather than in either
module because ``app.py`` imports ``media_routes`` -- the reverse import would
be a cycle, and the copy that produced was already drifting.
"""

from flask import request

from .errors import ReservedName

# Spellings that count as "yes". An allowlist, not a denylist: both flags this
# serves (``?purge=``, ``?force=``) destroy something, so an unrecognised value
# must read as *no*. The documented spelling everywhere is ``=1``.
_TRUTHY = ("1", "true", "yes", "on")


def reject_reserved(database: str) -> None:
    """Block access to internal/reserved databases (e.g. the auth store)."""
    if database.startswith("_"):
        raise ReservedName(f"Database '{database}' is reserved and not accessible.")


def flag_arg(name: str) -> bool:
    """A boolean query flag, true only when spelled as an explicit yes."""
    return request.args.get(name, "").strip().lower() in _TRUTHY
