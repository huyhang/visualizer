"""Domain errors for Prithvi.

Mirrors ``akasha.errors`` and ``chronos.errors``: every error carries an HTTP
``status_code`` so the web layer can serialize it without knowing what went
wrong, a stable machine ``code`` a client can branch on, and optional structured
``evidence`` naming the values that actually failed.

Every distinct failure gets its own code, including the dull ones. It is
tempting to let a mistyped map name come back as ``INVALID_SVG`` because both
arrive on the same route, but then a client cannot tell a bad name from a bad
drawing without reading the prose -- and prose is the one part of a response
that is allowed to change.

The set of codes here is the contract: ``docs/prithvi/openapi.json`` enumerates
it, and a contract test fails if the two ever drift apart.
"""

from typing import Any


class PrithviError(Exception):
    """Base class for all Prithvi domain errors."""

    status_code = 500
    code = "PRITHVI_ERROR"

    def __init__(self, message: str, evidence: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.evidence = evidence or {}

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"error": self.message, "code": self.code}
        if self.evidence:
            body["evidence"] = self.evidence
        return body


# -- malformed input (the caller can fix these by sending something else) -----


class InvalidWorld(PrithviError):
    """The world segment is empty or names a reserved database."""

    status_code = 400
    code = "INVALID_WORLD"


class InvalidMapName(PrithviError):
    """The map segment is not a usable name."""

    status_code = 400
    code = "INVALID_MAP_NAME"


class InvalidArticleAddress(PrithviError):
    """The collection or article segment is empty or implausibly long."""

    status_code = 400
    code = "INVALID_ARTICLE_ADDRESS"


class InvalidSvg(PrithviError):
    """The upload is not a well-formed SVG we can place pins on."""

    status_code = 400
    code = "INVALID_SVG"


class InvalidPosition(PrithviError):
    """A pin body is not exactly two finite numbers."""

    status_code = 400
    code = "INVALID_POSITION"


class InvalidScale(PrithviError):
    """A scale body is not a positive distance with a unit."""

    status_code = 400
    code = "INVALID_SCALE"


class InvalidRevision(PrithviError):
    """An ``If-Match`` header that is not a concrete revision number."""

    status_code = 400
    code = "INVALID_REVISION"


class UnsupportedMediaType(PrithviError):
    """An SVG upload arrived under some other content type."""

    status_code = 415
    code = "UNSUPPORTED_MEDIA_TYPE"


class SvgTooLarge(PrithviError):
    """The upload is over the configured byte cap."""

    status_code = 413
    code = "SVG_TOO_LARGE"


class PreconditionRequired(PrithviError):
    """A mutation arrived without the ``If-Match`` it must carry."""

    status_code = 428
    code = "PRECONDITION_REQUIRED"


# -- referential (the request is well formed, the world disagrees) ------------


class PositionOutOfBounds(PrithviError):
    """A pin was placed outside its map's ``viewBox``."""

    status_code = 422
    code = "POSITION_OUT_OF_BOUNDS"


class ArticleNotFound(PrithviError):
    """The pin names an Akasha article that does not exist."""

    status_code = 422
    code = "ARTICLE_NOT_FOUND"


class WorldNotFound(PrithviError):
    """No such Akasha database."""

    status_code = 404
    code = "WORLD_NOT_FOUND"


class MapNotFound(PrithviError):
    """No such map, or it is currently a tombstone."""

    status_code = 404
    code = "MAP_NOT_FOUND"


class PinNotFound(PrithviError):
    """No such pin -- or one the caller may not know about.

    Also raised, deliberately, when the reader lacks access to the article a pin
    names: telling them "forbidden" would confirm that a pin exists there.
    """

    status_code = 404
    code = "PIN_NOT_FOUND"


class RevisionNotRetained(PrithviError):
    """That revision has aged out of the retention window."""

    status_code = 404
    code = "REVISION_NOT_RETAINED"


# -- conflict and permission --------------------------------------------------


class AlreadyExists(PrithviError):
    """A live record already holds that name."""

    status_code = 409
    code = "ALREADY_EXISTS"


class RevisionConflict(PrithviError):
    """Someone else wrote first; the caller's revision is stale."""

    status_code = 409
    code = "REVISION_CONFLICT"


class ViewBoxLocked(PrithviError):
    """A replacement SVG changes the coordinate space a live pin sits in."""

    status_code = 409
    code = "VIEWBOX_LOCKED"


class Forbidden(PrithviError):
    """The caller's Akasha grants do not reach this world or article."""

    status_code = 403
    code = "FORBIDDEN"
