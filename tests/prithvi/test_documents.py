"""The shared revision mechanics, exercised without a domain on top.

``VersionedDocuments`` lives in ``visualizer.documents`` beside the helper
Chronos uses, so these tests hand it error classes of their own making: if the
module ever needs to know what a map is, one of these will stop compiling.
"""

import mongomock
import pytest

from visualizer.documents import VersionedDocuments


class Missing(Exception):
    def __init__(self, message):
        super().__init__(message)


class Taken(Exception):
    def __init__(self, message):
        super().__init__(message)


class Stale(Exception):
    def __init__(self, message, evidence=None):
        super().__init__(message)
        self.evidence = evidence or {}


class Gone(Exception):
    def __init__(self, message):
        super().__init__(message)


THING = {"world": "earth", "map": "west"}
OTHER = {"world": "earth", "map": "east"}


@pytest.fixture
def documents():
    client = mongomock.MongoClient()
    return VersionedDocuments(
        client["_test"]["heads"],
        client["_test"]["revisions"],
        ("world", "map"),
        keep=3,
        conflict=Stale,
        gone=Gone,
    )


def create(documents, identity=THING, **body):
    return documents.create(identity, body or {"n": 1}, "mara", Taken)


# -- the ordinary lifecycle ---------------------------------------------------


def test_a_record_starts_at_revision_one(documents):
    created = create(documents, n=1)
    assert created["rev"] == 1
    assert created["world"] == "earth"
    assert documents.get(THING, Missing)["n"] == 1


def test_a_live_name_cannot_be_taken_twice(documents):
    create(documents)
    with pytest.raises(Taken):
        create(documents)


def test_each_write_moves_the_revision_on(documents):
    create(documents, n=1)
    assert documents.update(THING, {"n": 2}, 1, "devi", Missing)["rev"] == 2
    assert documents.get(THING, Missing)["n"] == 2


def test_a_stale_writer_loses(documents):
    create(documents, n=1)
    documents.update(THING, {"n": 2}, 1, "mara", Missing)
    with pytest.raises(Stale) as raised:
        documents.update(THING, {"n": 3}, 1, "devi", Missing)
    assert raised.value.evidence == {"expected": 1, "actual": 2}


# -- deleting, and taking the name back ---------------------------------------


def test_a_deleted_record_is_gone_from_reads_and_lists(documents):
    create(documents)
    documents.delete(THING, 1, "mara", Missing)

    with pytest.raises(Missing):
        documents.get(THING, Missing)
    assert documents.list({"world": "earth"}) == []
    assert documents.count({"world": "earth"}) == 0


def test_creating_a_deleted_name_again_revives_it(documents):
    """The plain lifecycle -- place it, remove it, place it again -- must work.

    Requiring an explicit restore instead would mean a client had to know that
    the thing it just deleted still exists in order to make it again.
    """
    create(documents, n=1)
    documents.delete(THING, 1, "mara", Missing)

    revived = create(documents, n=9)

    assert revived["rev"] == 3
    assert documents.get(THING, Missing)["n"] == 9
    assert [v["op"] for v in documents.history(THING, Missing)] == [
        "create",
        "delete",
        "create",
    ]


def test_history_survives_a_delete(documents):
    create(documents, n=1)
    documents.delete(THING, 1, "mara", Missing)
    assert [v["rev"] for v in documents.history(THING, Missing)] == [2, 1]


def test_a_delete_can_be_undone_by_restoring(documents):
    create(documents, n=1)
    documents.delete(THING, 1, "mara", Missing)

    restored = documents.restore(THING, 1, 2, "mara", Missing)

    assert restored["rev"] == 3
    assert restored["n"] == 1


def test_a_deletion_is_not_something_to_restore_to(documents):
    create(documents, n=1)
    documents.delete(THING, 1, "mara", Missing)
    with pytest.raises(Gone):
        documents.restore(THING, 2, 2, "mara", Missing)


# -- retention ----------------------------------------------------------------


def test_only_the_last_few_revisions_are_retained(documents):
    create(documents, n=1)
    for rev in range(1, 5):
        documents.update(THING, {"n": rev + 1}, rev, "mara", Missing)

    assert [v["rev"] for v in documents.history(THING, Missing)] == [5, 4, 3]
    with pytest.raises(Gone):
        documents.revision(THING, 1, Missing)


def test_a_retained_revision_can_still_be_read(documents):
    create(documents, n=1)
    documents.update(THING, {"n": 2}, 1, "devi", Missing)

    older = documents.revision(THING, 1, Missing)

    assert older["n"] == 1
    assert older["op"] == "create"
    assert older["author"] == "mara"
    assert older["world"] == "earth"


# -- listing ------------------------------------------------------------------


def test_listing_is_scoped_ordered_and_counted(documents):
    create(documents, identity=THING, n=1)
    create(documents, identity=OTHER, n=2)
    create(documents, identity={"world": "mars", "map": "west"}, n=3)

    rows = documents.list({"world": "earth"})

    assert [row["map"] for row in rows] == ["east", "west"]
    assert documents.count({"world": "earth"}) == 2


def test_an_absent_record_is_reported_as_missing(documents):
    for call in (
        lambda: documents.get(THING, Missing),
        lambda: documents.history(THING, Missing),
        lambda: documents.revision(THING, 1, Missing),
    ):
        with pytest.raises(Missing):
            call()
