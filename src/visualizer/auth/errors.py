"""Domain errors for the shared authentication / access-control layer.

Each error carries an HTTP ``status_code`` so the web layer can translate it into
a response without knowing the details. ``AuthError`` is the common base, so any
service hosting the shared auth routes can serialise them with a single error
handler (see akasha's and chronos's ``create_app``).
"""


class AuthError(Exception):
    """Base class for all shared auth/access-control errors."""

    status_code = 500

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class InvalidCredentials(AuthError):
    """Raised when a login attempt has bad or missing credentials."""

    status_code = 400


class UserAlreadyExists(AuthError):
    """Raised when registering a username that is already taken."""

    status_code = 409


class EmailAlreadyExists(AuthError):
    """Raised when registering an email address that is already in use."""

    status_code = 409


class InvalidEmail(AuthError):
    """Raised when an email address is missing or malformed."""

    status_code = 400


class WeakPassword(AuthError):
    """Raised when a chosen password fails the strength policy."""

    status_code = 400


class RegistrationDisabled(AuthError):
    """Raised when self-registration is attempted while in invite-only mode."""

    status_code = 403


class UserNotFound(AuthError):
    """Raised when addressing a user account that does not exist."""

    status_code = 404


class Unauthorized(AuthError):
    """Raised when a request is not authenticated."""

    status_code = 401


class Forbidden(AuthError):
    """Raised when an authenticated user lacks permission for an action."""

    status_code = 403
