"""Domain errors for Akasha.

Each error carries an HTTP ``status_code`` so the web layer can translate it
into a response without knowing the details of what went wrong.
"""


class AkashaError(Exception):
    """Base class for all akasha domain errors."""

    status_code = 500

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class InvalidDocument(AkashaError):
    """Raised when a payload is not a valid JSON dictionary."""

    status_code = 400


class InvalidSearch(AkashaError):
    """Raised when search parameters are missing or malformed."""

    status_code = 400


class DatabaseNotFound(AkashaError):
    """Raised when addressing a database that does not exist."""

    status_code = 404


class CollectionNotFound(AkashaError):
    """Raised when addressing a collection that does not exist."""

    status_code = 404


class DocumentNotFound(AkashaError):
    """Raised when a document does not exist for the given id."""

    status_code = 404


class CollectionAlreadyExists(AkashaError):
    """Raised when creating a collection that already exists."""

    status_code = 409


class DocumentAlreadyExists(AkashaError):
    """Raised when creating a document whose id is already taken."""

    status_code = 409


class InvalidCredentials(AkashaError):
    """Raised when a login attempt has bad or missing credentials."""

    status_code = 400


class UserAlreadyExists(AkashaError):
    """Raised when registering a username that is already taken."""

    status_code = 409


class EmailAlreadyExists(AkashaError):
    """Raised when registering an email address that is already in use."""

    status_code = 409


class InvalidEmail(AkashaError):
    """Raised when an email address is missing or malformed."""

    status_code = 400


class UserNotFound(AkashaError):
    """Raised when addressing a user account that does not exist."""

    status_code = 404


class Unauthorized(AkashaError):
    """Raised when a request is not authenticated."""

    status_code = 401


class Forbidden(AkashaError):
    """Raised when an authenticated user lacks permission for an action."""

    status_code = 403


class ReservedName(AkashaError):
    """Raised when a caller tries to use a reserved (internal) name."""

    status_code = 400


class RevisionConflict(AkashaError):
    """Raised when a write's expected revision does not match the stored one.

    The optimistic-concurrency guard: someone else changed the document since
    the caller last read it, so the write is refused rather than silently
    clobbering their change.
    """

    status_code = 409


class VersionNotFound(AkashaError):
    """Raised when addressing a document version that is not retained."""

    status_code = 404


class InvalidRevision(AkashaError):
    """Raised when an If-Match / _rev precondition value is malformed."""

    status_code = 400
