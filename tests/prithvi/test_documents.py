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


def test_relocating_a_record_keeps_its_revision_chain(documents):
    create(documents, n=1)
    documents.update(THING, {"n": 2}, 1, "mara", Missing)

    moved = documents.relocate(THING, OTHER, 2, "devi", Missing, Taken)

    assert moved["map"] == "east"
    assert moved["n"] == 2
    assert [row["rev"] for row in documents.history(OTHER, Missing)] == [2, 1]
    assert documents.revision(OTHER, 1, Missing)["n"] == 1
    with pytest.raises(Missing):
        documents.get(THING, Missing)


def test_relocation_obeys_revision_and_destination_guards(documents):
    create(documents)
    with pytest.raises(Stale):
        documents.relocate(THING, OTHER, 99, "mara", Missing, Taken)

    create(documents, identity=OTHER)
    with pytest.raises(Taken):
        documents.relocate(THING, OTHER, 1, "mara", Missing, Taken)

    # A refused destination must not leave the source locked.
    assert documents.update(THING, {"n": 3}, 1, "mara", Missing)["n"] == 3


def test_relocating_does_not_spend_a_revision(documents):
    """A move re-addresses a record; it is not an edit and must not read as one."""
    create(documents, n=1)
    documents.update(THING, {"n": 2}, 1, "mara", Missing)
    before = [row["rev"] for row in documents.history(THING, Missing)]

    moved = documents.relocate(THING, OTHER, 2, "devi", Missing, Taken)

    assert moved["rev"] == 2
    assert [row["rev"] for row in documents.history(OTHER, Missing)] == before
    assert [row["op"] for row in documents.history(OTHER, Missing)] == [
        "update", "create",
    ]


def test_relocating_to_where_it_already_is_changes_nothing(documents):
    create(documents, n=1)

    same = documents.relocate(THING, THING, 1, "mara", Missing, Taken)

    assert (same["rev"], same["n"]) == (1, 1)


def test_a_second_destination_is_refused_while_a_move_is_outstanding(documents):
    """The lock names where the record is going, so a rival move cannot start."""
    create(documents, n=1)
    third = {"world": "earth", "map": "north"}
    documents._heads.update_one(
        {"_id": documents._key(THING)},
        {"$set": {"moving_to": documents._key(OTHER)}},
    )

    with pytest.raises(Stale, match="already being moved elsewhere"):
        documents.relocate(THING, third, 1, "mara", Missing, Taken)

    # The original destination still completes: the lock is a claim, not a jam.
    assert documents.relocate(THING, OTHER, 1, "mara", Missing, Taken)["n"] == 1


def test_losing_the_lock_race_refuses_rather_than_half_moving(documents, monkeypatch):
    create(documents, n=1)
    heads = documents._heads

    class LostRace:
        matched_count = 0

    monkeypatch.setattr(heads, "update_one", lambda *a, **k: LostRace())

    with pytest.raises(Stale, match="Modified concurrently"):
        documents.relocate(THING, OTHER, 1, "mara", Missing, Taken)


def test_a_destination_inserted_mid_move_is_adopted_not_duplicated(
    documents, monkeypatch
):
    """The copy loses an insert race, so it re-reads rather than reporting a clash.

    Reachable only when two callers relocate the same record at once. The
    survivor is whichever head landed; both callers must agree on it.
    """
    create(documents, n=1)
    real_insert = documents._heads.insert_one
    landed = {}

    def insert_then_lose(document):
        if document["_id"] == documents._key(OTHER) and not landed:
            landed["yes"] = True
            real_insert(document)
        return real_insert(document)

    monkeypatch.setattr(documents._heads, "insert_one", insert_then_lose)

    moved = documents.relocate(THING, OTHER, 1, "mara", Missing, Taken)

    assert (moved["map"], moved["n"]) == ("east", 1)
    with pytest.raises(Missing):
        documents.get(THING, Missing)


def test_relocating_something_that_was_never_there_is_not_found(documents):
    with pytest.raises(Missing):
        documents.relocate(THING, OTHER, 1, "mara", Missing, Taken)


def test_relocating_a_deleted_record_is_not_found(documents):
    create(documents, n=1)
    documents.delete(THING, 1, "mara", Missing)

    with pytest.raises(Missing):
        documents.relocate(THING, OTHER, 2, "mara", Missing, Taken)


def test_a_finished_move_replayed_returns_the_record_at_its_destination(documents):
    """The retry that closes an interrupted move must not report it as missing."""
    create(documents, n=1)
    documents.relocate(THING, OTHER, 1, "mara", Missing, Taken)

    again = documents.relocate(THING, OTHER, 1, "mara", Missing, Taken)

    assert (again["map"], again["n"]) == ("east", 1)


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
