"""Shared authentication & access-control package.

Owns user accounts, the permission (grant) model, the password policy, email
validation, and the Flask-Login session routes (registered as an ``auth``
blueprint). Both akasha and chronos depend on this package; it depends on
neither of them, so the one login and one permission model are genuinely shared
rather than borrowed from a peer service.
"""

from .authz import (
    ALL_PERMS,
    DATABASE_RESOURCE,
    DELETE,
    READ,
    ROLE_PERMS,
    WRITE,
    effective_perms,
    is_allowed,
    owned_resources,
    perm_for_method,
    resources_shared_with,
    role_for_perms,
)
from .errors import (
    AuthError,
    EmailAlreadyExists,
    Forbidden,
    InvalidCredentials,
    InvalidEmail,
    RegistrationDisabled,
    Unauthorized,
    UserAlreadyExists,
    UserNotFound,
    WeakPassword,
)
from .passwords import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    generate_temp_password,
    validate_password_strength,
)
from .session import (
    User,
    admin_required,
    build_limiter,
    init_login,
    register_auth_routes,
)
from .store import (
    REGISTRATION_INVITE,
    REGISTRATION_MODES,
    REGISTRATION_OPEN,
    AuthStore,
    registration_allowed,
)
from .validation import validate_email

__all__ = [
    # authz
    "ALL_PERMS",
    "DATABASE_RESOURCE",
    "DELETE",
    "MAX_PASSWORD_LENGTH",
    # passwords
    "MIN_PASSWORD_LENGTH",
    "READ",
    "REGISTRATION_INVITE",
    "REGISTRATION_MODES",
    "REGISTRATION_OPEN",
    "ROLE_PERMS",
    "WRITE",
    # errors
    "AuthError",
    # store
    "AuthStore",
    "EmailAlreadyExists",
    "Forbidden",
    "InvalidCredentials",
    "InvalidEmail",
    "RegistrationDisabled",
    "Unauthorized",
    # session / blueprint
    "User",
    "UserAlreadyExists",
    "UserNotFound",
    "WeakPassword",
    "admin_required",
    "build_limiter",
    "effective_perms",
    "generate_temp_password",
    "init_login",
    "is_allowed",
    "owned_resources",
    "perm_for_method",
    "register_auth_routes",
    "registration_allowed",
    "resources_shared_with",
    "role_for_perms",
    # validation
    "validate_email",
    "validate_password_strength",
]
