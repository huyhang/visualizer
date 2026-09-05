"""Stable domain errors returned by the Logos API.

Each carries an HTTP status and a machine-readable code, the same contract the
other three services publish. The contract test asserts that every class here
appears in the documented ``code`` enum, so adding one without documenting it
fails the suite.
"""

from typing import Any


class LogosError(Exception):
    status_code = 500
    code = "LOGOS_ERROR"

    def __init__(self, message: str, evidence: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.evidence = evidence or {}

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"error": self.message, "code": self.code}
        if self.evidence:
            body["evidence"] = self.evidence
        return body


class InvalidIdentifier(LogosError):
    status_code = 400
    code = "INVALID_IDENTIFIER"


class InvalidVolume(LogosError):
    status_code = 400
    code = "INVALID_VOLUME"


class InvalidSection(LogosError):
    status_code = 400
    code = "INVALID_SECTION"


class InvalidDocument(LogosError):
    status_code = 400
    code = "INVALID_DOCUMENT"


class InvalidOrder(LogosError):
    status_code = 400
    code = "INVALID_ORDER"


class InvalidReaderItem(LogosError):
    status_code = 400
    code = "INVALID_READER_ITEM"


class InvalidReadingPosition(LogosError):
    status_code = 400
    code = "INVALID_READING_POSITION"


class InvalidPublication(LogosError):
    status_code = 400
    code = "INVALID_PUBLICATION"


class InvalidSearch(LogosError):
    status_code = 400
    code = "INVALID_SEARCH"


class InvalidRevision(LogosError):
    status_code = 400
    code = "INVALID_REVISION"


class Forbidden(LogosError):
    status_code = 403
    code = "FORBIDDEN"


class BookNotFound(LogosError):
    status_code = 404
    code = "BOOK_NOT_FOUND"


class ManuscriptNotFound(LogosError):
    status_code = 404
    code = "MANUSCRIPT_NOT_FOUND"


class VolumeNotFound(LogosError):
    status_code = 404
    code = "VOLUME_NOT_FOUND"


class SectionNotFound(LogosError):
    status_code = 404
    code = "SECTION_NOT_FOUND"


class ReaderItemNotFound(LogosError):
    status_code = 404
    code = "READER_ITEM_NOT_FOUND"


class PublicationCoverNotFound(LogosError):
    status_code = 404
    code = "PUBLICATION_COVER_NOT_FOUND"


class ExportJobNotFound(LogosError):
    status_code = 404
    code = "EXPORT_JOB_NOT_FOUND"


class AlreadyExists(LogosError):
    status_code = 409
    code = "ALREADY_EXISTS"


class RevisionConflict(LogosError):
    status_code = 409
    code = "REVISION_CONFLICT"


class CascadeRequired(LogosError):
    status_code = 409
    code = "CASCADE_REQUIRED"


class SectionKindInUse(LogosError):
    status_code = 409
    code = "SECTION_KIND_IN_USE"


class RevisionNotRetained(LogosError):
    status_code = 410
    code = "REVISION_NOT_RETAINED"


class ChronosEventNotFound(LogosError):
    status_code = 422
    code = "CHRONOS_EVENT_NOT_FOUND"


class ExportUnavailable(LogosError):
    status_code = 503
    code = "EXPORT_UNAVAILABLE"


class PreconditionRequired(LogosError):
    status_code = 428
    code = "PRECONDITION_REQUIRED"
