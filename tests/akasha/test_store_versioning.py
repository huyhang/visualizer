"""DocumentStore tests for optimistic concurrency and embedded versioning."""

from datetime import datetime, timezone

import mongomock
import pytest

from visualizer.akasha.errors import DocumentNotFound, RevisionConflict
from visualizer.akasha.store import DocumentStore

DB, COL = "earth", "lotr"
FIXED = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def store():
    s = DocumentStore(mongomock.MongoClient(), clock=lambda: FIXED, versions_keep=3)
    s.create_collection(DB, COL)
    return s


def test_create_sets_rev_and_records_create_snapshot(store):
    result = store.create(DB, COL, "a", {"name": "Aragorn"}, author="huy")
    assert result["rev"] == 1
    history = store.history(DB, COL, "a")
    assert len(history) == 1
    assert history[0]["op"] == "create"
    assert history[0]["author"] == "huy"
    assert history[0]["timestamp"] == FIXED.isoformat()
    assert history[0]["document"] == {"name": "Aragorn"}


def test_update_bumps_rev_and_appends_history(store):
    store.create(DB, COL, "a", {"name": "Aragorn"})
    result = store.update(DB, COL, "a", {"name": "Elessar"}, expected_rev=1, author="huy")
    assert result["rev"] == 2
    revs = [s["rev"] for s in store.history(DB, COL, "a")]
    assert revs == [1, 2]


def test_update_with_stale_rev_conflicts(store):
    store.create(DB, COL, "a", {"name": "Aragorn"})
    store.update(DB, COL, "a", {"name": "Elessar"}, expected_rev=1)
    with pytest.raises(RevisionConflict):
        store.update(DB, COL, "a", {"name": "Strider"}, expected_rev=1)


def test_occ_interleave_second_writer_loses(store):
    store.create(DB, COL, "a", {"v": 0})
    # Two clients both read rev 1.
    read_a = store.get(DB, COL, "a")["rev"]
    read_b = store.get(DB, COL, "a")["rev"]
    # A writes first, succeeds.
    store.update(DB, COL, "a", {"v": 1}, expected_rev=read_a)
    # B writes against the now-stale rev, is rejected.
    with pytest.raises(RevisionConflict):
        store.update(DB, COL, "a", {"v": 2}, expected_rev=read_b)


def test_unconditional_update_still_versions(store):
    store.create(DB, COL, "a", {"v": 0})
    result = store.update(DB, COL, "a", {"v": 1})  # no expected_rev
    assert result["rev"] == 2


def test_keep_last_n_prunes_oldest(store):
    store.create(DB, COL, "a", {"v": 0})
    for i in range(1, 6):
        store.update(DB, COL, "a", {"v": i})
    revs = [s["rev"] for s in store.history(DB, COL, "a")]
    assert revs == [4, 5, 6]  # versions_keep=3


def test_soft_delete_hides_document_but_keeps_history(store):
    store.create(DB, COL, "a", {"name": "Aragorn"})
    store.delete(DB, COL, "a", expected_rev=1, author="huy")
    with pytest.raises(DocumentNotFound):
        store.get(DB, COL, "a")
    history = store.history(DB, COL, "a")
    assert history[-1]["op"] == "delete"
    assert history[-1]["document"] is None


def test_delete_with_stale_rev_conflicts(store):
    store.create(DB, COL, "a", {"name": "Aragorn"})
    store.update(DB, COL, "a", {"name": "Elessar"}, expected_rev=1)
    with pytest.raises(RevisionConflict):
        store.delete(DB, COL, "a", expected_rev=1)


def test_create_after_delete_revives(store):
    store.create(DB, COL, "a", {"name": "Aragorn"})
    store.delete(DB, COL, "a", expected_rev=1)
    revived = store.create(DB, COL, "a", {"name": "Strider"})
    assert revived["rev"] == 3  # rev1 create, rev2 delete, rev3 revive
    assert store.get(DB, COL, "a")["document"] == {"name": "Strider"}


def test_list_documents_excludes_deleted(store):
    store.create(DB, COL, "a", {"n": 1})
    store.create(DB, COL, "b", {"n": 2})
    store.delete(DB, COL, "a", expected_rev=1)
    ids = {d["id"] for d in store.list_documents(DB, COL)}
    assert ids == {"b"}


def test_list_documents_pagination(store):
    for name in ["a", "b", "c", "d"]:
        store.create(DB, COL, name, {"n": name})
    page = store.list_documents(DB, COL, limit=2)
    assert [d["id"] for d in page] == ["a", "b"]
    page2 = store.list_documents(DB, COL, limit=2, after="b")
    assert [d["id"] for d in page2] == ["c", "d"]


def test_internal_fields_never_leak(store):
    store.create(DB, COL, "a", {"_id": "x", "_rev": 99, "_history": [], "name": "A"})
    got = store.get(DB, COL, "a")
    assert got["document"] == {"name": "A"}
    assert got["id"] == "a" and got["rev"] == 1


def test_list_databases_hides_reserved(store):
    # The auth store shares the client and lives in a reserved `_auth` db.
    store._client["_auth"]["users"].insert_one({"_id": "huy"})
    assert "_auth" not in store.list_databases()
    assert DB in store.list_databases()
