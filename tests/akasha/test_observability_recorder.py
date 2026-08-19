"""Unit tests for the in-request accumulator.

The concurrency test is the important one here: the recorder is written from
several gthread worker threads and drained by another, and a read-modify-write
in this position silently loses samples under load -- corrupting exactly the
latency figure the feature exists to report.
"""

import threading
from datetime import UTC, datetime

from visualizer.observability.recorder import (
    OVERFLOW_ROUTE,
    InProcessRecorder,
    NullRecorder,
    Sample,
)

AT = datetime(2026, 8, 19, 14, 30, tzinfo=UTC)


def _sample(**overrides) -> Sample:
    defaults = {
        "service": "akasha",
        "route": "/databases/<database>",
        "method": "GET",
        "status": 200,
        "writer": "mara",
        "duration_ms": 12.0,
        "bytes_in": 10,
        "bytes_out": 90,
        "at": AT,
    }
    return Sample(**{**defaults, **overrides})


def test_null_recorder_keeps_nothing():
    recorder = NullRecorder()
    recorder.record(_sample())
    assert recorder.drain() == ([], [], 0)


def test_samples_in_the_same_hour_merge_into_one_bucket():
    recorder = InProcessRecorder()
    recorder.record(_sample(duration_ms=4))
    recorder.record(_sample(duration_ms=40, at=AT.replace(minute=59)))

    buckets, _, _ = recorder.drain()

    assert len(buckets) == 1
    assert buckets[0].count == 2
    assert buckets[0].buckets == {"5": 1, "50": 1}
    assert buckets[0].latency_total_ms == 44
    assert buckets[0].bytes_in == 20 and buckets[0].bytes_out == 180


def test_different_writers_and_statuses_stay_separate():
    recorder = InProcessRecorder()
    recorder.record(_sample(writer="mara"))
    recorder.record(_sample(writer="devi"))
    recorder.record(_sample(writer="mara", status=404))

    buckets, _, _ = recorder.drain()

    assert len(buckets) == 3
    assert {(b.writer, b.status_class) for b in buckets} == {
        ("mara", "2xx"),
        ("devi", "2xx"),
        ("mara", "4xx"),
    }


def test_draining_leaves_the_recorder_empty():
    recorder = InProcessRecorder()
    recorder.record(_sample())
    assert recorder.drain()[0]
    assert recorder.drain() == ([], [], 0)


def test_concurrent_records_lose_nothing():
    """Eight threads, 500 samples each: every one must be counted exactly once."""
    recorder = InProcessRecorder()
    threads = 8
    per_thread = 500

    def hammer():
        for _ in range(per_thread):
            recorder.record(_sample(duration_ms=7.0))

    workers = [threading.Thread(target=hammer) for _ in range(threads)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    buckets, _, _ = recorder.drain()
    expected = threads * per_thread
    assert len(buckets) == 1
    assert buckets[0].count == expected
    # The histogram must agree with the count -- this is precisely where a
    # read-modify-write would drop samples without dropping the total.
    assert sum(buckets[0].buckets.values()) == expected


def test_server_errors_are_kept_as_problem_detail():
    recorder = InProcessRecorder()
    recorder.record(_sample(status=500, error="DocumentNotFound"))

    _, problems, dropped = recorder.drain()

    assert dropped == 0
    assert [(p.status, p.error) for p in problems] == [(500, "DocumentNotFound")]


def test_slow_successes_are_kept_too():
    recorder = InProcessRecorder(slow_ms=100)
    recorder.record(_sample(duration_ms=150))
    recorder.record(_sample(duration_ms=99))

    _, problems, _ = recorder.drain()

    assert [p.duration_ms for p in problems] == [150]


def test_problem_detail_is_bounded_and_reports_what_it_dropped():
    recorder = InProcessRecorder(max_problems=3)
    for _ in range(10):
        recorder.record(_sample(status=500))

    _, problems, dropped = recorder.drain()

    assert len(problems) == 3
    assert dropped == 7


def test_cardinality_cap_folds_into_a_visible_overflow_route():
    """Excess keys must be visible as overflow, never silently discarded."""
    recorder = InProcessRecorder(max_keys=2)
    for index in range(6):
        recorder.record(_sample(route=f"/route-{index}"))

    buckets, _, _ = recorder.drain()

    assert len(buckets) == 3  # two real routes plus the overflow bucket
    overflow = next(b for b in buckets if b.route == OVERFLOW_ROUTE)
    assert overflow.count == 4
    assert sum(b.count for b in buckets) == 6


def test_a_known_key_still_records_after_the_cap_is_reached():
    recorder = InProcessRecorder(max_keys=1)
    recorder.record(_sample(route="/first"))
    recorder.record(_sample(route="/second"))
    recorder.record(_sample(route="/first"))

    buckets, _, _ = recorder.drain()

    first = next(b for b in buckets if b.route == "/first")
    assert first.count == 2
