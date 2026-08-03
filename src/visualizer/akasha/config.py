"""Runtime configuration helpers for the production entrypoint.

Kept separate from the app factory so the factory itself stays free of
environment/IO concerns and remains trivially testable.
"""

import os

from pymongo import MongoClient

DEFAULT_MONGO_URI = "mongodb://mongo:27017"
DEFAULT_VERSIONS_KEEP = 20
# In-memory rate-limit storage suits a single process; point this at Redis
# (e.g. "redis://redis:6379") to share limits across multiple gunicorn workers.
DEFAULT_RATELIMIT_STORAGE_URI = "memory://"


def get_mongo_uri() -> str:
    return os.environ.get("MONGO_URI", DEFAULT_MONGO_URI)


def get_mongo_client() -> MongoClient:
    return MongoClient(get_mongo_uri())


def get_secret_key() -> str:
    """Secret key for signing session cookies, read from the environment.

    Required: raises if ``SECRET_KEY`` is unset or empty rather than falling back
    to an insecure default. (In Docker, compose enforces this too.)
    """
    key = os.environ.get("SECRET_KEY")
    if not key:
        raise RuntimeError(
            "SECRET_KEY environment variable is required (set it in docker/.env)."
        )
    return key


def get_versions_keep() -> int:
    """Max version snapshots retained per document (older ones are pruned).

    Read here (the only place env is touched) and injected into the app factory,
    keeping the store env-free and testable. Defaults to ``20``; a non-numeric or
    non-positive value is rejected rather than silently ignored.
    """
    raw = os.environ.get("VERSIONS_KEEP")
    if raw is None or raw.strip() == "":
        return DEFAULT_VERSIONS_KEEP
    try:
        value = int(raw)
    except ValueError:
        raise RuntimeError(f"VERSIONS_KEEP must be an integer, got {raw!r}.")
    if value < 1:
        raise RuntimeError("VERSIONS_KEEP must be at least 1.")
    return value


def get_rate_limit_storage_uri() -> str:
    """Storage backend URI for the auth rate limiter.

    Defaults to in-memory. Set ``RATELIMIT_STORAGE_URI`` to a shared backend
    (e.g. Redis) so limits hold across gunicorn workers.
    """
    return os.environ.get("RATELIMIT_STORAGE_URI", DEFAULT_RATELIMIT_STORAGE_URI)


def get_secure_cookies() -> bool:
    """Whether to mark the session cookie ``Secure`` (HTTPS-only).

    Off by default so plain-HTTP local dev works; enable it (``SESSION_COOKIE_SECURE=true``)
    when the app is served over HTTPS, e.g. behind a reverse proxy.
    """
    return os.environ.get("SESSION_COOKIE_SECURE", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
