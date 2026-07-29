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
