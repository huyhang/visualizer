"""Persistence mechanics that belong to Logos rather than to the shared engine."""

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
