"""The durable monitoring switch, cached and fail-safe.

Two properties this module exists to guarantee, both learned the hard way:

*Cached* -- the switch is consulted on every request, so reading it must not be
a database round trip. It is refreshed at most once per TTL per worker.

*Fail-safe* -- if the read fails, the switch keeps serving its last known value
and never raises. An observability layer that can turn a transient MongoDB blip
into a failed request has inverted its own purpose.
"""

from __future__ import annotations

import logging
from time import monotonic
from typing import Protocol

LOGGER = logging.getLogger("visualizer.observability")

_DEFAULT_TTL_SECONDS = 30.0


class SwitchStore(Protocol):
    def get_monitoring_enabled(self) -> bool | None: ...
    def set_monitoring_enabled(self, enabled: bool) -> None: ...


class StaticSwitch:
    """A switch with no storage behind it -- the default in tests."""

    def __init__(self, enabled: bool = True):
        self._enabled = enabled

    def enabled(self) -> bool:
        return self._enabled

    def set(self, enabled: bool) -> None:
        self._enabled = enabled


class CachedSwitch:
    """Reads the durable switch at most once per ``ttl_seconds``."""

    def __init__(
        self,
        store: SwitchStore,
        *,
        default: bool = True,
        ttl_seconds: float = _DEFAULT_TTL_SECONDS,
        clock=monotonic,
    ):
        self._store = store
        self._ttl = ttl_seconds
        self._clock = clock
        self._value = default
        self._expires_at: float | None = None
        self._degraded = False

    def enabled(self) -> bool:
        now = self._clock()
        if self._expires_at is not None and now < self._expires_at:
            return self._value
        self._refresh(now)
        return self._value

    def set(self, enabled: bool) -> None:
        """Persist the switch and adopt the new value immediately."""
        self._store.set_monitoring_enabled(enabled)
        self._value = enabled
        self._expires_at = self._clock() + self._ttl

    def _refresh(self, now: float) -> None:
        try:
            stored = self._store.get_monitoring_enabled()
        except Exception:
            # Deliberately broad, and one of only three such handlers in this
            # package. Any failure to read the switch -- MongoDB unreachable,
            # a malformed record -- must leave the last known value in place
            # rather than propagate into the request that asked. Logged with
            # its cause, and only on the first failure of a run rather than
            # once per TTL forever.
            if not self._degraded:
                self._degraded = True
                LOGGER.exception(
                    "could not read the monitoring switch; holding enabled=%s",
                    self._value,
                )
            self._expires_at = now + self._ttl
            return
        if stored is not None:
            self._value = stored
        self._degraded = False
        self._expires_at = now + self._ttl
