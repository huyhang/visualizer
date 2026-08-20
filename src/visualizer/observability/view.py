"""Turns stored rows into exactly what the admin template renders.

Kept apart from both the store and the template so the shaping decisions --
which hour a reading belongs in, how a percentile becomes a chart point, when a
banner appears -- are ordinary functions over plain dictionaries, testable
without a database or a request context.

Series are built *dense*: one slot per hour across the whole window, with
``None`` where nothing was recorded, so a quiet night renders as a gap in the
line rather than being compressed out of the axis.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from . import charts
from .aggregation import merge_counts, percentile_ms
from .alerts import Alert, Thresholds
from .alerts import evaluate as evaluate_alerts
from .capacity import (
    format_bytes,
    format_months,
    growth_per_day,
    months_until_full,
    severity,
    used_fraction,
)

DEFAULT_WINDOW_HOURS = 168  # seven days

# Windows the filter row offers, in hours.
WINDOWS = {"24h": 24, "7d": 168, "30d": 720}
DEFAULT_WINDOW = "7d"

# Endpoints listed in the routes table. Past this the tail is noise, and the
# cap is stated on the page rather than silently truncating.
ROUTE_LIMIT = 15


@dataclass(frozen=True)
class Meter:
    label: str
    detail: str
    percent: int
    severity: str


@dataclass(frozen=True)
class WriterRow:
    writer: str
    owns: int
    authored: int
    records: int
    requests: int
    errors: int
    p95_ms: int | None

    @property
    def total(self) -> int:
        return self.owns + self.authored

    @property
    def total_label(self) -> str:
        return format_bytes(self.total)

    @property
    def owns_label(self) -> str:
        return format_bytes(self.owns)

    @property
    def authored_label(self) -> str:
        return format_bytes(self.authored)


@dataclass(frozen=True)
class RouteRow:
    service: str
    route: str
    method: str
    requests: int
    p95_ms: int | None
    client_errors: int
    server_errors: int


@dataclass(frozen=True)
class Overview:
    window: str
    hero: str
    hero_detail: str
    meters: list[Meter]
    writers: list[WriterRow]
    routes: list[RouteRow]
    latency: dict
    errors: dict
    problems: list[dict]
    alerts: list[Alert]
    total_requests: int
    truncated: bool

    @property
    def max_writer_total(self) -> int:
        """Largest per-writer total, so the inline bars compare across rows."""
        return max((row.total for row in self.writers), default=0)


def window_hours(name: str) -> int:
    return WINDOWS.get(name, DEFAULT_WINDOW_HOURS)


def build_overview(
    *,
    request_rows: list[dict],
    storage_rows: list[dict],
    storage_history: list[dict],
    capacity: dict | None,
    problems: list[dict],
    window: str = DEFAULT_WINDOW,
    now: datetime | None = None,
    thresholds: Thresholds | None = None,
) -> Overview:
    """Assemble everything the observability page shows."""
    moment = now or datetime.now(UTC)
    hours = _hour_slots(moment, window_hours(window))
    by_hour = _group_by_hour(request_rows)
    meters = _meters(capacity)
    per_day = growth_per_day(_daily_totals(storage_history))
    free = (capacity or {}).get("volume_free")
    months = months_until_full(free, per_day)
    return Overview(
        window=window,
        hero=format_months(months),
        hero_detail=_hero_detail(per_day, free),
        meters=meters,
        writers=_writers(storage_rows, request_rows),
        routes=_routes(request_rows),
        latency=_latency_chart(hours, by_hour),
        errors=_error_chart(hours, by_hour),
        problems=problems,
        # Structured, not sentences: the same evaluation feeds the banner here
        # and any future off-box notifier. See ``alerts``.
        alerts=evaluate_alerts(capacity, months, thresholds),
        total_requests=sum(row.get("count", 0) for row in request_rows),
        truncated=any(row.get("route") == "<overflow>" for row in request_rows),
    )


# -- capacity ----------------------------------------------------------------


def _meters(capacity: dict | None) -> list[Meter]:
    capacity = capacity or {}
    volume = used_fraction(capacity.get("volume_total"), capacity.get("volume_free"))
    memory = used_fraction(
        capacity.get("memory_total"), capacity.get("memory_available")
    )
    meters = [
        _meter("Volume", volume, capacity.get("volume_total"), capacity.get("volume_free")),
        _meter(
            "Memory", memory, capacity.get("memory_total"), capacity.get("memory_available")
        ),
    ]
    mongo = capacity.get("mongo_bytes")
    if mongo is not None:
        volume_total = capacity.get("volume_total") or 0
        share = mongo / volume_total if volume_total else 0.0
        meters.append(
            Meter(
                label="MongoDB",
                detail=format_bytes(mongo),
                percent=round(share * 100),
                # Informational: MongoDB's own size is a component of the
                # volume meter above, not a separate thing that can fill up.
                severity="ok",
            )
        )
    return meters


def _meter(label: str, fraction: float | None, total, free) -> Meter:
    used = None if total is None or free is None else total - free
    detail = "—" if used is None else f"{format_bytes(used)} of {format_bytes(total)}"
    return Meter(
        label=label,
        detail=detail,
        percent=round((fraction or 0) * 100),
        severity=severity(fraction),
    )


def _hero_detail(per_day: float | None, free: int | None) -> str:
    if per_day is None:
        return "storage is flat or too new to project"
    monthly = format_bytes(int(per_day * 30.44))
    return f"at {monthly}/month, with {format_bytes(free)} free"


def _daily_totals(storage_history: list[dict]) -> list[tuple[date, int]]:
    """Collapse per-writer daily rows into one total per calendar day."""
    totals: dict[date, int] = {}
    for row in storage_history:
        day = row["day"].date() if hasattr(row["day"], "date") else row["day"]
        totals[day] = totals.get(day, 0) + row.get("owns", 0) + row.get("authored", 0)
    return sorted(totals.items())


# -- writers -----------------------------------------------------------------


def _writers(storage_rows: list[dict], request_rows: list[dict]) -> list[WriterRow]:
    names = {row["writer"] for row in storage_rows} | {
        row["writer"] for row in request_rows
    }
    storage = {row["writer"]: row for row in storage_rows}
    rows = []
    for name in names:
        owned = storage.get(name, {})
        mine = [row for row in request_rows if row["writer"] == name]
        counts: dict[str, int] = {}
        for row in mine:
            counts = merge_counts(counts, row.get("buckets", {}))
        rows.append(
            WriterRow(
                writer=name,
                owns=owned.get("owns", 0),
                authored=owned.get("authored", 0),
                records=owned.get("records", 0),
                requests=sum(row.get("count", 0) for row in mine),
                errors=sum(
                    row.get("count", 0) for row in mine if row.get("status_class") == "5xx"
                ),
                p95_ms=percentile_ms(counts, 95),
            )
        )
    return sorted(rows, key=lambda row: (-row.total, -row.requests, row.writer))


# -- routes ------------------------------------------------------------------


def _routes(request_rows: list[dict], limit: int = ROUTE_LIMIT) -> list[RouteRow]:
    """Busiest endpoints first -- the follow-up to "p95 is high, but where?".

    Ordered by request count rather than latency so the table describes where
    the load actually is; a slow-but-rare endpoint surfaces in the problems
    table instead of displacing everything real.
    """
    grouped: dict[tuple[str, str, str], list[dict]] = {}
    for row in request_rows:
        key = (row.get("service", ""), row.get("route", ""), row.get("method", ""))
        grouped.setdefault(key, []).append(row)
    rows = []
    for (service, route, method), matching in grouped.items():
        counts: dict[str, int] = {}
        for row in matching:
            counts = merge_counts(counts, row.get("buckets", {}))
        rows.append(
            RouteRow(
                service=service,
                route=route,
                method=method,
                requests=sum(row.get("count", 0) for row in matching),
                p95_ms=percentile_ms(counts, 95),
                client_errors=_class_total(matching, "4xx"),
                server_errors=_class_total(matching, "5xx"),
            )
        )
    rows.sort(key=lambda row: (-row.requests, row.route, row.method))
    return rows[:limit]


def _class_total(rows: list[dict], status_class: str) -> int:
    return sum(row.get("count", 0) for row in rows if row.get("status_class") == status_class)


# -- time series -------------------------------------------------------------


def _hour_slots(moment: datetime, count: int) -> list[datetime]:
    latest = moment.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    return [latest - timedelta(hours=offset) for offset in range(count - 1, -1, -1)]


def _group_by_hour(request_rows: list[dict]) -> dict[datetime, list[dict]]:
    grouped: dict[datetime, list[dict]] = {}
    for row in request_rows:
        hour = row["hour"]
        hour = hour.replace(tzinfo=UTC) if hour.tzinfo is None else hour.astimezone(UTC)
        grouped.setdefault(hour, []).append(row)
    return grouped


def _latency_chart(hours: list[datetime], by_hour: dict) -> dict:
    p50: list[float | None] = []
    p95: list[float | None] = []
    for hour in hours:
        counts: dict[str, int] = {}
        for row in by_hour.get(hour, ()):
            counts = merge_counts(counts, row.get("buckets", {}))
        p50.append(percentile_ms(counts, 50))
        p95.append(percentile_ms(counts, 95))
    plot = charts.plot_for([p50, p95], slots=len(hours))
    end = charts.last_reading(p95)
    return {
        "plot": plot,
        "band": charts.band_path(plot, p50, p95),
        "line": charts.line_path(plot, p95),
        "gridlines": charts.gridlines(plot),
        "ticks": _time_ticks(plot, hours),
        "end": None
        if end is None
        else {
            "x": plot.x_for(end[0]),
            "y": plot.y_for(end[1]),
            # The offset lives with the geometry that reserves room for it.
            "label_x": plot.x_for(end[0]) + charts.END_LABEL_OFFSET,
            "label": f"{end[1]:.0f}ms",
        },
        "empty": end is None,
        "rows": _latency_rows(hours, p50, p95),
    }


def _latency_rows(hours, p50, p95) -> list[dict]:
    """The table twin: every plotted value, reachable without hovering."""
    return [
        {"hour": hour, "p50": low, "p95": high}
        for hour, low, high in zip(hours, p50, p95, strict=True)
        if high is not None
    ]


def _error_chart(hours: list[datetime], by_hour: dict) -> dict:
    client: list[int] = []
    server: list[int] = []
    for hour in hours:
        rows = by_hour.get(hour, ())
        client.append(sum(r.get("count", 0) for r in rows if r.get("status_class") == "4xx"))
        server.append(sum(r.get("count", 0) for r in rows if r.get("status_class") == "5xx"))
    plot = charts.plot_for([client, server], slots=len(hours))
    return {
        "plot": plot,
        "client": charts.columns(plot, client),
        "server": charts.columns(plot, server),
        "gridlines": charts.gridlines(plot),
        "ticks": _time_ticks(plot, hours),
        "empty": not any(client) and not any(server),
        "rows": [
            {"hour": hour, "client": c, "server": s}
            for hour, c, s in zip(hours, client, server, strict=True)
            if c or s
        ],
    }


def _time_ticks(plot: charts.Plot, hours: list[datetime]) -> list[dict]:
    """Roughly four evenly spaced x labels, always including the last slot."""
    if not hours:
        return []
    step = max(1, len(hours) // 4)
    indexes = list(range(0, len(hours), step))
    if indexes[-1] != len(hours) - 1:
        indexes.append(len(hours) - 1)
    return [
        {"x": plot.x_for(index), "label": hours[index].strftime("%a %H:%M")}
        for index in indexes
    ]
