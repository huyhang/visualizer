"""Per-writer resource, latency and error observability.

Shaped around one rule: **nothing that observes a request may do I/O inside it.**
Requests only ever touch an in-process accumulator (``recorder``); a background
``flush`` drains it into a reserved ``_ops`` database every few minutes, and the
expensive measurements -- storage attribution and host capacity -- run on their
own slower cadence. Pausing stops the work, not just the recording.

The layers, innermost first:

``aggregation``  pure rules: latency buckets, percentiles, bucket identity
``recorder``     thread-safe in-memory accumulation; performs no I/O
``middleware``   the only Flask-aware part; one before/after request pair
``settings``     the durable switch, cached and fail-safe
``store``        the ``_ops`` MongoDB boundary; atomic ``$inc`` upserts only
``usage``        who is charged for which stored bytes (pure rule + injected sweep)
``capacity``     host disk/memory/MongoDB sampling and the growth projection
``alerts``       threshold evaluation as structured events, and the notifier seam
``flush``        drains the recorder and drives the periodic scans
``charts``       pure value-to-SVG geometry
``view``         stored rows to page content
``page``         the admin route and its pause switch
"""

from dataclasses import dataclass

from .alerts import Alert, Notifier, NullNotifier, Thresholds
from .capacity import CapacitySource, HostCapacitySource
from .flush import BackgroundFlusher, Flusher
from .middleware import register_observability
from .recorder import (
    InProcessRecorder,
    NullRecorder,
    Problem,
    RequestRecorder,
    Sample,
)
from .settings import CachedSwitch, StaticSwitch
from .store import MetricsStore
from .usage import MongoDocumentSource, UsageScan

__all__ = [
    "Alert",
    "BackgroundFlusher",
    "CachedSwitch",
    "CapacitySource",
    "Flusher",
    "HostCapacitySource",
    "InProcessRecorder",
    "MetricsStore",
    "MongoDocumentSource",
    "Notifier",
    "NullNotifier",
    "NullRecorder",
    "Observability",
    "Problem",
    "RequestRecorder",
    "Sample",
    "StaticSwitch",
    "Thresholds",
    "UsageScan",
    "register_observability",
]


@dataclass(frozen=True)
class Observability:
    """What an application is handed: somewhere to record, and a switch.

    ``store`` is optional because only Akasha renders the admin page; Chronos
    records through the same recorder but never reads it back.
    """

    recorder: RequestRecorder
    switch: CachedSwitch | StaticSwitch
    store: MetricsStore | None = None

    def install(self, app, service: str) -> None:
        register_observability(app, self.recorder, self.switch, service)
