"""Unit tests for the pure history helpers."""

from visualizer.akasha.history import (
    CREATE,
    UPDATE,
    find_snapshot,
    history_meta,
    make_snapshot,
    prune,
    snapshot_meta,
)


def _snap(rev, op=UPDATE):
    return make_snapshot(rev, op, "huy", f"2026-01-0{rev}T00:00:00", {"n": rev})


def test_make_snapshot_shape():
    snap = make_snapshot(1, CREATE, "huy", "2026-01-01T00:00:00", {"a": 1})
    assert snap == {
        "rev": 1,
        "op": CREATE,
        "author": "huy",
        "timestamp": "2026-01-01T00:00:00",
        "document": {"a": 1},
    }


def test_make_snapshot_copies_document():
    body = {"a": 1}
    snap = make_snapshot(1, CREATE, "huy", "t", body)
    body["a"] = 2
    assert snap["document"] == {"a": 1}


def test_make_snapshot_tombstone_keeps_none():
    assert make_snapshot(2, "delete", "huy", "t", None)["document"] is None


def test_prune_keeps_last_n():
    history = [_snap(i) for i in range(1, 6)]
    kept = prune(history, 3)
    assert [s["rev"] for s in kept] == [3, 4, 5]


def test_prune_shorter_than_cap_is_unchanged():
    history = [_snap(1), _snap(2)]
    assert prune(history, 5) == history


def test_snapshot_meta_drops_body():
    meta = snapshot_meta(_snap(1))
    assert "document" not in meta
    assert set(meta) == {"rev", "op", "author", "timestamp"}


def test_history_meta_is_newest_first_without_bodies():
    history = [_snap(1), _snap(2), _snap(3)]
    meta = history_meta(history)
    assert [m["rev"] for m in meta] == [3, 2, 1]
    assert all("document" not in m for m in meta)


def test_find_snapshot():
    history = [_snap(1), _snap(2)]
    assert find_snapshot(history, 2)["rev"] == 2
    assert find_snapshot(history, 9) is None
