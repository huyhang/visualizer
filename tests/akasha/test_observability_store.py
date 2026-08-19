"""Tests for the ``_ops`` MongoDB boundary.

The merge behaviour is what these protect: flushing the same hour twice, from
two workers, must add rather than overwrite -- both the totals and the latency
histogram.
"""

from datetime import UTC, datetime, timedelta

import mongomock

from visualizer.observability.recorder import Bucket, Problem
from visualizer.observability.store import OPS_DB, MetricsStore

HOUR = datetime(2026, 8, 19, 14, tzinfo=UTC)


def _store():
    return MetricsStore(mongomock.MongoClient())


def _bucket(**overrides) -> Bucket:
    defaults = {
        "hour": HOUR,
        "service": "akasha",
        "route": "/databases/<database>",
        "method": "GET",
        "status_class": "2xx",
        "writer": "mara",
        "count": 3,
        "latency_total_ms": 30.0,
        "buckets": {"10": 2, "25": 1},
        "bytes_in": 10,
        "bytes_out": 90,
    }
    return Bucket(**{**defaults, **overrides})


def _problem(minute: int = 0, **overrides) -> Problem:
    defaults = {
        "at": HOUR + timedelta(minutes=minute),
        "service": "akasha",
        "route": "/x",
        "method": "GET",
        "writer": "mara",
        "status": 500,
        "duration_ms": 2000.0,
        "error": "Boom",
    }
    return Problem(**{**defaults, **overrides})


def test_indexes_are_created_and_recreating_them_is_safe():
    store = _store()
    store.ensure_indexes()
    store.ensure_indexes()


def test_writing_no_buckets_is_a_no_op():
    assert _store().add_buckets([]) == 0


def test_flushing_the_same_hour_twice_merges_instead_of_overwriting():
    store = _store()
    store.add_buckets([_bucket()])
    store.add_buckets([_bucket()])

    rows = store.request_hours()

    assert len(rows) == 1
    assert rows[0]["count"] == 6
    assert rows[0]["latency_total_ms"] == 60.0
    assert rows[0]["buckets"] == {"10": 4, "25": 2}
    assert rows[0]["bytes_in"] == 20


def test_a_later_flush_can_introduce_a_new_latency_bucket():
    store = _store()
    store.add_buckets([_bucket(buckets={"10": 1})])
    store.add_buckets([_bucket(buckets={"5000": 1})])

    assert store.request_hours()[0]["buckets"] == {"10": 1, "5000": 1}


def test_identity_fields_are_written_once_and_kept():
    store = _store()
    store.add_buckets([_bucket()])
    store.add_buckets([_bucket()])

    row = store.request_hours()[0]
    assert row["service"] == "akasha"
    assert row["writer"] == "mara"
    assert row["hour"].replace(tzinfo=UTC) == HOUR


def test_different_identities_get_their_own_rows():
    store = _store()
    store.add_buckets([_bucket(), _bucket(writer="devi"), _bucket(status_class="5xx")])

    assert len(store.request_hours()) == 3


def test_hours_can_be_read_back_from_a_starting_point():
    store = _store()
    store.add_buckets([_bucket(hour=HOUR - timedelta(hours=5)), _bucket()])

    assert len(store.request_hours()) == 2
    assert len(store.request_hours(since=HOUR - timedelta(hours=1))) == 1


def test_stored_rows_expose_no_internal_fields():
    store = _store()
    store.add_buckets([_bucket()])
    assert not {"_id", "expires_at"} & set(store.request_hours()[0])


def test_rows_carry_an_expiry_so_they_cannot_accumulate_forever():
    store = _store()
    store.add_buckets([_bucket()])

    raw = store._client[OPS_DB]["request_hours"].find_one({})

    assert raw["expires_at"].replace(tzinfo=UTC) > HOUR


def test_the_durable_switch_defaults_to_unset():
    store = _store()
    assert store.get_monitoring_enabled() is None
    store.set_monitoring_enabled(False)
    assert store.get_monitoring_enabled() is False
    store.set_monitoring_enabled(True)
    assert store.get_monitoring_enabled() is True


def test_problems_are_trimmed_to_the_newest_rows():
    store = _store()
    for minute in range(12):
        store.add_problems([_problem(minute)], keep=5)

    kept = store.problems(limit=99)

    assert len(kept) == 5
    assert [row["at"].minute for row in kept] == [11, 10, 9, 8, 7]


def test_problems_come_back_newest_first_and_respect_the_limit():
    store = _store()
    store.add_problems([_problem(minute) for minute in range(6)])

    assert [row["at"].minute for row in store.problems(limit=2)] == [5, 4]


def test_trimming_runs_even_when_nothing_new_arrived():
    store = _store()
    store.add_problems([_problem(minute) for minute in range(9)])
    store.add_problems([], keep=4)

    assert len(store.problems(limit=99)) == 4


def test_a_storage_scan_supersedes_the_same_day():
    store = _store()
    store.save_storage(HOUR, [{"writer": "mara", "owns": 10, "authored": 1, "records": 1}])
    store.save_storage(HOUR, [{"writer": "mara", "owns": 90, "authored": 2, "records": 3}])

    rows = store.storage_days()

    assert len(rows) == 1
    assert rows[0]["owns"] == 90


def test_storage_days_are_kept_per_day_and_per_writer():
    store = _store()
    yesterday = HOUR - timedelta(days=1)
    store.save_storage(yesterday, [{"writer": "mara", "owns": 5, "authored": 0, "records": 1}])
    store.save_storage(
        HOUR,
        [
            {"writer": "mara", "owns": 10, "authored": 0, "records": 1},
            {"writer": "devi", "owns": 20, "authored": 0, "records": 1},
        ],
    )

    assert len(store.storage_days()) == 3
    assert store.latest_storage_day().replace(tzinfo=UTC) == HOUR
    assert len(store.storage_days(since=HOUR)) == 2


def test_latest_storage_day_is_none_before_the_first_scan():
    assert _store().latest_storage_day() is None


def test_capacity_keeps_only_the_latest_sample():
    store = _store()
    store.save_capacity({"volume_free": 1, "at": HOUR})
    store.save_capacity({"volume_free": 2, "at": HOUR})

    assert store.latest_capacity()["volume_free"] == 2
    assert store._client[OPS_DB]["capacity"].count_documents({}) == 1


def test_capacity_is_none_before_the_first_sample():
    assert _store().latest_capacity() is None
