"""Tests for the page's shaping layer -- stored rows in, page content out.

Pure: no database, no request context. The behaviour worth pinning down is that
series stay dense (a quiet night is a gap on the axis, not a compressed-away
hour) and that the banner only fires when something is actually wrong.
"""

from datetime import UTC, datetime, timedelta

from visualizer.observability.view import (
    DEFAULT_WINDOW_HOURS,
    build_overview,
    window_hours,
)

NOW = datetime(2026, 8, 19, 14, 30, tzinfo=UTC)
TB = 1_000_000_000_000


def _hour(offset: int) -> datetime:
    return (NOW - timedelta(hours=offset)).replace(minute=0, second=0, microsecond=0)


def _request_row(offset=0, **overrides):
    defaults = {
        "hour": _hour(offset),
        "service": "akasha",
        "route": "/x",
        "method": "GET",
        "status_class": "2xx",
        "writer": "mara",
        "count": 4,
        "latency_total_ms": 80.0,
        "buckets": {"25": 3, "250": 1},
        "bytes_in": 10,
        "bytes_out": 90,
    }
    return {**defaults, **overrides}


def _overview(**overrides):
    defaults = {
        "request_rows": [],
        "storage_rows": [],
        "storage_history": [],
        "capacity": None,
        "problems": [],
        "window": "7d",
        "now": NOW,
    }
    return build_overview(**{**defaults, **overrides})


def test_window_names_map_to_hours_and_unknown_falls_back():
    assert window_hours("24h") == 24
    assert window_hours("30d") == 720
    assert window_hours("nonsense") == DEFAULT_WINDOW_HOURS


def test_an_empty_system_renders_without_data():
    overview = _overview()

    assert overview.latency["empty"] is True
    assert overview.errors["empty"] is True
    assert overview.writers == []
    assert overview.hero == "not enough history"
    assert overview.banners == []


# -- series ------------------------------------------------------------------


def test_the_latency_series_has_one_slot_per_hour_in_the_window():
    overview = _overview(request_rows=[_request_row(0)], window="24h")
    assert overview.latency["plot"].slots == 24


def test_quiet_hours_stay_as_gaps_rather_than_being_compressed_away():
    overview = _overview(request_rows=[_request_row(0), _request_row(20)], window="24h")

    # Only the two populated hours appear in the table twin...
    assert len(overview.latency["rows"]) == 2
    # ...but the axis still spans the whole window.
    assert overview.latency["plot"].slots == 24
    assert overview.latency["line"].count("M") == 2


def test_latency_merges_every_route_and_writer_within_an_hour():
    rows = [
        _request_row(0, writer="mara", buckets={"10": 1}),
        _request_row(0, writer="devi", route="/y", buckets={"5000": 1}),
    ]
    overview = _overview(request_rows=rows, window="24h")

    assert overview.latency["rows"][0]["p50"] == 10
    assert overview.latency["rows"][0]["p95"] == 5000


def test_the_end_label_reports_the_most_recent_reading():
    overview = _overview(request_rows=[_request_row(0, buckets={"250": 1})], window="24h")
    assert overview.latency["end"]["label"] == "250ms"


def test_errors_are_split_by_class_and_only_populated_hours_are_listed():
    rows = [
        _request_row(0, status_class="4xx", count=3),
        _request_row(0, status_class="5xx", count=1),
        _request_row(5, status_class="2xx", count=9),
    ]
    overview = _overview(request_rows=rows, window="24h")

    assert overview.errors["empty"] is False
    assert overview.errors["rows"] == [{"hour": _hour(0), "client": 3, "server": 1}]


def test_successful_traffic_alone_leaves_the_error_chart_empty():
    overview = _overview(request_rows=[_request_row(0)], window="24h")
    assert overview.errors["empty"] is True


def test_naive_stored_timestamps_still_land_in_the_right_hour():
    """MongoDB hands back naive datetimes; they are UTC by construction."""
    row = _request_row(0)
    row["hour"] = row["hour"].replace(tzinfo=None)
    overview = _overview(request_rows=[row], window="24h")

    assert len(overview.latency["rows"]) == 1


def test_x_axis_labels_always_include_the_final_slot():
    overview = _overview(request_rows=[_request_row(0)], window="24h")
    ticks = overview.latency["ticks"]

    assert len(ticks) >= 2
    assert ticks[-1]["x"] == overview.latency["plot"].x_for(23)


# -- writers -----------------------------------------------------------------


def test_writers_combine_storage_and_request_activity():
    overview = _overview(
        storage_rows=[{"writer": "mara", "owns": 900, "authored": 100, "records": 4}],
        request_rows=[_request_row(0, writer="mara", count=7, buckets={"250": 7})],
    )

    row = overview.writers[0]
    assert (row.writer, row.owns, row.authored, row.total) == ("mara", 900, 100, 1000)
    assert row.requests == 7
    assert row.p95_ms == 250


def test_a_writer_with_traffic_but_no_storage_still_appears():
    overview = _overview(request_rows=[_request_row(0, writer="devi")])
    assert [row.writer for row in overview.writers] == ["devi"]


def test_a_writer_with_storage_but_no_traffic_still_appears():
    overview = _overview(
        storage_rows=[{"writer": "jun", "owns": 5, "authored": 0, "records": 1}]
    )
    row = overview.writers[0]
    assert (row.writer, row.requests, row.p95_ms) == ("jun", 0, None)


