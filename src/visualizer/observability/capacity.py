"""Host capacity: the part of the question the application cannot answer itself.

No amount of request instrumentation tells you the volume is 85 percent full,
so this samples the host directly. The judgement -- what counts as a warning,
how fast storage is growing, how long that leaves -- is pure and lives at the
top of the file; the sampling that has to touch the operating system is an
injected seam at the bottom.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Protocol

# Fractions of a resource in use at which the admin console starts warning.
WARN_AT = 0.75
DANGER_AT = 0.90

_DAYS_PER_MONTH = 30.44
_MEMINFO = "/proc/meminfo"

OK, WARN, DANGER = "ok", "warn", "danger"


@dataclass(frozen=True)
class CapacitySample:
    volume_total: int | None = None
    volume_free: int | None = None
    memory_total: int | None = None
    memory_available: int | None = None
    mongo_bytes: int | None = None

    def as_record(self) -> dict:
        return {
            "volume_total": self.volume_total,
            "volume_free": self.volume_free,
            "memory_total": self.memory_total,
            "memory_available": self.memory_available,
            "mongo_bytes": self.mongo_bytes,
        }


class CapacitySource(Protocol):
    def sample(self) -> CapacitySample: ...


# -- pure judgement ----------------------------------------------------------


def used_fraction(total: int | None, free: int | None) -> float | None:
    """How much of a resource is in use, as 0.0-1.0."""
    if not total or free is None:
        return None
    return max(0.0, min(1.0, (total - free) / total))


def severity(fraction: float | None) -> str:
    """Status band for a usage fraction."""
    if fraction is None:
        return OK
    if fraction >= DANGER_AT:
        return DANGER
    if fraction >= WARN_AT:
        return WARN
    return OK


def growth_per_day(points: Iterable[tuple[date, int]]) -> float | None:
    """Average bytes added per day across the observed window.

    Deliberately the endpoint slope over the whole window rather than a fitted
    regression: it needs to be explainable in one sentence on the page, and with
    daily samples over weeks the two barely differ. Returns ``None`` when there
    is not enough history, or when storage is flat or shrinking -- projecting a
    fill date off noise would be worse than saying nothing.
    """
    ordered = sorted(points)
    if len(ordered) < 2:
        return None
    (first_day, first_bytes), (last_day, last_bytes) = ordered[0], ordered[-1]
    elapsed = (last_day - first_day).days
    if elapsed <= 0:
        return None
    per_day = (last_bytes - first_bytes) / elapsed
    return per_day if per_day > 0 else None


def months_until_full(free_bytes: int | None, per_day: float | None) -> float | None:
    """How long the free space lasts at the observed growth rate."""
    if not free_bytes or not per_day or per_day <= 0:
        return None
    return free_bytes / per_day / _DAYS_PER_MONTH


def format_bytes(size: int | None) -> str:
    """Human-readable size, e.g. ``1.4 GB``. Uses decimal units, like the NAS."""
    if size is None:
        return "—"
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < 1000 or unit == "TB":
            precision = 0 if unit == "B" or abs(value) >= 100 else 1
            return f"{value:.{precision}f} {unit}"
        value /= 1000
    return f"{value:.1f} TB"


def format_months(months: float | None) -> str:
    """Phrase a projection the way the page states it."""
    if months is None:
        return "not enough history"
    if months >= 24:
        return f"≈ {months / 12:.0f} years"
    if months >= 1.5:
        return f"≈ {months:.0f} months"
    if months >= 0.5:
        return "≈ 1 month"
    return "under a month"


# -- the sampling seam -------------------------------------------------------


class StaticCapacitySource:
    """A fixed sample -- what the tests inject."""

    def __init__(self, sample: CapacitySample):
        self._sample = sample

    def sample(self) -> CapacitySample:
        return self._sample


class HostCapacitySource:
    """Reads the real host: the data volume, system memory and MongoDB size."""

    def __init__(self, client, data_path: str = "/data"):
        self._client = client
        self._data_path = data_path

    def sample(self) -> CapacitySample:
        volume = shutil.disk_usage(self._data_path)
        memory_total, memory_available = _linux_memory()
        return CapacitySample(
            volume_total=volume.total,
            volume_free=volume.free,
            memory_total=memory_total,
            memory_available=memory_available,
            mongo_bytes=self._mongo_bytes(),
        )

    def _mongo_bytes(self) -> int:
        total = 0
        for name in self._client.list_database_names():
            stats = self._client[name].command("dbStats")
            total += int(stats.get("storageSize", 0)) + int(stats.get("indexSize", 0))
        return total


def _linux_memory() -> tuple[int | None, int | None]:
    """Total and available bytes from ``/proc/meminfo``.

    Returns ``(None, None)`` off Linux -- the NAS is Linux, developer laptops
    frequently are not, and a missing memory reading should render as an em dash
    rather than fail the whole capacity sample.
    """
    wanted = {"MemTotal:": None, "MemAvailable:": None}
    try:
        with open(_MEMINFO, encoding="ascii") as handle:
            for line in handle:
                field, _, rest = line.partition(" ")
                if field in wanted:
                    wanted[field] = int(rest.strip().split()[0]) * 1024
    except OSError:
        return None, None
    return wanted["MemTotal:"], wanted["MemAvailable:"]
