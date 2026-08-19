"""Environment reading. The only module in this package that looks at ``os.environ``.

Everything else receives its configuration by injection, so the rules stay
testable without monkeypatching the environment.
"""

import os

_TRUTHY = ("1", "true", "yes", "on")

# Defaults chosen for a NAS running a handful of writers: drain every five
# minutes, re-measure storage and host capacity hourly.
DEFAULT_FLUSH_SECONDS = 300
DEFAULT_SCAN_SECONDS = 3600
DEFAULT_DATA_PATH = "/data"


def get_monitoring_enabled() -> bool:
    """Whether monitoring starts enabled. The durable admin switch overrides it."""
    return os.environ.get("MONITORING_ENABLED", "true").strip().lower() in _TRUTHY


def get_flush_seconds() -> int:
    return _positive_int("MONITORING_FLUSH_SECONDS", DEFAULT_FLUSH_SECONDS, floor=10)


def get_scan_seconds() -> int:
    return _positive_int("MONITORING_SCAN_SECONDS", DEFAULT_SCAN_SECONDS, floor=60)


def get_data_path() -> str:
    """Filesystem path whose free space represents the NAS data volume."""
    return os.environ.get("MONITORING_DATA_PATH", DEFAULT_DATA_PATH)


def _positive_int(name: str, default: int, floor: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return max(floor, int(raw))
    except ValueError:
        return default
