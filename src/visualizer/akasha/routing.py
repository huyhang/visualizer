"""Guards and request plumbing shared by Akasha's route modules.

Every route module hangs routes off the same ``/databases/<database>/…``
prefix, so they share the URL templates, the namespace guard, the reading of a
boolean query flag and of an ``If-Match`` precondition. They live here rather
than in any one module because ``app.py`` imports all of them -- the reverse
import would be a cycle, and the copy that produced was already drifting.
"""

from flask import jsonify, request

from .errors import InvalidRevision, ReservedName

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


COLLECTION_ROUTE = "/databases/<database>/collections/<collection>"
DOC_ROUTE = "/databases/<database>/collections/<collection>/documents/<doc_id>"
SEARCH_ROUTE = "/databases/<database>/collections/<collection>/search"


def expected_rev() -> int | None:
    """Parse the optimistic-concurrency precondition the client sent, if any.

    Accepts an ``If-Match`` header (an ETag such as ``"5"``, or ``*`` for an
    unconditional write) or a ``_rev`` query param. Returns the expected
    revision as an int, or ``None`` for an unconditional write. The browser
    editor always sends one; raw API callers may omit it.
    """
    raw = request.headers.get("If-Match")
    if raw is None:
        raw = request.args.get("_rev")
    if raw is None:
        return None
    raw = raw.strip().strip('"')
    if raw in ("", "*"):
        return None
    try:
        return int(raw)
    except ValueError:
        raise InvalidRevision(f"Invalid If-Match/_rev precondition: {raw!r}.")


def document_response(result: dict, status: int = 200):
    """JSON-encode a document result and expose its rev as an ``ETag`` header."""
    response = jsonify(result)
    response.status_code = status
    if "rev" in result:
        response.headers["ETag"] = f'"{result["rev"]}"'
    return response


def int_arg(name: str, default: int) -> int:
    """A positive integer query param, falling back rather than 400-ing.

    A malformed ``?page=`` comes from a hand-edited URL, not from a bug worth
    interrupting someone's browsing over.
    """
    try:
        return int(request.args.get(name, ""))
    except ValueError:
        return default
