"""Tests for storage attribution -- who is charged for which stored bytes.

The rule under test: the owner is charged for the current document, each author
for the version snapshots they wrote. The property that makes the numbers
trustworthy is that they reconcile -- owns plus authored must equal exactly what
is on disk, with nothing double-counted and nothing lost.
"""

import mongomock

from visualizer.akasha.store import DocumentStore
from visualizer.auth import AuthStore
from visualizer.chronos.store import CalendarStore, StoryStore
from visualizer.observability.usage import (
    UNATTRIBUTED,
    MongoDocumentSource,
    StoredDocument,
    UsageScan,
    attribute,
    owner_index,
)
from visualizer.prithvi.store import PrithviStore


def _grant(username, database, collection, doc_id, perms, granted_by, kind="database"):
    return {
        "username": username,
        "resource_type": kind,
        "database": database,
        "collection": collection,
        "doc_id": doc_id,
        "perms": perms,
        "granted_by": granted_by,
    }


# -- the ownership rule ------------------------------------------------------


def test_ownership_requires_delete():
    grants = [_grant("devi", "world", "people", "mara", ["read", "write"], "mara")]
    assert owner_index(grants) == {}


def test_a_self_granted_delete_wins_over_one_someone_else_gave():
    grants = [
        _grant("devi", "world", "people", "mara", ["delete"], "mara"),
        _grant("mara", "world", "people", "mara", ["delete"], "mara"),
    ]
    assert owner_index(grants)[("article", "world", "people", "mara")] == "mara"


def test_ties_break_deterministically():
    """Two equal claims must resolve the same way on every run."""
    grants = [
        _grant("zoe", "world", "people", "x", ["delete"], "admin"),
        _grant("ada", "world", "people", "x", ["delete"], "admin"),
    ]
    reversed_order = list(reversed(grants))
    assert owner_index(grants) == owner_index(reversed_order)
    assert owner_index(grants)[("article", "world", "people", "x")] == "ada"


def test_book_grants_are_namespaced_away_from_article_grants():
    grants = [
        _grant("mara", "novel", None, None, ["delete"], "mara", kind="book"),
        _grant("devi", "novel", "people", "novel", ["delete"], "devi"),
    ]
    index = owner_index(grants)
    assert index[("book", "novel")] == "mara"
    assert index[("article", "novel", "people", "novel")] == "devi"


def test_partial_scopes_confer_no_ownership():
    """A collection-wide grant does not make someone the owner of each document."""
    assert owner_index([_grant("mara", "world", "people", None, ["delete"], "mara")]) == {}


# -- the charging rule -------------------------------------------------------


def test_owner_takes_the_current_body_and_authors_take_their_snapshots():
    document = StoredDocument(
        resource=("article", "world", "people", "mara"),
        total_bytes=400,
        history=(("mara", 100), ("devi", 200)),
    )
    rows = attribute([document], {("article", "world", "people", "mara"): "mara"})

    by_writer = {row.writer: row for row in rows}
    assert by_writer["mara"].owns == 100  # 400 total less 300 of history
    assert by_writer["mara"].authored == 100
    assert by_writer["devi"].owns == 0
    assert by_writer["devi"].authored == 200


def test_attribution_reconciles_to_what_is_on_disk():
    documents = [
        StoredDocument(("article", "w", "c", "a"), 400, (("mara", 100), ("devi", 200))),
        StoredDocument(("article", "w", "c", "b"), 250, (("devi", 50),)),
        StoredDocument(("book", "novel"), 90, (), created_by="jun"),
    ]
    rows = attribute(documents, {("article", "w", "c", "a"): "mara"})

    on_disk = sum(document.total_bytes for document in documents)
    assert sum(row.owns + row.authored for row in rows) == on_disk


def test_history_larger_than_the_document_never_charges_negative_bytes():
    """Defensive: the history array's own overhead is charged to nobody."""
    document = StoredDocument(("article", "w", "c", "a"), 100, (("devi", 400),))
    rows = attribute([document], {})

    assert all(row.owns >= 0 for row in rows)
    assert {row.writer: row.owns for row in rows}["devi"] == 0


def test_an_ungranted_document_falls_back_to_its_creator():
    document = StoredDocument(("book", "novel"), 90, (), created_by="jun")
    assert attribute([document], {})[0].writer == "jun"


def test_an_uncreated_document_falls_back_to_its_first_author():
    document = StoredDocument(("article", "w", "c", "a"), 300, (("mara", 100),))
    rows = {row.writer: row for row in attribute([document], {})}
    assert rows["mara"].owns == 200


