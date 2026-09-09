"""Runtime configuration helpers for the production entrypoint.

Kept separate from the app factory so the factory itself stays free of
environment/IO concerns and remains trivially testable.
"""

import os

from pymongo import MongoClient

DEFAULT_MONGO_URI = "mongodb://mongo:27017"
DEFAULT_VERSIONS_KEEP = 20
DEFAULT_MAX_IMAGE_BYTES = 20 * 1024 * 1024
DEFAULT_MAX_IMAGE_PIXELS = 40_000_000
DEFAULT_IMAGE_DISPLAY_MAX_PX = 2048
DEFAULT_IMAGE_THUMBNAIL_MAX_PX = 360
# In-memory rate-limit storage suits a single process; point this at Redis
# (e.g. "redis://redis:6379") to share limits across multiple gunicorn workers.
DEFAULT_RATELIMIT_STORAGE_URI = "memory://"
# Browser-facing base URLs for the four services, used by the service nav.
# Defaults match the standalone development ports; override all four
# when serving behind a reverse proxy (e.g. https://myworld/akasha).
DEFAULT_AKASHA_URL = "http://localhost:5002"
DEFAULT_CHRONOS_URL = "http://localhost:5003"
DEFAULT_PRITHVI_URL = "http://localhost:5004"
DEFAULT_LOGOS_URL = "http://localhost:5005"


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


def _positive_int(name: str, default: int) -> int:
    """One env-backed positive integer.

    Every numeric knob below reads through here, so they all agree on what an
    empty value, a non-number and a zero mean: default, refuse, refuse. Read at
    import time and injected into the app factory, keeping the stores and route
    layer env-free and testable.
    """
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise RuntimeError(f"{name} must be an integer, got {raw!r}.") from None
    if value < 1:
        raise RuntimeError(f"{name} must be at least 1.")
    return value


def get_versions_keep() -> int:
    """Max version snapshots retained per document (older ones are pruned)."""
    return _positive_int("VERSIONS_KEEP", DEFAULT_VERSIONS_KEEP)


def get_max_image_bytes() -> int:
    return _positive_int("AKASHA_MAX_IMAGE_BYTES", DEFAULT_MAX_IMAGE_BYTES)


def get_max_image_pixels() -> int:
    return _positive_int("AKASHA_MAX_IMAGE_PIXELS", DEFAULT_MAX_IMAGE_PIXELS)


def get_image_display_max_px() -> int:
    return _positive_int("AKASHA_IMAGE_DISPLAY_MAX_PX", DEFAULT_IMAGE_DISPLAY_MAX_PX)


def get_image_thumbnail_max_px() -> int:
    return _positive_int(
        "AKASHA_IMAGE_THUMBNAIL_MAX_PX", DEFAULT_IMAGE_THUMBNAIL_MAX_PX
    )


def get_rate_limit_storage_uri() -> str:
    """Storage backend URI for the auth rate limiter.

    Defaults to in-memory. Set ``RATELIMIT_STORAGE_URI`` to a shared backend
    (e.g. Redis) so limits hold across gunicorn workers.
    """
    return os.environ.get("RATELIMIT_STORAGE_URI", DEFAULT_RATELIMIT_STORAGE_URI)


def get_akasha_url() -> str:
    """Browser-facing base URL of the akasha service (for the service nav)."""
    return os.environ.get("AKASHA_URL", DEFAULT_AKASHA_URL)


def get_chronos_url() -> str:
    """Browser-facing base URL of the chronos service (for the service nav)."""
    return os.environ.get("CHRONOS_URL", DEFAULT_CHRONOS_URL)


def get_prithvi_url() -> str:
    """Browser-facing base URL of the prithvi service (for the service nav)."""
    return os.environ.get("PRITHVI_URL", DEFAULT_PRITHVI_URL)


def get_logos_url() -> str:
    """Browser-facing base URL of the logos service (for the service nav)."""
    return os.environ.get("LOGOS_URL", DEFAULT_LOGOS_URL)


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
