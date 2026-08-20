"""The MongoDB boundary for observability data.

Everything lives in a reserved ``_ops`` database, alongside ``_auth`` and
``_chronos``: never addressable through the document API, and expiring on its
own so it cannot grow into the volume it exists to measure.

The hourly write is the load-bearing detail. Each bucket has a *deterministic*
id derived from its identity, so a flush is a single ``$inc`` upsert that
MongoDB applies atomically. There is no read-modify-write anywhere in this file,
which is what makes concurrent workers merge rather than clobber.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from .aggregation import bucket_key
from .recorder import Bucket, Problem

OPS_DB = "_ops"

REQUEST_HOURS = "request_hours"
PROBLEMS = "problems"
SETTINGS = "settings"
STORAGE_DAYS = "storage_days"
CAPACITY = "capacity"
ALERTS = "alerts"

# Hourly buckets and daily storage rows are the long-range trend, so they are
# kept for a little over a year. Problem detail is bounded by row count instead
# (see ``add_problems``) because its usefulness falls off within days.
_RETENTION = timedelta(days=400)
_MONITORING_KEY = "monitoring_enabled"
_CAPACITY_KEY = "latest"
_ALERTS_KEY = "active"
_DEFAULT_PROBLEMS_KEPT = 500


class MetricsStore:
    """CRUD over the ``_ops`` collections. Holds no policy."""

    def __init__(self, client, retention: timedelta = _RETENTION):
        self._client = client
        self._retention = retention

    @property
    def _hours(self):
        return self._client[OPS_DB][REQUEST_HOURS]

    @property
    def _problems(self):
        return self._client[OPS_DB][PROBLEMS]

    @property
    def _settings(self):
        return self._client[OPS_DB][SETTINGS]

    @property
    def _storage(self):
        return self._client[OPS_DB][STORAGE_DAYS]

    @property
    def _capacity(self):
        return self._client[OPS_DB][CAPACITY]

    @property
    def _alerts(self):
        return self._client[OPS_DB][ALERTS]

    def ensure_indexes(self) -> None:
        """Create the TTL and query indexes.

        Called explicitly at startup rather than from ``__init__`` so a failure
        is visible to the caller. A silently swallowed index error means the TTL
        never exists and the "it expires on its own" promise quietly lapses.
        """
        self._hours.create_index("expires_at", expireAfterSeconds=0)
        self._hours.create_index("hour")
        self._storage.create_index("expires_at", expireAfterSeconds=0)
        self._storage.create_index("day")
        self._problems.create_index("at")

    # -- the durable switch --------------------------------------------------

    def get_monitoring_enabled(self) -> bool | None:
        record = self._settings.find_one({"_id": _MONITORING_KEY})
        return None if record is None else bool(record.get("value"))

    def set_monitoring_enabled(self, enabled: bool) -> None:
        self._settings.update_one(
            {"_id": _MONITORING_KEY}, {"$set": {"value": bool(enabled)}}, upsert=True
        )

    # -- request telemetry ---------------------------------------------------

    def add_buckets(self, buckets: Iterable[Bucket]) -> int:
        """Merge drained buckets into their hours. Atomic per bucket.

        One ``update_one`` per bucket rather than a single ``bulk_write``: a
        flush carries a few dozen buckets at most, every few minutes, off the
        request path, so the extra round trips are free -- and the bulk update
        path is not usable across the mongomock/pymongo pairing the tests run
        on. Each individual write is still an atomic upsert, which is the
        property that actually matters.

        Returns the number of buckets written.
        """
        written = 0
        for bucket in buckets:
            query, update = self._bucket_write(bucket)
            self._hours.update_one(query, update, upsert=True)
            written += 1
        return written

    def _bucket_write(self, bucket: Bucket) -> tuple[dict, dict]:
        increments = {
            "count": bucket.count,
            "latency_total_ms": bucket.latency_total_ms,
            "bytes_in": bucket.bytes_in,
            "bytes_out": bucket.bytes_out,
        }
        for label, hits in bucket.buckets.items():
            increments[f"buckets.{label}"] = hits
        key = bucket_key(
            bucket.hour,
            bucket.service,
            bucket.route,
            bucket.method,
            bucket.status_class,
            bucket.writer,
        )
        return (
            {"_id": key},
            {
                "$inc": increments,
                "$setOnInsert": {
                    "hour": bucket.hour,
                    "service": bucket.service,
                    "route": bucket.route,
                    "method": bucket.method,
                    "status_class": bucket.status_class,
                    "writer": bucket.writer,
                    "expires_at": bucket.hour + self._retention,
                },
            },
        )

    def request_hours(self, since: datetime | None = None) -> list[dict]:
        """Hourly buckets at or after ``since``, oldest first."""
        query = {"hour": {"$gte": since}} if since is not None else {}
        return [_public(row) for row in self._hours.find(query).sort("hour", 1)]

    # -- problem detail ------------------------------------------------------

    def add_problems(
        self, problems: Iterable[Problem], keep: int = _DEFAULT_PROBLEMS_KEPT
    ) -> None:
        """Append slow/failed rows and trim back to the newest ``keep``.

        A MongoDB capped collection would self-trim, but capped collections are
        not available in the in-memory client the tests use. An explicit trim is
        a few lines, provably bounded, and behaves identically in both.
        """
        rows = [
            {
                "at": problem.at,
                "service": problem.service,
                "route": problem.route,
                "method": problem.method,
                "writer": problem.writer,
                "status": problem.status,
                "duration_ms": problem.duration_ms,
                "error": problem.error,
            }
            for problem in problems
        ]
        if rows:
            self._problems.insert_many(rows)
        self._trim_problems(keep)

    def _trim_problems(self, keep: int) -> None:
        surplus = self._problems.count_documents({}) - keep
        if surplus <= 0:
            return
        stale = self._problems.find({}, {"_id": 1}).sort("at", 1).limit(surplus)
        self._problems.delete_many({"_id": {"$in": [row["_id"] for row in stale]}})

    def problems(self, limit: int = 50) -> list[dict]:
        """The most recent slow/failed requests, newest first."""
        cursor = self._problems.find({}).sort("at", -1).limit(limit)
        return [_public(row) for row in cursor]

    # -- storage accounting --------------------------------------------------

    def save_storage(self, day: datetime, rows: Iterable[dict]) -> int:
        """Replace the storage attribution recorded for ``day``.

        A day's scan supersedes any earlier scan of the same day, so re-running
        it converges instead of accumulating.
        """
        written = 0
        for row in rows:
            self._storage.update_one(
                {"_id": f"{day.date().isoformat()}\x1f{row['writer']}"},
                {
                    "$set": {
                        "day": day,
                        "writer": row["writer"],
                        "owns": row["owns"],
                        "authored": row["authored"],
                        "records": row["records"],
                        "expires_at": day + self._retention,
                    }
                },
                upsert=True,
            )
            written += 1
        return written

    def storage_days(self, since: datetime | None = None) -> list[dict]:
        """Daily per-writer storage rows at or after ``since``, oldest first."""
        query = {"day": {"$gte": since}} if since is not None else {}
        return [_public(row) for row in self._storage.find(query).sort("day", 1)]

    def latest_storage_day(self) -> datetime | None:
        newest = self._storage.find({}).sort("day", -1).limit(1)
        rows = list(newest)
        return rows[0]["day"] if rows else None

    # -- host capacity -------------------------------------------------------

    def save_capacity(self, sample: dict) -> None:
        self._capacity.update_one(
            {"_id": _CAPACITY_KEY},
            {"$set": {**sample, "at": sample.get("at") or datetime.now(UTC)}},
            upsert=True,
        )

    def latest_capacity(self) -> dict | None:
        record = self._capacity.find_one({"_id": _CAPACITY_KEY})
        return _public(record) if record else None


    # -- alert state ---------------------------------------------------------

    def save_active_alerts(self, records: list[dict]) -> None:
        """Remember what was firing, so the next scan can report only changes.

        A single document rather than a row per alert: it is read and replaced
        atomically every cycle, so there is no partial state for a diff to
        misread.
        """
        self._alerts.update_one(
            {"_id": _ALERTS_KEY}, {"$set": {"alerts": records}}, upsert=True
        )

    def active_alerts(self) -> list[dict]:
        record = self._alerts.find_one({"_id": _ALERTS_KEY}) or {}
        return list(record.get("alerts", ()))


def _public(row: dict) -> dict:
    """Strip the fields the store owns."""
    return {key: value for key, value in row.items() if key not in ("_id", "expires_at")}
