"""Pure, DB-free helpers for embedded version history.

Each document carries the last *N* snapshots in an internal ``_history`` array
(see the design doc): a single atomic ``find_one_and_update`` in the store
appends a snapshot and prunes with ``$slice`` on every write, so history and the
document stay consistent even on a standalone MongoDB with no transactions.

This module holds the *pure* parts -- building a snapshot record and pruning a
list -- so they can be unit tested without a database. Timestamps are supplied
by the caller (from an injected clock), never read from the wall clock here.
"""

CREATE = "create"
UPDATE = "update"
DELETE = "delete"

# Public metadata fields of a snapshot (everything except the body).
_META_FIELDS = ("rev", "op", "author", "timestamp")


def make_snapshot(
    rev: int,
    op: str,
    author: str | None,
    timestamp: str,
    document: dict | None,
) -> dict:
    """Build one immutable history record.

    ``document`` is the full body at ``rev`` (a tombstone ``delete`` stores the
    last body so the deletion is diffable). ``timestamp`` is an ISO-8601 string
    provided by the caller.
    """
    return {
        "rev": rev,
        "op": op,
        "author": author,
        "timestamp": timestamp,
        "document": dict(document) if document is not None else None,
    }


def prune(history: list[dict], keep: int) -> list[dict]:
    """Return at most the last ``keep`` snapshots (oldest dropped first)."""
    if keep <= 0:
        return []
    return list(history[-keep:])


def snapshot_meta(snapshot: dict) -> dict:
    """The metadata view of a snapshot (no document body)."""
    return {field: snapshot.get(field) for field in _META_FIELDS}


def history_meta(history: list[dict]) -> list[dict]:
    """Metadata for every snapshot, newest first."""
    return [snapshot_meta(s) for s in reversed(history or [])]


def find_snapshot(history: list[dict], rev: int) -> dict | None:
    """Return the snapshot at ``rev`` from ``history``, or ``None``."""
    for snapshot in history or ():
        if snapshot.get("rev") == rev:
            return snapshot
    return None
