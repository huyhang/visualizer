"""Persistence mechanics that belong to Logos rather than to the shared engine."""

import pytest

from visualizer.logos.errors import RevisionConflict
from visualizer.logos.store import LogosStore

from .conftest import BOOK, SECTION, VOLUME, document, section_payload


def _seed(store):
    store.create_outline(BOOK, {"volumes": [VOLUME]}, "mara")
    store.create_volume(
        BOOK, VOLUME, {"title": "One", "overview": "", "sections": [SECTION]}, "mara"
    )
    return store.create_section(BOOK, VOLUME, SECTION, section_payload(), "mara")


def test_the_three_records_round_trip(logos_store):
    section = _seed(logos_store)

    assert section["rev"] == 1
    assert logos_store.find_outline(BOOK)["volumes"] == [VOLUME]
    assert logos_store.get_volume(BOOK, VOLUME)["sections"] == [SECTION]
    assert logos_store.get_section(BOOK, VOLUME, SECTION)["kind"] == "chapter"


def test_absence_is_answered_with_none_rather_than_an_exception(logos_store):
    assert logos_store.find_outline(BOOK) is None
    assert logos_store.find_volume(BOOK, VOLUME) is None
    assert logos_store.find_section(BOOK, VOLUME, SECTION) is None


def test_section_history_is_bounded_and_restorable(mongo_client):
    store = LogosStore(mongo_client, section_revisions_keep=2)
    store.create_section(BOOK, VOLUME, SECTION, section_payload(), "mara")
    second = section_payload(doc=document("Second draft."))
    store.update_section(BOOK, VOLUME, SECTION, second, 1, "mara")
    third = section_payload(doc=document("Third draft."))
    store.update_section(BOOK, VOLUME, SECTION, third, 2, "mara")

    retained = [row["rev"] for row in store.section_history(BOOK, VOLUME, SECTION)]
    assert retained == [3, 2]

    restored = store.restore_section(BOOK, VOLUME, SECTION, 2, 3, "mara")
    assert restored["document"] == second["document"]


def test_ordering_records_keep_only_their_current_revision(logos_store):
    """The outline holds an arrangement, not prose; its history is not a thing
    anyone reads back, and paying storage for it would be paying for nothing."""
    logos_store.create_outline(BOOK, {"volumes": ["a"]}, "mara")
    logos_store.update_outline(BOOK, {"volumes": ["a", "b"]}, 1, "mara")

    assert logos_store.find_outline(BOOK)["volumes"] == ["a", "b"]
    assert logos_store.find_outline(BOOK)["rev"] == 2


def test_the_shelf_wide_reads_answer_in_one_query_each(logos_store):
    _seed(logos_store)
    logos_store.create_outline("other", {"volumes": []}, "mara")

    assert sorted(logos_store.outlines_by_book()) == [BOOK, "other"]
    assert list(logos_store.volumes_by_book()) == [BOOK]
    assert len(logos_store.volumes_by_book()[BOOK]) == 1


def test_cross_service_questions_see_only_live_prose(logos_store):
    created = _seed(logos_store)

    assert logos_store.has_content(BOOK)
    assert [
        row["section"] for row in logos_store.sections_referencing(BOOK, "opening")
    ] == [SECTION]
    assert logos_store.sections_referencing(BOOK, "climax") == []

    logos_store.delete_section(BOOK, VOLUME, SECTION, created["rev"], "mara")

    assert logos_store.sections_referencing(BOOK, "opening") == []
    # The outline and volume records survive a section delete, so the book is
    # still holding a manuscript.
    assert logos_store.has_content(BOOK)


def test_purging_a_book_removes_its_retained_history_too(logos_store, mongo_client):
    _seed(logos_store)
    revisions = mongo_client["_logos"]["section_revisions"]
    assert revisions.count_documents({}) == 1

    logos_store.purge_book(BOOK)

    assert not logos_store.has_content(BOOK)
    assert revisions.count_documents({}) == 0
    assert mongo_client["_logos"]["volume_revisions"].count_documents({}) == 0
    assert mongo_client["_logos"]["outline_revisions"].count_documents({}) == 0