def test_a_document_with_no_trace_of_authorship_is_unattributed():
    rows = attribute([StoredDocument(("article", "w", "c", "a"), 300)], {})
    assert [row.writer for row in rows] == [UNATTRIBUTED]


def test_snapshots_with_no_author_are_unattributed_not_dropped():
    document = StoredDocument(("article", "w", "c", "a"), 300, ((None, 100),), created_by="mara")
    rows = {row.writer: row for row in attribute([document], {})}
    assert rows[UNATTRIBUTED].authored == 100
    assert sum(row.owns + row.authored for row in rows.values()) == 300


def test_rows_are_ordered_by_total_descending():
    documents = [
        StoredDocument(("book", "small"), 10, (), created_by="ada"),
        StoredDocument(("book", "big"), 900, (), created_by="zoe"),
    ]
    assert [row.writer for row in attribute(documents, {})] == ["zoe", "ada"]


def test_no_documents_produces_no_rows():
    assert attribute([], {}) == []


# -- the sweep over real storage ---------------------------------------------


def _populated_client():
    client = mongomock.MongoClient()
    auth = AuthStore(client)
    auth.create_user("mara", "hash")
    auth.create_user("devi", "hash")
    documents = DocumentStore(client)
    documents.create_collection("world", "people")
    documents.create("world", "people", "mara", {"name": "Mara"}, author="mara")
    documents.update("world", "people", "mara", {"name": "Mara II"}, author="devi")
    auth.grant_owner("mara", "world", "people", "mara", ["read", "write", "delete"])
    stories = StoryStore(client)
    stories.create_book("novel", {"title": "Novel"}, author="mara")
    stories.create_event("novel", "opening", {"title": "Opening"}, author="devi")
    auth.grant_owner("mara", "novel", None, None, ["read", "write", "delete"], resource_type="book")
    CalendarStore(client).create("mara", "solar", {"name": "Solar"})
    maps = PrithviStore(client)
    body = {"svg": "<svg/>", "view_box": [0.0, 0.0, 1.0, 1.0], "sanitization": {}}
    maps.create_map("world", "west", body, "mara")
    maps.update_map("world", "west", body, 1, "devi")
    maps.create_pin("world", "west", "people", "mara", {"x": 0.5, "y": 0.5}, "mara")
    return client, auth


def test_the_sweep_skips_reserved_databases():
    client, _ = _populated_client()
    resources = {doc.resource[0] for doc in MongoDocumentSource(client).documents()}
    assert resources == {"article", "book", "calendar", "map", "pin"}


def test_the_sweep_counts_a_map_once_and_charges_its_revisions_to_their_writers():
    """Prithvi keeps revisions in their own records; the sweep rejoins them.

    Without that, a map would be counted once per revision, and a drawing's
    bytes would land on whoever happened to create the map rather than on
    whoever redrew it.
    """
    client, _ = _populated_client()
    maps = [
        doc for doc in MongoDocumentSource(client).documents() if doc.resource[0] == "map"
    ]

    assert len(maps) == 1
    assert maps[0].resource == ("map", "world", "west")
    assert [author for author, _ in maps[0].history] == ["mara", "devi"]
    assert maps[0].total_bytes > sum(size for _, size in maps[0].history)


def test_the_sweep_measures_articles_and_their_history():
    client, _ = _populated_client()
    article = next(
        doc for doc in MongoDocumentSource(client).documents() if doc.resource[0] == "article"
    )
    assert article.total_bytes > 0
    assert [author for author, _ in article.history] == ["mara", "devi"]
    assert all(size > 0 for _, size in article.history)


def test_a_scan_writes_one_row_per_writer_and_supersedes_itself():
    from datetime import UTC, datetime

    from visualizer.observability.store import MetricsStore

    client, auth = _populated_client()
    store = MetricsStore(client)
    scan = UsageScan(MongoDocumentSource(client), auth.all_grants, store)
    day = datetime(2026, 8, 19, 3, tzinfo=UTC)

    first = scan.run(day)
    scan.run(day)
    rows = store.storage_days()

    assert {row.writer for row in first} == {row["writer"] for row in rows}
    assert len(rows) == len(first), "re-running a day must overwrite, not accumulate"


def test_a_collaborator_is_charged_for_their_edits_not_the_whole_article():
    client, auth = _populated_client()
    rows = {
        row.writer: row
        for row in attribute(
            MongoDocumentSource(client).documents(), owner_index(auth.all_grants())
        )
    }
    # mara owns the article, the book and the calendar; devi only ever edited.
    assert rows["mara"].owns > 0
    assert rows["devi"].owns == 0
    assert rows["devi"].authored > 0
