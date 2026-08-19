"""Unit tests for the pure aggregation rules -- no database, no Flask."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from visualizer.observability.aggregation import (
    BUCKETS_MS,
    OVERFLOW,
    UNMATCHED,
    bucket_for,
    bucket_key,
    floor_hour,
    mean_ms,
    merge_counts,
    overflow_count,
    percentile_ms,
    route_key,
    status_class,
)


def test_floor_hour_drops_everything_below_the_hour():
    assert floor_hour(datetime(2026, 8, 19, 14, 37, 9, 500, tzinfo=UTC)) == datetime(
        2026, 8, 19, 14, tzinfo=UTC
    )


def test_floor_hour_converts_before_flooring():
    """An offset timezone must land in the correct UTC hour, not its local one."""
    tokyo = datetime(2026, 8, 20, 2, 30, tzinfo=timezone(timedelta(hours=9)))
    assert floor_hour(tokyo) == datetime(2026, 8, 19, 17, tzinfo=UTC)


def test_floor_hour_assumes_utc_for_naive_input():
    naive = datetime(2026, 8, 19, 14, 37)  # noqa: DTZ001 -- naive input is the case under test
    assert floor_hour(naive) == datetime(2026, 8, 19, 14, tzinfo=UTC)


@pytest.mark.parametrize(
    ("status", "expected"), [(200, "2xx"), (204, "2xx"), (404, "4xx"), (503, "5xx")]
)
def test_status_class(status, expected):
    assert status_class(status) == expected


def test_route_key_never_falls_back_to_a_raw_path():
    """A raw path carries document ids; an unmatched request must not leak one."""
    assert route_key("/databases/<database>") == "/databases/<database>"
    assert route_key(None) == UNMATCHED


@pytest.mark.parametrize(
    ("duration", "expected"),
    [(0.0, "5"), (5.0, "5"), (5.1, "10"), (250, "250"), (251, "500"), (10_000, "10000")],
)
def test_bucket_boundaries_are_inclusive_upper_bounds(duration, expected):
    assert bucket_for(duration) == expected


def test_anything_past_the_top_bucket_overflows():
    assert bucket_for(10_001) == OVERFLOW
    assert bucket_for(1e9) == OVERFLOW


def test_bucket_key_separates_components_unambiguously():
    """Two different identities must never collide into one key."""
    hour = datetime(2026, 8, 19, 14, tzinfo=UTC)
    first = bucket_key(hour, "akasha", "/a", "GET", "2xx", "b|c")
    second = bucket_key(hour, "akasha", "/a", "GET", "2xx|b", "c")
    assert first != second


def test_bucket_key_is_stable_across_equivalent_moments():
    early = datetime(2026, 8, 19, 14, 2, tzinfo=UTC)
    late = datetime(2026, 8, 19, 14, 59, tzinfo=UTC)
    assert bucket_key(early, "a", "/r", "GET", "2xx", "w") == bucket_key(
        late, "a", "/r", "GET", "2xx", "w"
    )


def test_merge_counts_is_addition():
    assert merge_counts({"5": 1, "10": 2}, {"10": 3, "25": 1}) == {"5": 1, "10": 5, "25": 1}
    assert merge_counts({}, {}) == {}


def test_percentile_of_no_data_is_none():
    assert percentile_ms({}, 95) is None
    assert percentile_ms({"5": 0}, 95) is None


def test_percentile_resolves_to_the_crossing_bucket():
    counts = {"5": 90, "1000": 10}
    assert percentile_ms(counts, 50) == 5
    assert percentile_ms(counts, 95) == 1000


def test_percentile_of_a_single_observation():
    assert percentile_ms({"250": 1}, 50) == 250
    assert percentile_ms({"250": 1}, 99) == 250


def test_overflow_reports_the_top_bound_and_is_countable_separately():
    counts = {"5": 1, OVERFLOW: 99}
    assert percentile_ms(counts, 95) == BUCKETS_MS[-1]
    assert overflow_count(counts) == 99
    assert overflow_count({"5": 1}) == 0


def test_mean_of_no_requests_is_none():
    assert mean_ms(0.0, 0) is None
    assert mean_ms(30.0, 3) == 10.0
