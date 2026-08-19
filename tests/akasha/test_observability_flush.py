"""Tests for the flusher -- the work, not the thread.

``Flusher`` exposes each cycle as a plain method precisely so these can run
without threads, sleeps or a wall clock. The one genuinely concurrent piece,
``BackgroundFlusher``, is covered separately and only for the promises that
matter: it survives a failing cycle, and a clean stop drains what is in memory.
"""

from datetime import UTC, datetime

import mongomock
import pytest

from visualizer.observability.capacity import CapacitySample, StaticCapacitySource
from visualizer.observability.flush import BackgroundFlusher, Flusher
from visualizer.observability.recorder import InProcessRecorder, Sample
from visualizer.observability.settings import StaticSwitch
from visualizer.observability.store import MetricsStore

NOW = datetime(2026, 8, 19, 14, 30, tzinfo=UTC)


class RecordingScan:
    def __init__(self):
        self.runs = []

    def run(self, moment):
        self.runs.append(moment)
        return []


def _sample(**overrides) -> Sample:
    defaults = {
        "service": "akasha",
        "route": "/x",
        "method": "GET",
        "status": 200,
        "writer": "mara",
        "duration_ms": 12.0,
        "bytes_in": 0,
        "bytes_out": 0,
        "at": NOW,
    }
    return Sample(**{**defaults, **overrides})


def _parts(switch=None, scan=None, capacity=None):
    recorder = InProcessRecorder()
    store = MetricsStore(mongomock.MongoClient())
    flusher = Flusher(
        recorder,
        store,
        switch or StaticSwitch(True),
        usage_scan=scan,
        capacity_source=capacity,
        now=lambda: NOW,
    )
    return recorder, store, flusher


def test_flushing_an_empty_recorder_writes_nothing():
    _, store, flusher = _parts()
    assert flusher.flush_once() == 0
    assert store.request_hours() == []


def test_a_flush_moves_samples_into_the_store():
    recorder, store, flusher = _parts()
    recorder.record(_sample())
    recorder.record(_sample(duration_ms=40))

    assert flusher.flush_once() == 1
    assert store.request_hours()[0]["count"] == 2


def test_a_flush_empties_the_recorder_so_nothing_is_written_twice():
    recorder, store, flusher = _parts()
    recorder.record(_sample())
    flusher.flush_once()
    flusher.flush_once()

    assert store.request_hours()[0]["count"] == 1


def test_problems_are_flushed_alongside_the_buckets():
    recorder, store, flusher = _parts()
    recorder.record(_sample(status=500, error="Boom"))

    flusher.flush_once()

    assert [row["error"] for row in store.problems()] == ["Boom"]


def test_a_paused_system_still_drains_what_was_recorded_before_the_pause():
    """The switch stops the recorder, so anything already accumulated is real
    data that would otherwise be thrown away at the moment of pausing."""
    recorder, store, flusher = _parts(switch=StaticSwitch(False))
    recorder.record(_sample())

    assert flusher.flush_once() == 1
    assert store.request_hours()[0]["count"] == 1


def test_dropped_problem_rows_are_logged_rather_than_lost_quietly(caplog):
    """A cap that truncates silently reads as "this is everything" when it is not."""
    recorder = InProcessRecorder(max_problems=2)
    store = MetricsStore(mongomock.MongoClient())
    flusher = Flusher(recorder, store, StaticSwitch(True))
    for _ in range(7):
        recorder.record(_sample(status=500))

    with caplog.at_level("WARNING", logger="visualizer.observability"):
        flusher.flush_once()

    assert "dropped 5 problem rows" in caplog.text
    assert len(store.problems()) == 2


def test_a_scan_measures_storage_and_capacity():
    scan = RecordingScan()
    _, store, flusher = _parts(
        scan=scan, capacity=StaticCapacitySource(CapacitySample(volume_free=7))
    )

    assert flusher.scan_once() is True
    assert scan.runs == [NOW]
    assert store.latest_capacity()["volume_free"] == 7


def test_pausing_stops_the_expensive_scan_entirely():
    """Pausing must stop doing work, not merely stop recording its results."""
    scan = RecordingScan()
    _, store, flusher = _parts(
        switch=StaticSwitch(False),
        scan=scan,
        capacity=StaticCapacitySource(CapacitySample(volume_free=7)),
    )

    assert flusher.scan_once() is False
    assert scan.runs == []
    assert store.latest_capacity() is None


def test_a_scan_ensures_indexes_even_while_paused():
    """Indexes are structural; without them nothing ever expires."""
    calls = []
    recorder = InProcessRecorder()

    class Store(MetricsStore):
        def ensure_indexes(self):
            calls.append(True)

    flusher = Flusher(recorder, Store(mongomock.MongoClient()), StaticSwitch(False))
    flusher.scan_once()

    assert calls == [True]


def test_a_scan_works_without_optional_collaborators():
    _, store, flusher = _parts()
    assert flusher.scan_once() is True
    assert store.latest_capacity() is None


# -- the thread ---------------------------------------------------------------


def test_a_failing_cycle_does_not_kill_the_thread(caplog):
    class Broken:
        def __init__(self):
            self.calls = 0

        def flush_once(self):
            self.calls += 1
            raise RuntimeError("nope")

        def scan_once(self):
            raise RuntimeError("nope")

    broken = Broken()
    background = BackgroundFlusher(broken, flush_seconds=0.01, scan_seconds=0.01)
    background.start()
    background.stop(timeout=1.0)

    assert broken.calls >= 1, "the loop stopped after the first failure"


def test_stopping_a_thread_that_never_started_is_safe():
    """``stop`` is an atexit handler; if startup failed it must not raise on
    the way out and mask the original error."""
    _, _, flusher = _parts()
    BackgroundFlusher(flusher).stop(timeout=0.1)


def test_stopping_twice_is_safe():
    _, _, flusher = _parts()
    background = BackgroundFlusher(flusher, flush_seconds=60.0, scan_seconds=60.0)
    background.start()
    background.stop(timeout=2.0)
    background.stop(timeout=2.0)


def test_stopping_drains_what_is_still_in_memory():
    recorder, store, flusher = _parts()
    background = BackgroundFlusher(flusher, flush_seconds=60.0, scan_seconds=60.0)
    background.start()
    recorder.record(_sample())
    background.stop(timeout=2.0)

    assert store.request_hours()[0]["count"] == 1


@pytest.mark.parametrize("enabled", [True, False])
def test_the_switch_decides_scanning_not_flushing(enabled):
    scan = RecordingScan()
    recorder, _, flusher = _parts(switch=StaticSwitch(enabled), scan=scan)
    recorder.record(_sample())

    flushed = flusher.flush_once()
    flusher.scan_once()

    assert flushed == 1
    assert bool(scan.runs) is enabled
