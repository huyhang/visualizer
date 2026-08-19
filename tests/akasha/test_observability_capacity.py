"""Tests for capacity judgement: thresholds, growth and the fill projection.

All pure. The projection is the number the page leads with, so the cases that
matter most are the ones where it must decline to answer rather than invent a
figure from noise.
"""

from datetime import date

import pytest

from visualizer.observability.capacity import (
    DANGER,
    OK,
    WARN,
    CapacitySample,
    StaticCapacitySource,
    format_bytes,
    format_months,
    growth_per_day,
    months_until_full,
    severity,
    used_fraction,
)

_GB = 1_000_000_000


def test_used_fraction_of_a_known_volume():
    assert used_fraction(100, 25) == 0.75


@pytest.mark.parametrize(("total", "free"), [(None, 10), (100, None), (0, 0)])
def test_used_fraction_is_unknown_without_both_numbers(total, free):
    assert used_fraction(total, free) is None


def test_used_fraction_is_clamped_against_inconsistent_readings():
    assert used_fraction(100, 200) == 0.0
    assert used_fraction(100, -50) == 1.0


@pytest.mark.parametrize(
    ("fraction", "expected"),
    [(None, OK), (0.0, OK), (0.74, OK), (0.75, WARN), (0.89, WARN), (0.90, DANGER), (1.0, DANGER)],
)
def test_severity_bands(fraction, expected):
    assert severity(fraction) == expected


# -- growth ------------------------------------------------------------------


def test_growth_needs_at_least_two_days():
    assert growth_per_day([]) is None
    assert growth_per_day([(date(2026, 8, 1), 100)]) is None


def test_growth_is_the_slope_across_the_window():
    points = [(date(2026, 8, 1), 100), (date(2026, 8, 11), 1100)]
    assert growth_per_day(points) == 100.0


def test_growth_ignores_the_order_rows_arrive_in():
    points = [(date(2026, 8, 11), 1100), (date(2026, 8, 1), 100)]
    assert growth_per_day(points) == 100.0


def test_flat_or_shrinking_storage_projects_nothing():
    """Better to say "not enough history" than to invent a fill date."""
    assert growth_per_day([(date(2026, 8, 1), 500), (date(2026, 8, 11), 500)]) is None
    assert growth_per_day([(date(2026, 8, 1), 900), (date(2026, 8, 11), 100)]) is None


def test_several_readings_on_one_day_do_not_divide_by_zero():
    assert growth_per_day([(date(2026, 8, 1), 100), (date(2026, 8, 1), 900)]) is None


# -- projection --------------------------------------------------------------


def test_months_until_full_at_a_known_rate():
    # 30.44 GB free, growing 1 GB/day -> about one month.
    assert months_until_full(int(30.44 * _GB), float(_GB)) == pytest.approx(1.0, rel=1e-3)


@pytest.mark.parametrize(
    ("free", "per_day"), [(None, 100.0), (0, 100.0), (1000, None), (1000, 0.0), (1000, -5.0)]
)
def test_no_projection_without_both_halves(free, per_day):
    assert months_until_full(free, per_day) is None


# -- presentation ------------------------------------------------------------


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        (None, "—"),
        (0, "0 B"),
        (999, "999 B"),
        (1_000, "1.0 KB"),
        (1_400_000_000, "1.4 GB"),
        (2_700_000_000_000, "2.7 TB"),
        # Past three digits the decimal is noise, and TB is the last unit, so
        # an implausibly large volume still reads cleanly rather than overflowing.
        (9_000_000_000_000_000, "9000 TB"),
    ],
)
def test_format_bytes(size, expected):
    assert format_bytes(size) == expected


@pytest.mark.parametrize(
    ("months", "expected"),
    [
        (None, "not enough history"),
        (0.2, "under a month"),
        (0.9, "≈ 1 month"),
        (14.0, "≈ 14 months"),
        (36.0, "≈ 3 years"),
    ],
)
def test_format_months(months, expected):
    assert format_months(months) == expected


def test_a_static_source_returns_what_it_was_given():
    sample = CapacitySample(volume_total=100, volume_free=25)
    assert StaticCapacitySource(sample).sample() is sample


def test_a_sample_serialises_every_field_even_when_unknown():
    record = CapacitySample().as_record()
    assert set(record) == {
        "volume_total",
        "volume_free",
        "memory_total",
        "memory_available",
        "mongo_bytes",
    }
    assert all(value is None for value in record.values())
