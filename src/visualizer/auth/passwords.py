"""Pure password helpers: the strength policy and temporary-password generation.

No dependency on Flask or MongoDB, so both functions unit-test in isolation.

The policy follows **NIST SP 800-63B** for memorised secrets: a generous length
range, screening against a list of known-bad values, and *no* composition or
rotation rules (NIST explicitly advises against them). A full breached-password
(HIBP) check is intentionally out of scope for this personal tool -- it would add
a network dependency; the built-in blocklist covers the common case.
"""

import secrets

from .errors import WeakPassword

# NIST recommends a minimum of 8; 12 is a stronger, still-memorable default.
MIN_PASSWORD_LENGTH = 12
# An upper bound guards against denial-of-service via very long hash inputs.
MAX_PASSWORD_LENGTH = 128

# A small screen of the most common / breached passwords. Lower-cased; the check
# is case-insensitive.
_COMMON_PASSWORDS = frozenset(
    {
        "password", "password1", "password12", "password123", "passw0rd",
        "123456", "1234567", "12345678", "123456789", "1234567890",
        "qwerty", "qwertyuiop", "qwerty123", "letmein", "welcome",
        "welcome123", "admin", "administrator", "iloveyou", "monkey",
        "dragon", "abc123", "abcd1234", "111111", "000000", "changeme",
        "trustno1", "football", "baseball", "superman", "master",
        "sunshine", "princess", "login", "starwars", "whatever",
        "secret", "password!", "letmein123",
    }
)


def validate_password_strength(password: object, username: str | None = None) -> str:
    """Return ``password`` if it satisfies the policy, else raise ``WeakPassword``.

    Policy (NIST SP 800-63B): length between :data:`MIN_PASSWORD_LENGTH` and
    :data:`MAX_PASSWORD_LENGTH`, not a known-common password, and -- when
    ``username`` is supplied -- not equal to the username.
    """
    if not isinstance(password, str) or not password:
        raise WeakPassword("A password is required.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPassword(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
        )
    if len(password) > MAX_PASSWORD_LENGTH:
        raise WeakPassword(
            f"Password must be at most {MAX_PASSWORD_LENGTH} characters long."
        )
    if password.lower() in _COMMON_PASSWORDS:
        raise WeakPassword("That password is too common; please choose another.")
    if username and password.strip().lower() == username.strip().lower():
        raise WeakPassword("Password must not be the same as the username.")
    return password


# Unambiguous alphabet for generated passwords: no 0/O or 1/l/I, so a temporary
# credential is easy to read aloud and type. 16 chars from this set clears the
# policy above by construction.
_TEMP_ALPHABET = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_TEMP_LENGTH = 16


def generate_temp_password(length: int = _TEMP_LENGTH) -> str:
    """Generate a strong, readable temporary password using ``secrets``.

    The default length and alphabet guarantee the result passes
    :func:`validate_password_strength`.
    """
    return "".join(secrets.choice(_TEMP_ALPHABET) for _ in range(length))
