"""Akasha articles linked to a section as a whole, rather than to its words."""

import pytest

from visualizer.akasha.store import DocumentStore
from visualizer.auth import ALL_PERMS
from visualizer.logos.errors import InvalidSection
from visualizer.logos.gateways import FakeChronosGateway, InProcessArticleGateway
from visualizer.logos.services import SectionService
from visualizer.logos.validation import MAX_SECTION_ARTICLES, validate_section_payload

from .conftest import BOOK, SECTION, VOLUME, WORLD, document, section_payload

SECTION_URL = f"/books/{BOOK}/volumes/{VOLUME}/sections/{SECTION}"
METADATA = SECTION_URL + "/metadata"
LINKED = SECTION_URL + "/ui/linked-articles"

LYRA = {"database": WORLD, "collection": "characters", "id": "lyra"}
GATE = {"database": WORLD, "collection": "places", "id": "gate"}
GONE = {"database": WORLD, "collection": "characters", "id": "nobody"}


def link(client, articles):
    rev = client.get(SECTION_URL).get_json()["rev"]
    return client.put(
        METADATA, json={"articles": articles}, headers={"If-Match": f'"{rev}"'}
    )


def test_linking_articles_is_a_metadata_edit_that_leaves_the_prose_alone(section):
    before = section.get(SECTION_URL).get_json()

    changed = link(section, [GATE, LYRA])

    assert changed.status_code == 200
    body = changed.get_json()
    assert body["articles"] == [GATE, LYRA]
    assert body["document"] == before["document"]
    assert body["event_ids"] == before["event_ids"]
    assert section.get(SECTION_URL).get_json()["articles"] == [GATE, LYRA]


def test_the_tools_list_them_in_order_titled_and_flag_one_that_is_gone(
    section, article_gateway
):
    article_gateway.add(WORLD, "places", "gate", {"title": "The Broken Gate"})
    link(section, [GATE, GONE, LYRA])

    body = section.get(LINKED).get_json()

    assert body["section"] == SECTION
    assert body["rev"] == section.get(SECTION_URL).get_json()["rev"]
    assert body["articles"] == [
        {**GATE, "title": "The Broken Gate", "missing": False},
        {**GONE, "title": None, "missing": True},
        {**LYRA, "title": "Lyra", "missing": False},
    ]


def test_a_section_with_none_linked_lists_none(section):
    assert section.get(LINKED).get_json()["articles"] == []


def test_a_linked_article_that_is_gone_is_a_missing_ref(section):
    link(section, [GONE, LYRA])

    assert section.get(SECTION_URL).get_json()["missing_refs"] == [GONE]
    report = section.get(f"/books/{BOOK}/report").get_json()
    assert report["sections_with_missing_refs"] == [
        {"volume": VOLUME, "section": SECTION, "missing_refs": [GONE]}
    ]


def test_saving_the_primary_draft_keeps_the_links(section):
    link(section, [LYRA])
    draft = section.get(SECTION_URL + "/drafts/draft-1").get_json()

    saved = section.put(
        SECTION_URL + "/drafts/draft-1",
        json={"name": draft["name"], "document": document("New words.")},
        headers={"If-Match": str(draft["rev"])},
    )

    assert saved.status_code == 200
    assert section.get(SECTION_URL).get_json()["articles"] == [LYRA]


def test_restoring_a_revision_restores_the_links_it_had(section):
    link(section, [LYRA])
    link(section, [])
    rev = section.get(SECTION_URL).get_json()["rev"]

    restored = section.post(
        SECTION_URL + f"/restore/{rev - 1}", headers={"If-Match": f'"{rev}"'}
    )

    assert restored.status_code == 200
    assert restored.get_json()["articles"] == [LYRA]


def test_a_revision_from_before_links_restores_with_none(section):
    link(section, [LYRA])
    rev = section.get(SECTION_URL).get_json()["rev"]

    restored = section.post(SECTION_URL + "/restore/1", headers={"If-Match": f'"{rev}"'})

    assert restored.status_code == 200
    assert restored.get_json()["articles"] == []


@pytest.mark.parametrize(
    "articles",
    [
        "lyra",
        [LYRA, dict(LYRA)],
        [{"database": WORLD, "collection": "characters"}],
        [{**LYRA, "title": "Lyra"}],
        [{**LYRA, "id": "  "}],
        [{**LYRA, "id": 7}],
    ],
)
def test_a_malformed_list_is_refused(section, articles):
    assert link(section, articles).status_code == 400
    assert section.get(SECTION_URL).get_json()["articles"] == []


def test_refs_are_trimmed_and_capped():
    payload = section_payload(events=())
    linked = validate_section_payload(
        SECTION, {**payload, "articles": [{**LYRA, "id": " lyra "}]}
    )
    assert linked.articles == [LYRA]

    many = [{**LYRA, "id": f"a{n}"} for n in range(MAX_SECTION_ARTICLES + 1)]
    with pytest.raises(InvalidSection):
        validate_section_payload(SECTION, {**payload, "articles": many})


def test_the_list_is_the_writers_alone(section, reader):
    assert reader.get(LINKED).status_code == 403


def test_the_list_needs_a_live_section(volume):
    assert volume.get(LINKED).status_code == 404


def test_titles_come_only_from_articles_the_writer_may_read(
    mongo_client, auth_store, logos_store
):
    """Through the real Akasha gateway: a grant on characters, none on places."""
    documents = DocumentStore(mongo_client)
    for collection, article, title in (
        ("characters", "lyra", "Lyra Venn"), ("places", "gate", "The Broken Gate"),
    ):
        documents.create_collection(WORLD, collection)
        documents.create(WORLD, collection, article, {"title": title})
    auth_store.grant_owner("mara", WORLD, "characters", None, list(ALL_PERMS))
    chronos = FakeChronosGateway()
    chronos.add_book(BOOK, "The Ember Pact", world=WORLD)
    sections = SectionService(logos_store, chronos, InProcessArticleGateway(documents))
    logos_store.create_volume(BOOK, VOLUME, {"title": "One", "sections": []}, "mara")
    sections.create(
        BOOK, VOLUME, SECTION,
        {**section_payload(events=()), "articles": [GATE, LYRA]}, "mara",
    )

    body = sections.linked_articles(BOOK, VOLUME, SECTION, auth_store.grants_for("mara"))

    assert body["articles"] == [
        # There, but not the writer's to read: no title, and not missing.
        {**GATE, "title": None, "missing": False},
        {**LYRA, "title": "Lyra Venn", "missing": False},
    ]
