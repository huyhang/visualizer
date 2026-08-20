"""Moves accumulated telemetry out of memory and into ``_ops``.

The work and the loop are deliberately separate. ``Flusher`` exposes each unit
of work as an ordinary method that returns what it did, so the tests drive it
directly -- no threads, no sleeping, no wall clock. ``BackgroundFlusher`` is the
thin daemon-thread wrapper around it, and is the only part that cannot be
unit tested.

Cadence: telemetry drains every few minutes, into hourly buckets. The two are
independent on purpose -- an hour of data is never at risk, only a few minutes
of it -- and a flush of a few dozen buckets is far cheaper than writing on every
request would be.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime

from .alerts import Alert, NullNotifier, Thresholds
from .alerts import evaluate as evaluate_alerts
from .alerts import raised as newly_raised
from .alerts import resolved as newly_resolved
from .capacity import CapacitySource, growth_per_day, months_until_full
from .settings import CachedSwitch, StaticSwitch
from .store import MetricsStore
from .usage import UsageScan

LOGGER = logging.getLogger("visualizer.observability")

_DEFAULT_FLUSH_SECONDS = 300.0
_DEFAULT_SCAN_SECONDS = 3_600.0


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Flusher:
    """Drains the recorder and runs the periodic scans. No threading here."""

    def __init__(
        self,
        recorder,
        store: MetricsStore,
        switch: CachedSwitch | StaticSwitch | None = None,
        *,
        usage_scan: UsageScan | None = None,
        capacity_source: CapacitySource | None = None,
        notifier=None,
        thresholds: Thresholds | None = None,
        now=_utcnow,
    ):
        self._recorder = recorder
        self._store = store
        self._switch = switch or StaticSwitch(True)
        self._usage_scan = usage_scan
        self._capacity_source = capacity_source
        self._notifier = notifier or NullNotifier()
        self._thresholds = thresholds or Thresholds()
        self._now = now

    def flush_once(self) -> int:
        """Write whatever the recorder has accumulated. Returns bucket count.

        Runs even while monitoring is paused, so that whatever was recorded in
        the moments before the switch flipped is not silently lost. The recorder
        stops feeding it, so a paused system drains once and then writes nothing.
        """
        buckets, problems, dropped = self._recorder.drain()
        if dropped:
            LOGGER.warning("dropped %s problem rows; in-memory cap reached", dropped)
        written = self._store.add_buckets(buckets)
        if problems:
            self._store.add_problems(problems)
        return written

    def scan_once(self) -> bool:
        """Re-measure storage attribution and host capacity.

        Skipped entirely while paused -- this is the expensive half, and pausing
        should actually stop work rather than merely stop recording it.
        """
        # Indexes are structural, so they are ensured regardless of the switch,
        # and here rather than at import: creating them is the first real call
        # to MongoDB, and observability must never be the reason the
        # application fails to boot. Idempotent, and retried every cycle, so a
        # database that is briefly unavailable at startup still ends up
        # correctly indexed -- and a persistent failure is logged every hour
        # rather than swallowed once.
        self._store.ensure_indexes()
        if not self._switch.enabled():
            return False
        moment = self._now()
        if self._usage_scan is not None:
            self._usage_scan.run(moment)
        if self._capacity_source is not None:
            sample = self._capacity_source.sample()
            self._store.save_capacity({**sample.as_record(), "at": moment})
            self._evaluate_alerts(sample.as_record())
        return True

    def _evaluate_alerts(self, capacity: dict) -> list[Alert]:
        """Diff this cycle's conditions against the last, and report the change.

        Evaluating here rather than when the page is rendered is what lets an
        alert reach someone who is not looking at the page. The notifier is
        handed only what changed -- de-duplication is done here, once, so no
        delivery mechanism has to reimplement it.
        """
        previous = [Alert.from_record(r) for r in self._store.active_alerts()]
        current = evaluate_alerts(
            capacity, self._months_until_full(capacity), self._thresholds
        )
        self._store.save_active_alerts([alert.as_record() for alert in current])
        started, ended = newly_raised(previous, current), newly_resolved(previous, current)
        if started or ended:
            self._notifier.notify(started, ended)
        return current

    def _months_until_full(self, capacity: dict) -> float | None:
        history = self._store.storage_days()
        totals: dict = {}
        for row in history:
            day = row["day"].date() if hasattr(row["day"], "date") else row["day"]
            totals[day] = totals.get(day, 0) + row.get("owns", 0) + row.get("authored", 0)
        return months_until_full(
            capacity.get("volume_free"), growth_per_day(sorted(totals.items()))
        )


class BackgroundFlusher:
    """Runs a ``Flusher`` on a daemon thread until asked to stop."""

    def __init__(
        self,
        flusher: Flusher,
        *,
        flush_seconds: float = _DEFAULT_FLUSH_SECONDS,
        scan_seconds: float = _DEFAULT_SCAN_SECONDS,
    ):
        self._flusher = flusher
        self._flush_seconds = flush_seconds
        self._scan_seconds = scan_seconds
        self._stopping = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="visualizer-observability", daemon=True
        )
        self._elapsed = 0.0

    def start(self) -> None:
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the loop and give it a chance to flush what is in memory.

        Safe to call when the thread was never started: ``stop`` is registered
        with ``atexit``, so if startup failed before ``start`` this must not
        raise on the way out and mask the original error.
        """
        self._stopping.set()
        if self._thread.ident is not None:
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        # The scan is expensive and the first one has nothing to compare
        # against, so run it immediately at startup and then on its own cadence.
        self._safely(self._flusher.scan_once)
        while not self._stopping.wait(self._flush_seconds):
            self._safely(self._flusher.flush_once)
            self._elapsed += self._flush_seconds
            if self._elapsed >= self._scan_seconds:
                self._elapsed = 0.0
                self._safely(self._flusher.scan_once)
        # A clean shutdown still writes what the last interval accumulated.
        self._safely(self._flusher.flush_once)

    @staticmethod
    def _safely(work) -> None:
        try:
            work()
        except Exception:
            # Deliberately broad, and the second of only two such handlers in
            # this package. A background thread that dies on one bad cycle stops
            # observing forever and does so silently; logging and continuing is
            # strictly better than either crashing or swallowing quietly.
            LOGGER.exception("observability cycle failed; continuing")
