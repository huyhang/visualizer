"""Jobs, in one SQLite file that survives restarts.

The queue, each job's progress, and finished results until they expire. One
connection behind one lock: a handful of jobs an hour does not need more, and
it keeps the state machine in plain sight.

Privacy is part of the schema, not an afterthought:

- a job's **input** (for a review, a chapter of unpublished prose) is erased the
  moment the job finishes; only a hash is kept, for idempotency;
- **results** are deleted at ``expires_at``;
- ``secure_delete`` overwrites deleted rows instead of leaving them in free
  pages of the file.

A research job asked to have its plan approved parks in ``awaiting_approval``
between two runs: its input is kept (the job is not finished), and if nobody
approves the plan by ``plan_expires_at`` the sweep fails it as ``plan_expired``.
"""

import json
import secrets
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,
    id           TEXT NOT NULL UNIQUE,
    kind         TEXT NOT NULL,
    state        TEXT NOT NULL,
    idem_key     TEXT UNIQUE,
    body_hash    TEXT NOT NULL,
    request      TEXT,
    stage        TEXT,
    message      TEXT,
    created_at   TEXT NOT NULL,
    started_at   TEXT,
    finished_at  TEXT,
    expires_at   TEXT,
    result       TEXT,
    error        TEXT,
    plan         TEXT,
    plan_expires_at TEXT
);
CREATE INDEX IF NOT EXISTS jobs_by_state ON jobs (state, seq);
"""

FINISHED = ("done", "failed", "cancelled")
# Columns added after the first schema, for job files that predate them.
_ADDED_COLUMNS = {"plan": "TEXT", "plan_expires_at": "TEXT"}


def _iso(moment: datetime) -> str:
    # Fixed width and always UTC, so the stored strings also sort as times.
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class JobStore:
    def __init__(self, path: str | Path, *, ttl: timedelta = timedelta(hours=24),
                 plan_ttl: timedelta = timedelta(hours=24)):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl
        self.plan_ttl = plan_ttl
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False,
                                   isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA secure_delete = ON")
        self._db.executescript(_SCHEMA)
        present = {row["name"] for row in self._db.execute("PRAGMA table_info(jobs)")}
        for column, kind in _ADDED_COLUMNS.items():
            if column not in present:
                self._db.execute(f"ALTER TABLE jobs ADD COLUMN {column} {kind}")

    # -- creating ------------------------------------------------------------

    def create(self, kind: str, request: dict, body_hash: str,
               idem_key: str | None, now: datetime) -> tuple[dict, bool]:
        """Queue a job; (job, created). An existing key returns its job instead."""
        with self._lock:
            if idem_key is not None:
                existing = self._row_by_key(idem_key)
                if existing is not None:
                    return self._view(existing), False
            job_id = "j_" + secrets.token_hex(8)
            self._db.execute(
                "INSERT INTO jobs (id, kind, state, idem_key, body_hash, request, "
                "created_at) VALUES (?, ?, 'queued', ?, ?, ?, ?)",
                (job_id, kind, idem_key, body_hash, json.dumps(request), _iso(now)),
            )
            return self._view(self._row(job_id)), True

    def by_key(self, idem_key: str) -> tuple[dict, str] | None:
        """(job, body hash) for an idempotency key, if it is still known."""
        with self._lock:
            row = self._row_by_key(idem_key)
            return (self._view(row), row["body_hash"]) if row else None

    # -- reading -------------------------------------------------------------

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            row = self._row(job_id)
            return self._view(row) if row else None

    def counts(self) -> dict:
        with self._lock:
            rows = self._db.execute(
                "SELECT state, COUNT(*) AS n FROM jobs WHERE state IN "
                "('queued', 'running') GROUP BY state").fetchall()
        found = {row["state"]: row["n"] for row in rows}
        return {"queued": found.get("queued", 0), "running": found.get("running", 0)}

    def state(self, job_id: str) -> str | None:
        with self._lock:
            row = self._db.execute("SELECT state FROM jobs WHERE id = ?",
                                   (job_id,)).fetchone()
        return row["state"] if row else None

    # -- the runner's side ---------------------------------------------------

    def claim_next(self, now: datetime) -> tuple[str, str, dict] | None:
        """Mark the oldest queued job running; (id, kind, request), or None."""
        with self._lock:
            row = self._db.execute(
                "SELECT id, kind, request FROM jobs WHERE state = 'queued' "
                "ORDER BY seq LIMIT 1").fetchone()
            if row is None:
                return None
            self._db.execute(
                "UPDATE jobs SET state = 'running', started_at = ? WHERE id = ?",
                (_iso(now), row["id"]))
            return row["id"], row["kind"], json.loads(row["request"])

    def set_progress(self, job_id: str, stage: str, message: str | None) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE jobs SET stage = ?, message = ? "
                "WHERE id = ? AND state = 'running'", (stage, message, job_id))

    def await_approval(self, job_id: str, plan: dict, now: datetime) -> None:
        """Park a running job with the plan it made, until it is approved."""
        with self._lock:
            self._db.execute(
                "UPDATE jobs SET state = 'awaiting_approval', plan = ?, "
                "plan_expires_at = ?, stage = NULL, message = NULL "
                "WHERE id = ? AND state = 'running'",
                (json.dumps({**plan, "approved": False}), _iso(now + self.plan_ttl),
                 job_id))

    def approve(self, job_id: str, queries: list[dict]) -> tuple[dict, bool] | None:
        """Queue a parked job again with ``queries``; (job, approved), or None.

        ``approved`` is False when the job was not awaiting approval -- it ran
        on, was cancelled, or its plan expired -- and the job is unchanged. The
        job keeps its ``seq``, so it goes ahead of everything queued after it.
        """
        with self._lock:
            row = self._row(job_id)
            if row is None:
                return None
            if row["state"] != "awaiting_approval":
                return self._view(row), False
            request = json.loads(row["request"])
            request["_approved_plan"] = queries
            self._db.execute(
                "UPDATE jobs SET state = 'queued', request = ?, plan = ?, "
                "plan_expires_at = NULL WHERE id = ?",
                (json.dumps(request),
                 json.dumps({"queries": queries, "approved": True}), job_id))
            return self._view(self._row(job_id)), True

    def finish(self, job_id: str, state: str, now: datetime, *,
               result: dict | None = None, error: dict | None = None) -> None:
        """Record how a running job ended, and erase its input.

        A job cancelled while it ran is already finished; its runner's late
        answer is dropped rather than written over the cancellation.
        """
        with self._lock:
            self._db.execute(
                "UPDATE jobs SET state = ?, finished_at = ?, expires_at = ?, "
                "result = ?, error = ?, request = NULL, stage = NULL, message = NULL "
                "WHERE id = ? AND state = 'running'",
                (state, _iso(now), _iso(now + self.ttl),
                 json.dumps(result) if result is not None else None,
                 json.dumps(error) if error is not None else None, job_id))

    def cancel(self, job_id: str, now: datetime) -> dict | None:
        """Cancel a job not yet finished. Finished jobs come back unchanged."""
        with self._lock:
            self._db.execute(
                "UPDATE jobs SET state = 'cancelled', finished_at = ?, expires_at = ?, "
                "request = NULL, stage = NULL, message = NULL, plan_expires_at = NULL "
                "WHERE id = ? AND state IN ('queued', 'running', 'awaiting_approval')",
                (_iso(now), _iso(now + self.ttl), job_id))
            row = self._row(job_id)
            return self._view(row) if row else None

    # -- housekeeping --------------------------------------------------------

    def sweep(self, now: datetime) -> int:
        """Fail plans nobody approved in time; delete expired results.

        Returns how many jobs were deleted.
        """
        error = {"code": "plan_expired", "retryable": False,
                 "message": "Nobody approved the search plan in time"}
        with self._lock:
            self._db.execute(
                "UPDATE jobs SET state = 'failed', finished_at = ?, expires_at = ?, "
                "error = ?, request = NULL, plan_expires_at = NULL "
                "WHERE state = 'awaiting_approval' AND plan_expires_at <= ?",
                (_iso(now), _iso(now + self.ttl), json.dumps(error), _iso(now)))
            return self._db.execute(
                "DELETE FROM jobs WHERE expires_at IS NOT NULL AND expires_at <= ?",
                (_iso(now),)).rowcount

    def recover(self, now: datetime) -> int:
        """At startup: whatever was running died with the last process."""
        error = {"code": "unavailable", "retryable": True,
                 "message": "The worker restarted during this job"}
        with self._lock:
            return self._db.execute(
                "UPDATE jobs SET state = 'failed', finished_at = ?, expires_at = ?, "
                "error = ?, request = NULL, stage = NULL, message = NULL "
                "WHERE state = 'running'",
                (_iso(now), _iso(now + self.ttl), json.dumps(error))).rowcount

    def raw_request(self, job_id: str):
        """The stored input, for tests that check it is gone once finished."""
        with self._lock:
            row = self._db.execute("SELECT request FROM jobs WHERE id = ?",
                                   (job_id,)).fetchone()
        return row["request"] if row else None

    # -- rows to API views ---------------------------------------------------

    def _row(self, job_id: str):
        return self._db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()

    def _row_by_key(self, idem_key: str):
        return self._db.execute("SELECT * FROM jobs WHERE idem_key = ?",
                                (idem_key,)).fetchone()

    def _view(self, row) -> dict:
        position = None
        if row["state"] == "queued":
            position = self._db.execute(
                "SELECT COUNT(*) FROM jobs WHERE state = 'queued' AND seq <= ?",
                (row["seq"],)).fetchone()[0]
        progress = None
        if row["state"] == "running" and row["stage"]:
            progress = {"stage": row["stage"]}
            if row["message"]:
                progress["message"] = row["message"]
        return {
            "id": row["id"],
            "kind": row["kind"],
            "state": row["state"],
            "position": position,
            "progress": progress,
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "expires_at": row["expires_at"],
            "result": json.loads(row["result"]) if row["result"] else None,
            "error": json.loads(row["error"]) if row["error"] else None,
            "plan": ({**json.loads(row["plan"]), "expires_at": row["plan_expires_at"]}
                     if row["plan"] else None),
        }
