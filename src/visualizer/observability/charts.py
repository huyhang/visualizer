"""Pure geometry for the server-rendered SVG charts.

No Flask, no data access, no colour -- just values in, coordinates out. Colour
lives in the template as CSS custom properties so the theme's hand-picked dark
steps apply, rather than a light palette being flipped at render time.

Series arrive *dense*: one slot per hour, with ``None`` where nothing was
recorded, so the x axis stays continuous time rather than compressing quiet
hours away. Every function here is total -- empty series, a single point, all
zeros and all-``None`` are ordinary inputs, not edge cases -- and no coordinate
is ever emitted outside the viewBox.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass

Number = float | int | None

# Conservative width of one character of the 10px tick font, used to check that
# axis labels fit inside their gutter. Deliberately generous: the cost of
# over-estimating is a few pixels of air, and of under-estimating is clipped text.
LABEL_CHAR_WIDTH = 6.5

# Distance from the final data point to its end label.
END_LABEL_OFFSET = 8


@dataclass(frozen=True)
class Plot:
    """The drawing area of one chart, in SVG user units.

    ``height`` is the whole viewBox including the axis band, so a caller sizing
    a container to this number cannot end up with the x-axis labels outside it.

    The horizontal gutters are sized for the *widest label the axis can
    produce* -- ``10000ms``, the top latency bucket -- rather than for typical
    values, so a slow period cannot push the y-axis text off the left edge or
    the end label off the right one. See ``LABEL_CHAR_WIDTH``.
    """

    width: int = 640
    height: int = 160
    pad_left: int = 52
    pad_right: int = 58
    pad_top: int = 10
    pad_bottom: int = 22
    y_max: float = 1.0
    slots: int = 1

    @property
    def plot_width(self) -> float:
        return max(1.0, self.width - self.pad_left - self.pad_right)

    @property
    def plot_height(self) -> float:
        return max(1.0, self.height - self.pad_top - self.pad_bottom)

    @property
    def baseline(self) -> float:
        return self.height - self.pad_bottom

    def x_for(self, index: int) -> float:
        """Centre of slot ``index``, clamped into the plot area."""
        if self.slots <= 1:
            return self.pad_left + self.plot_width / 2
        step = self.plot_width / (self.slots - 1)
        return self.pad_left + min(max(index, 0), self.slots - 1) * step

    def y_for(self, value: float) -> float:
        """Vertical position of ``value``, clamped to the plot area."""
        top = max(self.y_max, 1e-9)
        fraction = min(max(value / top, 0.0), 1.0)
        return self.baseline - fraction * self.plot_height


def nice_ceiling(largest: float | None) -> float:
    """A round axis top at or above ``largest`` (1, 2 or 5 times a power of ten)."""
    if not largest or largest <= 0:
        return 1.0
    magnitude = 10.0 ** _floor_log10(largest)
    for step in (1.0, 2.0, 5.0, 10.0):
        candidate = step * magnitude
        if candidate >= largest:
            return candidate
    return 10.0 * magnitude


def plot_for(
    series: Sequence[Sequence[Number]], slots: int, **geometry
) -> Plot:
    """Build a plot sized to hold every value in ``series``."""
    values = [v for one in series for v in one if v is not None]
    return Plot(
        y_max=nice_ceiling(max(values) if values else None),
        slots=max(1, slots),
        **geometry,
    )


def line_path(plot: Plot, values: Sequence[Number]) -> str:
    """An SVG path following ``values``, lifting the pen across gaps."""
    segments = []
    for run in _runs(values):
        points = [f"{plot.x_for(i):.1f},{plot.y_for(values[i]):.1f}" for i in run]
        if len(points) == 1:
            # A lone reading has no line to draw; a zero-length path renders
            # nothing at all, so emit a minimal horizontal stub the dot sits on.
            x, y = points[0].split(",")
            segments.append(f"M{float(x) - 0.5:.1f},{y} L{float(x) + 0.5:.1f},{y}")
        else:
            segments.append("M" + " L".join(points))
    return " ".join(segments)


def band_path(plot: Plot, lows: Sequence[Number], highs: Sequence[Number]) -> str:
    """A closed path filling between two series, one shape per contiguous run."""
    pairs = [
        None if lows[i] is None or highs[i] is None else i
        for i in range(min(len(lows), len(highs)))
    ]
    segments = []
    for run in _runs(pairs):
        upper = [f"{plot.x_for(i):.1f},{plot.y_for(highs[i]):.1f}" for i in run]
        lower = [f"{plot.x_for(i):.1f},{plot.y_for(lows[i]):.1f}" for i in reversed(run)]
        segments.append("M" + " L".join(upper + lower) + " Z")
    return " ".join(segments)


@dataclass(frozen=True)
class Column:
    x: float
    y: float
    width: float
    height: float


def columns(plot: Plot, values: Sequence[Number], max_width: float = 14.0) -> list[Column]:
    """Bars growing from the baseline, capped in width so the band keeps air.

    Zero and ``None`` produce no column rather than a zero-height rectangle,
    which would render as a hairline artefact along the axis.
    """
    slot = plot.plot_width / max(1, plot.slots)
    width = max(1.0, min(max_width, slot - 2.0))
    drawn = []
    for index, value in enumerate(values):
        if not value:
            continue
        top = plot.y_for(value)
        drawn.append(
            Column(
                x=plot.x_for(index) - width / 2,
                y=top,
                width=width,
                height=max(1.0, plot.baseline - top),
            )
        )
    return drawn


def gridlines(plot: Plot, divisions: int = 2) -> list[tuple[float, float]]:
    """``(value, y)`` for each horizontal rule, including the axis top."""
    return [
        (plot.y_max * step / divisions, plot.y_for(plot.y_max * step / divisions))
        for step in range(1, divisions + 1)
    ]


def last_reading(values: Sequence[Number]) -> tuple[int, float] | None:
    """Index and value of the final non-empty slot, for the end label."""
    for index in range(len(values) - 1, -1, -1):
        if values[index] is not None:
            return index, float(values[index])
    return None


def _runs(values: Sequence[Number]) -> Iterator[list[int]]:
    """Contiguous index runs where the series has data."""
    run: list[int] = []
    for index, value in enumerate(values):
        if value is None:
            if run:
                yield run
            run = []
        else:
            run.append(index)
    if run:
        yield run


def _floor_log10(value: float) -> int:
    exponent = 0
    while value >= 10:
        value /= 10
        exponent += 1
    while value < 1:
        value *= 10
        exponent -= 1
    return exponent