def test_reading_position_updates_are_compare_and_swap(logos_store):
    position = {"last": None, "furthest": None}
    logos_store.set_reading_position("mara", BOOK, position, expected_rev=0)

    with pytest.raises(RevisionConflict):
        logos_store.set_reading_position("mara", BOOK, position, expected_rev=0)


def test_an_account_and_a_book_cannot_be_confused_for_another_pair(logos_store):
    """Two fields, not one joined key.

    Nothing constrains the punctuation in a username or a Chronos book id, so a
    key built by concatenating them lets one pair spell another: 'alice' reading
    'x::y' and 'alice::x' reading 'y' are different readers of different books.
    """
    mark = {"volume": "v", "section": "s", "block": "p1", "offset": 0, "progress": 0.9}
    logos_store.set_reading_position(
        "alice", "x::y", {"last": mark, "furthest": None}, expected_rev=0
    )

    assert logos_store.get_reading_position("alice::x", "y") is None
    assert logos_store.get_reading_position("alice", "x::y")["last"] == mark


def test_drafts_can_be_listed_for_a_series_or_one_of_its_volumes(logos_store):
    """The series-wide read is what keeps a whole-series review to a handful of
    queries; the volume filter is what keeps a volume-scoped one from paying
    for the other nine."""
    _seed(logos_store)
    logos_store.create_volume(
        BOOK, "two", {"title": "Two", "overview": "", "sections": ["hall"]}, "mara"
    )
    logos_store.create_section(BOOK, "two", "hall", section_payload(), "mara")
    # A store-level section carries no draft record; the service layer makes
    # those, so this makes them by hand.
    logos_store.create_draft(
        BOOK, VOLUME, SECTION, "draft-1",
        {"name": "Draft 1", "document": document("The gate.")}, "mara",
    )
    logos_store.create_draft(
        BOOK, "two", "hall", "draft-1",
        {"name": "Draft 1", "document": document("The hall.")}, "mara",
    )

    everywhere = logos_store.list_book_drafts(BOOK)
    here = logos_store.list_book_drafts(BOOK, VOLUME)

    assert {row["volume"] for row in everywhere} == {VOLUME, "two"}
    assert {row["volume"] for row in here} == {VOLUME}
    assert logos_store.list_book_drafts(BOOK, "never-written") == []


_LEGACY_BOOKMARK_INDEX = "username_1_book_1_kind_1_volume_1_section_1_block_1"


def test_the_pre_draft_bookmark_index_is_dropped_on_the_way_past(mongo_client):
    """A bookmark is unique per *draft* now, so the old index is not merely
    redundant -- left in place it keeps enforcing uniqueness without `draft`
    and refuses the second bookmark on the same paragraph of an alternate.
    Deployments keep their database across releases, so the only place this
    ever runs is on a collection that already has the old index.
    """
    items = mongo_client["_logos"]["reader_items"]
    items.create_index(
        [("username", 1), ("book", 1), ("kind", 1), ("volume", 1),
         ("section", 1), ("block", 1)],
        unique=True,
        partialFilterExpression={"kind": "bookmark"},
    )
    assert _LEGACY_BOOKMARK_INDEX in items.index_information()

    store = LogosStore(mongo_client, section_revisions_keep=20)

    assert _LEGACY_BOOKMARK_INDEX not in items.index_information()
    assert "reader_bookmark_target" in items.index_information()
    anchor = {"kind": "bookmark", "scope": "paragraph", "volume": VOLUME,
              "section": SECTION, "block": "p1", "text": ""}
    primary = store.create_reader_item("mara", BOOK, dict(anchor))
    alternate = store.create_reader_item(
        "mara", BOOK, {**anchor, "draft": "draft-2"}
    )
    assert primary["id"] != alternate["id"]
