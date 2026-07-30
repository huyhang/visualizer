"""Domain errors for the document server.

Each error carries an HTTP ``status_code`` so the web layer can translate it
into a response without knowing the details of what went wrong.
"""


class DocumentServerError(Exception):
    """Base class for all document-server domain errors."""

    status_code = 500

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class InvalidDocument(DocumentServerError):
    """Raised when a payload is not a valid JSON dictionary."""

    status_code = 400


class InvalidSearch(DocumentServerError):
    """Raised when search parameters are missing or malformed."""

    status_code = 400


class DatabaseNotFound(DocumentServerError):
    """Raised when addressing a database that does not exist."""

    status_code = 404


class CollectionNotFound(DocumentServerError):
    """Raised when addressing a collection that does not exist."""

    status_code = 404


class DocumentNotFound(DocumentServerError):
    """Raised when a document does not exist for the given id."""

    status_code = 404


class CollectionAlreadyExists(DocumentServerError):
    """Raised when creating a collection that already exists."""

    status_code = 409


class DocumentAlreadyExists(DocumentServerError):
    """Raised when creating a document whose id is already taken."""

    status_code = 409


class InvalidCredentials(DocumentServerError):
    """Raised when a login attempt has bad or missing credentials."""

    status_code = 400


class UserAlreadyExists(DocumentServerError):
    """Raised when registering a username that is already taken."""

    status_code = 409


class EmailAlreadyExists(DocumentServerError):
    """Raised when registering an email address that is already in use."""

    status_code = 409


class InvalidEmail(DocumentServerError):
    """Raised when an email address is missing or malformed."""

    status_code = 400


class UserNotFound(DocumentServerError):
    """Raised when addressing a user account that does not exist."""

    status_code = 404


class Unauthorized(DocumentServerError):
    """Raised when a request is not authenticated."""

    status_code = 401


class Forbidden(DocumentServerError):
    """Raised when an authenticated user lacks permission for an action."""

    status_code = 403


class ReservedName(DocumentServerError):
    """Raised when a caller tries to use a reserved (internal) name."""

    status_code = 400


class RevisionConflict(DocumentServerError):
    """Raised when a write's expected revision does not match the stored one.

    The optimistic-concurrency guard: someone else changed the document since
    the caller last read it, so the write is refused rather than silently
    clobbering their change.
    """

    status_code = 409


class VersionNotFound(DocumentServerError):
    """Raised when addressing a document version that is not retained."""

    status_code = 404


class InvalidRevision(DocumentServerError):
    """Raised when an If-Match / _rev precondition value is malformed."""

    status_code = 400
