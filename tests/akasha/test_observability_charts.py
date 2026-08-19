"""Tests for the pure SVG geometry.

The load-bearing property is containment: whatever the data does -- empty,
single point, all zeros, a value far above the axis -- no coordinate may land
outside the viewBox, because the page has no client-side code to rescue it.
"""

import re

import pytest

from visualizer.observability.charts import (
    END_LABEL_OFFSET,
    LABEL_CHAR_WIDTH,
    Plot,
    band_path,
    columns,
    gridlines,
    last_reading,
    line_path,
    nice_ceiling,
    plot_for,
)

_NUMBER = re.compile(r"-?\d+\.?\d*")


def _coordinates(path: str) -> list[tuple[float, float]]:
    numbers = [float(match) for match in _NUMBER.findall(path)]
    return list(zip(numbers[::2], numbers[1::2], strict=True))


def _assert_inside(plot: Plot, path: str) -> None:
    for x, y in _coordinates(path):
        assert -0.01 <= x <= plot.width + 0.01, f"x {x} outside 0..{plot.width}"
        assert -0.01 <= y <= plot.height + 0.01, f"y {y} outside 0..{plot.height}"


# -- axis scaling ------------------------------------------------------------


@pytest.mark.parametrize(
    ("largest", "expected"),
    [(None, 1.0), (0, 1.0), (-5, 1.0), (0.4, 0.5), (1, 1.0), (3, 5.0), (12, 20.0), (180, 200.0)],
)
def test_nice_ceiling_rounds_up_to_a_readable_number(largest, expected):
    assert nice_ceiling(largest) == expected


def test_nice_ceiling_is_never_below_the_data():
    for value in (1, 7, 99, 101, 1234, 98765):
        assert nice_ceiling(value) >= value


# -- containment -------------------------------------------------------------


def test_an_empty_series_produces_an_empty_path_not_a_broken_one():
    plot = plot_for([[]], slots=0)
    assert line_path(plot, []) == ""
    assert band_path(plot, [], []) == ""
    assert columns(plot, []) == []


def test_an_all_none_series_draws_nothing():
    values = [None] * 5
    plot = plot_for([values], slots=5)
    assert line_path(plot, values) == ""
    assert columns(plot, values) == []


def test_a_single_reading_still_renders():
    """A zero-length path draws nothing at all, so a lone point needs a stub."""
    plot = plot_for([[42]], slots=1)
    path = line_path(plot, [42])
    assert path
    _assert_inside(plot, path)


def test_all_zero_values_sit_on_the_baseline_and_stay_inside():
    values = [0, 0, 0]
    plot = plot_for([values], slots=3)
    path = line_path(plot, values)
    _assert_inside(plot, path)
    assert all(abs(y - plot.baseline) < 0.01 for _, y in _coordinates(path))


def test_values_above_the_axis_top_are_clamped_into_the_plot():
    plot = Plot(y_max=100, slots=3)
    path = line_path(plot, [10, 10_000, 10])
    _assert_inside(plot, path)


def test_indexes_beyond_the_slot_count_are_clamped():
    plot = Plot(slots=3)
    assert plot.x_for(99) == plot.x_for(2)
    assert plot.x_for(-5) == plot.x_for(0)


def test_the_viewbox_leaves_room_for_the_axis_band():
    """A container sized to ``height`` must not clip the x-axis labels."""
    plot = Plot()
    assert plot.baseline < plot.height
    assert plot.height - plot.baseline >= 12


def test_the_left_gutter_fits_the_widest_y_axis_label():
    """``10000ms`` is the widest the latency axis can produce; it must not
    hang off the left edge of the viewBox."""
    plot = Plot()
    widest = len("10000ms") * LABEL_CHAR_WIDTH
    # The tick is drawn 6 units left of the plot area, anchored at its end.
    assert plot.pad_left - 6 - widest >= 0


def test_the_right_gutter_fits_the_widest_end_label():
    plot = Plot(slots=10)
    widest = len("10000ms") * LABEL_CHAR_WIDTH
    rightmost = plot.x_for(plot.slots - 1) + END_LABEL_OFFSET + widest
    assert rightmost <= plot.width


def test_long_series_stay_inside_the_viewbox():
    values = [i % 37 for i in range(720)]
    plot = plot_for([values], slots=len(values))
    _assert_inside(plot, line_path(plot, values))
    for column in columns(plot, values):
        assert column.x >= -0.01
        assert column.x + column.width <= plot.width + 0.01
        assert column.y + column.height <= plot.baseline + 0.01


# -- shapes ------------------------------------------------------------------


def test_a_gap_lifts_the_pen_rather_than_bridging_it():
    values = [1, 2, None, 4, 5]
    plot = plot_for([values], slots=5)
    assert line_path(plot, values).count("M") == 2


def test_a_band_needs_both_edges_present():
    plot = plot_for([[1, 2], [3, 4]], slots=2)
    assert band_path(plot, [1, None], [3, 4]).count("M") == 1
    assert band_path(plot, [None, None], [3, 4]) == ""


def test_a_band_closes_its_shape():
    plot = plot_for([[1, 1], [3, 3]], slots=2)
    assert band_path(plot, [1, 1], [3, 3]).endswith("Z")


def test_columns_skip_empty_slots_rather_than_drawing_hairlines():
    plot = plot_for([[0, 5, None, 3]], slots=4)
    assert len(columns(plot, [0, 5, None, 3])) == 2


def test_columns_are_capped_in_width_so_the_band_keeps_air():
    plot = plot_for([[1, 1]], slots=2)
    assert all(column.width <= 14.0 for column in columns(plot, [1, 1]))


def test_dense_columns_stay_at_least_a_pixel_wide():
    values = [1] * 500
    plot = plot_for([values], slots=len(values))
    assert all(column.width >= 1.0 for column in columns(plot, values))


def test_gridlines_span_the_axis_and_stay_inside():
    plot = Plot(y_max=200)
    lines = gridlines(plot, divisions=2)
    assert [value for value, _ in lines] == [100.0, 200.0]
    assert all(plot.pad_top - 0.01 <= y <= plot.baseline for _, y in lines)


def test_last_reading_finds_the_final_populated_slot():
    assert last_reading([1, 2, None]) == (1, 2.0)
    assert last_reading([None, None]) is None
    assert last_reading([]) is None
