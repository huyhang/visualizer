"""Assembles the production observability stack.

The one place that reads the environment and starts a thread, so the three WSGI
entry points each stay a single call. Everything it builds is the same object
graph the tests construct by hand -- this module adds wiring, never behaviour.
"""

from __future__ import annotations

import atexit

from . import Observability
from .alerts import NullNotifier
from .capacity import HostCapacitySource
from .config import (
    get_data_path,
    get_flush_seconds,
    get_monitoring_enabled,
    get_scan_seconds,
)
from .flush import BackgroundFlusher, Flusher
from .recorder import InProcessRecorder
from .settings import CachedSwitch
from .store import MetricsStore
from .usage import MongoDocumentSource, UsageScan


def start(client, auth_store) -> Observability:
    """Build the stack, start the background thread, and return the seam.

    Nothing here touches MongoDB. The first call happens on the background
    thread, so an unreachable database delays observability rather than
    preventing the application from serving.
    """
    store = MetricsStore(client)
    recorder = InProcessRecorder()
    switch = CachedSwitch(store, default=get_monitoring_enabled())
    background = BackgroundFlusher(
        Flusher(
            recorder,
            store,
            switch,
            usage_scan=UsageScan(
                MongoDocumentSource(client), auth_store.all_grants, store
            ),
            capacity_source=HostCapacitySource(client, get_data_path()),
            # Evaluation runs in production from day one; only delivery is
            # absent. Swapping this for an SMTP notifier changes nothing else.
            notifier=NullNotifier(),
        ),
        flush_seconds=get_flush_seconds(),
        scan_seconds=get_scan_seconds(),
    )
    background.start()
    # A clean shutdown drains whatever the last interval accumulated instead of
    # discarding it.
    atexit.register(background.stop)
    return Observability(recorder=recorder, switch=switch, store=store)
