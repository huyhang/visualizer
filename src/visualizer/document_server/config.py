"""Runtime configuration helpers for the production entrypoint.

Kept separate from the app factory so the factory itself stays free of
environment/IO concerns and remains trivially testable.
"""

import os

from pymongo import MongoClient

DEFAULT_MONGO_URI = "mongodb://mongo:27017"


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