def test_writers_are_ordered_by_total_storage():
    overview = _overview(
        storage_rows=[
            {"writer": "ada", "owns": 10, "authored": 0, "records": 1},
            {"writer": "zoe", "owns": 900, "authored": 0, "records": 1},
        ]
    )
    assert [row.writer for row in overview.writers] == ["zoe", "ada"]


def test_only_server_errors_count_against_a_writer():
    overview = _overview(
        request_rows=[
            _request_row(0, status_class="4xx", count=8),
            _request_row(0, status_class="5xx", count=2),
        ]
    )
    assert overview.writers[0].errors == 2


def test_the_bar_scale_is_the_largest_writer():
    overview = _overview(
        storage_rows=[
            {"writer": "ada", "owns": 10, "authored": 0, "records": 1},
            {"writer": "zoe", "owns": 900, "authored": 0, "records": 1},
        ]
    )
    assert overview.max_writer_total == 900


# -- routes ------------------------------------------------------------------


def test_routes_aggregate_across_hours_writers_and_status():
    rows = [
        _request_row(0, route="/a", count=2, buckets={"25": 2}),
        _request_row(5, route="/a", writer="devi", count=3, buckets={"250": 3}),
        _request_row(1, route="/a", status_class="5xx", count=1, buckets={"25": 1}),
    ]
    overview = _overview(request_rows=rows)

    assert len(overview.routes) == 1
    route = overview.routes[0]
    assert route.requests == 6
    assert route.server_errors == 1
    assert route.p95_ms == 250


def test_routes_separate_by_method():
    rows = [_request_row(0, route="/a", method="GET"), _request_row(0, route="/a", method="POST")]
    assert len(_overview(request_rows=rows).routes) == 2


def test_routes_are_ordered_by_traffic():
    rows = [
        _request_row(0, route="/quiet", count=1),
        _request_row(0, route="/busy", count=50),
    ]
    assert [route.route for route in _overview(request_rows=rows).routes] == ["/busy", "/quiet"]


def test_the_routes_table_is_capped():
    from visualizer.observability.view import ROUTE_LIMIT

    rows = [_request_row(0, route=f"/r{index}") for index in range(ROUTE_LIMIT + 8)]
    assert len(_overview(request_rows=rows).routes) == ROUTE_LIMIT


def test_route_ordering_is_stable_when_traffic_ties():
    rows = [_request_row(0, route="/b", count=5), _request_row(0, route="/a", count=5)]
    assert [route.route for route in _overview(request_rows=rows).routes] == ["/a", "/b"]


# -- capacity and banners ----------------------------------------------------


def _capacity(free_tb=1.2, total_tb=4.0):
    return {
        "volume_total": int(total_tb * TB),
        "volume_free": int(free_tb * TB),
        "memory_total": 8_000_000_000,
        "memory_available": 4_000_000_000,
        "mongo_bytes": 2_100_000_000,
    }


def test_meters_describe_each_resource():
    overview = _overview(capacity=_capacity())
    labels = {meter.label: meter for meter in overview.meters}

    assert labels["Volume"].percent == 70
    assert labels["Memory"].percent == 50
    assert labels["MongoDB"].detail == "2.1 GB"


def test_a_full_volume_warns_and_then_alarms():
    assert _overview(capacity=_capacity(free_tb=1.2)).banners == []
    assert _overview(capacity=_capacity(free_tb=0.8)).banners  # 80% used
    danger = _overview(capacity=_capacity(free_tb=0.2)).meters[0]
    assert danger.severity == "danger"


def test_the_projection_uses_observed_growth():
    history = [
        {"day": datetime(2026, 7, 20, tzinfo=UTC), "owns": 0, "authored": 0},
        {"day": datetime(2026, 8, 19, tzinfo=UTC), "owns": 30_000_000_000, "authored": 0},
    ]
    overview = _overview(capacity=_capacity(free_tb=1.2), storage_history=history)

    assert "years" in overview.hero
    assert "/month" in overview.hero_detail


def test_an_imminent_fill_raises_a_banner():
    history = [
        {"day": datetime(2026, 8, 12, tzinfo=UTC), "owns": 0, "authored": 0},
        {"day": datetime(2026, 8, 19, tzinfo=UTC), "owns": 700_000_000_000, "authored": 0},
    ]
    overview = _overview(capacity=_capacity(free_tb=1.2), storage_history=history)

    assert any("fills in" in banner for banner in overview.banners)


def test_daily_totals_sum_every_writer_for_that_day():
    day = datetime(2026, 8, 12, tzinfo=UTC)
    history = [
        {"day": day, "owns": 100, "authored": 0},
        {"day": day, "owns": 50, "authored": 50},
        {"day": datetime(2026, 8, 19, tzinfo=UTC), "owns": 400_000_000_000, "authored": 0},
    ]
    overview = _overview(capacity=_capacity(), storage_history=history)
    assert overview.hero != "not enough history"


def test_a_capped_cardinality_period_is_flagged():
    overview = _overview(request_rows=[_request_row(0, route="<overflow>")])
    assert overview.truncated is True


def test_total_requests_covers_the_whole_window():
    overview = _overview(request_rows=[_request_row(0, count=4), _request_row(3, count=6)])
    assert overview.total_requests == 10
