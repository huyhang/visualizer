"""Pure aggregation rules for request telemetry.

Nothing here touches MongoDB, Flask or the wall clock. Every interesting
decision -- which latency bucket a duration lands in, how a percentile is read
back out of those buckets, what a request is allowed to be labelled with -- is a
plain function, so the rules can be tested exhaustively without a database.

Latency is kept as *bucket counts* rather than retained samples. That costs a
little precision (a percentile resolves to a bucket bound, not an exact value)
and buys three things that matter more here: bounded memory per key, a merge
that is pure addition, and an update that MongoDB can apply atomically -- so two
gunicorn workers incrementing the same hour can never lose each other's counts.
"""

from datetime import UTC, datetime

# Upper bounds in milliseconds. Anything slower falls into ``OVERFLOW``.
BUCKETS_MS = (5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10_000)
OVERFLOW = "inf"
TOP_BUCKET_MS = BUCKETS_MS[-1]

# Routes are stored as Flask rule templates. A request that matched no rule is
# labelled with this instead of its path: a raw path carries document ids and
# usernames, and telemetry must not become a second copy of that.
UNMATCHED = "<unmatched>"

# Components are joined with ASCII unit-separator, which cannot occur in a route
# template or a username, so a composite key can never be ambiguous.
_SEP = "\x1f"


def floor_hour(moment: datetime) -> datetime:
    """Floor ``moment`` to the top of its UTC hour."""
    aware = moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment
    return aware.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def status_class(status: int) -> str:
    """Coarse HTTP status family, e.g. ``503`` -> ``5xx``."""
    return f"{status // 100}xx"


def route_key(rule: str | None) -> str:
    """The stored route label for a matched Flask rule."""
    return rule or UNMATCHED


def bucket_for(duration_ms: float) -> str:
    """The histogram bucket label a duration belongs to."""
    for bound in BUCKETS_MS:
        if duration_ms <= bound:
            return str(bound)
    return OVERFLOW


def bucket_key(
    hour: datetime, service: str, route: str, method: str, klass: str, writer: str
) -> str:
    """A deterministic id for one hourly bucket.

    Deterministic because it is what makes the write a single atomic upsert: no
    read-modify-write, so concurrent workers merge instead of overwriting.
    """
    return _SEP.join(
        (floor_hour(hour).isoformat(), service, route, method, klass, writer)
    )


def merge_counts(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    """Sum two bucket-count maps."""
    return {
        label: left.get(label, 0) + right.get(label, 0)
        for label in set(left) | set(right)
    }


def total_count(counts: dict[str, int]) -> int:
    return sum(counts.values())


def overflow_count(counts: dict[str, int]) -> int:
    """How many requests were slower than the top finite bucket."""
    return counts.get(OVERFLOW, 0)


def percentile_ms(counts: dict[str, int], percentile: float) -> int | None:
    """Upper bound of the bucket the given percentile falls in.

    Returns ``None`` when there is no data. A percentile landing in the overflow
    bucket reports the top finite bound -- pair it with ``overflow_count`` when
    the distinction matters.
    """
    total = total_count(counts)
    if total == 0:
        return None
    target = total * percentile / 100.0
    seen = 0
    for bound in BUCKETS_MS:
        seen += counts.get(str(bound), 0)
        if seen >= target:
            return bound
    return TOP_BUCKET_MS


def mean_ms(latency_total_ms: float, count: int) -> float | None:
    return latency_total_ms / count if count else None
