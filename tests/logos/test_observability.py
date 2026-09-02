"""Manuscript storage appears on the shared per-writer accounting sweep."""

from visualizer.observability.usage import MongoDocumentSource

from .conftest import BOOK, SECTION, VOLUME, section_payload


def test_manuscript_bytes_are_charged_to_the_chronos_book(mongo_client, logos_store):
    logos_store.create_outline(BOOK, {"volumes": [VOLUME]}, "mara")
    logos_store.create_volume(
        BOOK, VOLUME, {"title": "One", "overview": "", "sections": [SECTION]}, "mara"
    )
    logos_store.create_section(BOOK, VOLUME, SECTION, section_payload(), "mara")

    records = list(MongoDocumentSource(mongo_client).documents())

    assert len(records) == 3
    assert {record.resource for record in records} == {("book", BOOK)}
    assert all(record.created_by == "mara" for record in records)
    assert all(record.total_bytes > 0 for record in records)


def test_a_revision_is_charged_to_whoever_wrote_it(mongo_client, logos_store):
    logos_store.create_section(BOOK, VOLUME, SECTION, section_payload(), "mara")
    logos_store.update_section(
        BOOK, VOLUME, SECTION, section_payload(title="Revised"), 1, "devi"
    )

    record = next(iter(MongoDocumentSource(mongo_client).documents()))

    assert record.resource == ("book", BOOK)
    assert sorted(author for author, _ in record.history) == ["devi", "mara"]
