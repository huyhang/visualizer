"""Domain errors for Chronos.

Mirrors ``document_server.errors``: each error carries an HTTP ``status_code``
so the web layer can serialize it without knowing the details, plus a stable
machine ``code`` and optional structured ``evidence`` (the shared "finding"
vocabulary from the design, used by errors, ``status`` verdicts and
``/validate`` alike).

Note the *story-logic* rules (temporal conflict, ordering, convergence) are
deliberately **not** errors: under the all-soft model they never fail a write,
they are reported as findings (see ``book_rules``/``presenters``).
"""

from typing import Any


class ChronosError(Exception):
    """Base class for all Chronos domain errors."""

    status_code = 500
    code = "CHRONOS_ERROR"

    def __init__(self, message: str, evidence: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.evidence = evidence or {}

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"error": self.message, "code": self.code}
        if self.evidence:
            body["evidence"] = self.evidence
        return body


# -- referential / structural (hard: these reject the write) -----------------


class InvalidEvent(ChronosError):
    """Raised when an event payload is malformed."""

    status_code = 400
    code = "INVALID_EVENT"


class InvalidTimeframe(ChronosError):
    """Raised when ticks are non-integer or ``start_tick > end_tick``."""

    status_code = 400
    code = "INVALID_TIMEFRAME"


class InvalidPlotline(ChronosError):
    """Raised for an empty event list / empty goals / unknown event reference."""

    status_code = 400
    code = "INVALID_PLOTLINE"


class InvalidBook(ChronosError):
    """Raised when a book payload is malformed."""

    status_code = 400
    code = "INVALID_BOOK"


class EntityNotFound(ChronosError):
    """Raised when an EntityRef does not exist (or is unreadable) upstream."""

    status_code = 422
    code = "ENTITY_NOT_FOUND"


# -- not found ---------------------------------------------------------------


class BookNotFound(ChronosError):
    status_code = 404
    code = "BOOK_NOT_FOUND"


class PlotlineNotFound(ChronosError):
    status_code = 404
    code = "PLOTLINE_NOT_FOUND"


class EventNotFound(ChronosError):
    status_code = 404
    code = "EVENT_NOT_FOUND"


# -- conflicts (409) ---------------------------------------------------------


class RevisionConflict(ChronosError):
    """Raised when an ``If-Match``/``_rev`` precondition is stale (OCC)."""

    status_code = 409
    code = "REVISION_CONFLICT"


class EventInUse(ChronosError):
    """Raised when deleting an event a plotline still lists (without detach)."""

    status_code = 409
    code = "EVENT_IN_USE"


class TerminusInUse(ChronosError):
    """Raised when deleting a book's terminus before a new one is designated."""

    status_code = 409
    code = "TERMINUS_IN_USE"


class InvalidRevision(ChronosError):
    """Raised when an ``If-Match``/``_rev`` precondition value is malformed."""

    status_code = 400
    code = "INVALID_REVISION"


class AlreadyExists(ChronosError):
    """Raised when creating a book/plotline/event whose id is already taken."""

    status_code = 409
    code = "ALREADY_EXISTS"


# -- auth --------------------------------------------------------------------


class Forbidden(ChronosError):
    status_code = 403
    code = "FORBIDDEN"
