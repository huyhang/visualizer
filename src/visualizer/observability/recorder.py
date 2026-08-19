"""In-process accumulation of request telemetry. Performs no I/O.

This is the only observability code that runs inside a request, so it does the
least possible work: take a lock, add to some integers, release. Nothing here
opens a socket, touches MongoDB or reads the clock -- the caller supplies the
timestamp and a background flusher drains what accumulates.

Two bounds keep a busy or hostile workload from growing memory without limit:
``max_keys`` caps distinct hourly buckets (the excess folds into a visible
``<overflow>`` route rather than being dropped silently), and ``max_problems``
caps the retained slow/failed request detail between flushes.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from .aggregation import bucket_for, floor_hour, status_class

# Route label used once ``max_keys`` distinct buckets exist. Its presence in the
# admin view is the signal that cardinality was capped -- silent truncation
# would read as "this is everything" when it is not.
OVERFLOW_ROUTE = "<overflow>"

_DEFAULT_MAX_KEYS = 2_000
_DEFAULT_MAX_PROBLEMS = 200


@dataclass(frozen=True)
class Sample:
    """One completed request, as the middleware observed it."""

    service: str
    route: str
    method: str
    status: int
    writer: str
    duration_ms: float
    bytes_in: int
    bytes_out: int
    at: datetime
    error: str | None = None


@dataclass(frozen=True)
class Bucket:
    """One hour of requests sharing a route, method, status class and writer."""

    hour: datetime
    service: str
    route: str
    method: str
    status_class: str
    writer: str
    count: int
    latency_total_ms: float
    buckets: dict[str, int]
    bytes_in: int
    bytes_out: int


@dataclass(frozen=True)
class Problem:
    """A single slow or failed request, kept for the admin detail table."""

    at: datetime
    service: str
    route: str
    method: str
    writer: str
    status: int
    duration_ms: float
    error: str | None


@dataclass
class _Tally:
    count: int = 0
    latency_total_ms: float = 0.0
    buckets: dict[str, int] = field(default_factory=dict)
    bytes_in: int = 0
    bytes_out: int = 0


class RequestRecorder(Protocol):
    def record(self, sample: Sample) -> None: ...


class NullRecorder:
    """Used when monitoring is off at boot. One attribute lookup and a return."""

    def record(self, sample: Sample) -> None:
        return None

    def drain(self) -> tuple[list[Bucket], list[Problem], int]:
        return [], [], 0


class InProcessRecorder:
    """Thread-safe accumulator drained by the flusher.

    The lock is held only for arithmetic on plain integers -- never across I/O --
    so contention between gthread workers stays negligible while still making
    concurrent increments exact.
    """

    def __init__(
        self,
        *,
        slow_ms: float = 1_000.0,
        max_keys: int = _DEFAULT_MAX_KEYS,
        max_problems: int = _DEFAULT_MAX_PROBLEMS,
    ):
        self._slow_ms = slow_ms
        self._max_keys = max_keys
        self._max_problems = max_problems
        self._lock = threading.Lock()
        self._tallies: dict[tuple, _Tally] = {}
        self._problems: list[Problem] = []
        self._dropped_problems = 0

    def record(self, sample: Sample) -> None:
        klass = status_class(sample.status)
        label = bucket_for(sample.duration_ms)
        interesting = sample.status >= 500 or sample.duration_ms >= self._slow_ms
        with self._lock:
            key = self._key_for(sample, klass)
            tally = self._tallies.get(key)
            if tally is None:
                tally = _Tally()
                self._tallies[key] = tally
            tally.count += 1
            tally.latency_total_ms += sample.duration_ms
            tally.buckets[label] = tally.buckets.get(label, 0) + 1
            tally.bytes_in += sample.bytes_in
            tally.bytes_out += sample.bytes_out
            if interesting:
                self._add_problem(sample)

    def drain(self) -> tuple[list[Bucket], list[Problem], int]:
        """Take everything accumulated so far, leaving the recorder empty.

        Returns the hourly buckets, the retained problem rows, and how many
        problem rows were dropped because the in-memory cap was reached.
        """
        with self._lock:
            tallies, problems = self._tallies, self._problems
            dropped = self._dropped_problems
            self._tallies, self._problems, self._dropped_problems = {}, [], 0
        buckets = [
            Bucket(
                hour=hour,
                service=service,
                route=route,
                method=method,
                status_class=klass,
                writer=writer,
                count=tally.count,
                latency_total_ms=tally.latency_total_ms,
                buckets=dict(tally.buckets),
                bytes_in=tally.bytes_in,
                bytes_out=tally.bytes_out,
            )
            for (hour, service, route, method, klass, writer), tally in tallies.items()
        ]
        return buckets, problems, dropped

    # -- internals (called with the lock held) -------------------------------

    def _key_for(self, sample: Sample, klass: str) -> tuple:
        key = (
            floor_hour(sample.at),
            sample.service,
            sample.route,
            sample.method,
            klass,
            sample.writer,
        )
        if key in self._tallies or len(self._tallies) < self._max_keys:
            return key
        return (key[0], sample.service, OVERFLOW_ROUTE, sample.method, klass, sample.writer)

    def _add_problem(self, sample: Sample) -> None:
        if len(self._problems) >= self._max_problems:
            self._dropped_problems += 1
            return
        self._problems.append(
            Problem(
                at=sample.at,
                service=sample.service,
                route=sample.route,
                method=sample.method,
                writer=sample.writer,
                status=sample.status,
                duration_ms=sample.duration_ms,
                error=sample.error,
            )
        )
