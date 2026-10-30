"""The scene cards above the writing page, and choosing a section's scenes."""

from visualizer.akasha.store import DocumentStore
from visualizer.auth import ALL_PERMS
from visualizer.chronos.models import Book, EntityRef, Event
from visualizer.chronos.store import StoryStore
from visualizer.logos.gateways import InProcessArticleGateway, InProcessChronosGateway
from visualizer.logos.services import SectionService, VolumeService

from .conftest import BOOK, SECTION, VOLUME, WORLD, section_payload

CARDS = f"/books/{BOOK}/volumes/{VOLUME}/ui/scene-cards"
CHOICES = f"/books/{BOOK}/ui/scene-choices"
METADATA = f"/books/{BOOK}/volumes/{VOLUME}/sections/{SECTION}/metadata"

GATE = {"database": WORLD, "collection": "places", "id": "gate"}
LYRA = {"database": WORLD, "collection": "characters", "id": "lyra"}
GONE = {"database": WORLD, "collection": "characters", "id": "nobody"}


def test_the_cards_carry_each_scene_by_section_with_its_place_and_cast(
    volume, chronos_gateway, article_gateway
):
    article_gateway.add(WORLD, "places", "gate", {"title": "The Broken Gate"})
    chronos_gateway.add_event(
        BOOK, "opening", "The gate opens", "Day 5",
        description="Lyra reaches the gate.", location=GATE, characters=[LYRA, GONE],
    )
    for section, events in (("first", ["opening"]), ("second", []),
                            ("third", ["climax", "opening"])):
        assert volume.post(
            f"/books/{BOOK}/volumes/{VOLUME}/sections/{section}",
            json=section_payload(title=section, events=events),
        ).status_code == 201

    body = volume.get(CARDS).get_json()

    assert [row["section"] for row in body["sections"]] == ["first", "second", "third"]
    assert [
        [scene["id"] for scene in row["scenes"]] for row in body["sections"]
    ] == [["opening"], [], ["climax", "opening"]]
    assert body["sections"][0]["scenes"][0] == {
        "id": "opening",
        "title": "The gate opens",
        "when": "Day 5",
        "missing": False,
        "description": "Lyra reaches the gate.",
        "place": {**GATE, "title": "The Broken Gate"},
        "cast": [{**LYRA, "title": "Lyra"}],
        # An article Akasha no longer has is counted, not named.
        "unseen": 1,
    }


def test_a_scene_chronos_no_longer_has_is_flagged_with_nothing_to_show(
    volume, chronos_gateway
):
    assert volume.post(
        f"/books/{BOOK}/volumes/{VOLUME}/sections/{SECTION}",
        json=section_payload(),
    ).status_code == 201
    chronos_gateway._events[BOOK].pop("opening")

    (scene,) = volume.get(CARDS).get_json()["sections"][0]["scenes"]

    assert scene["missing"] is True
    assert (scene["place"], scene["cast"], scene["unseen"]) == (None, [], 0)


def test_the_choices_are_every_scene_in_the_book(volume, chronos_gateway):
    chronos_gateway.add_event(BOOK, "aftermath", "After the fire", "Day 9")

    body = volume.get(CHOICES).get_json()

    assert [scene["id"] for scene in body["scenes"]] == [
        "opening", "climax", "aftermath",
    ]
    assert body["scenes"][2] == {
        "id": "aftermath", "title": "After the fire", "when": "Day 9", "missing": False,
    }


def test_choosing_a_sections_scenes_is_a_metadata_edit(section):
    rev = section.get(
        f"/books/{BOOK}/volumes/{VOLUME}/sections/{SECTION}"
    ).get_json()["rev"]

    changed = section.put(
        METADATA, json={"event_ids": ["climax", "opening"]},
        headers={"If-Match": f'"{rev}"'},
    )

    assert changed.status_code == 200
    assert changed.get_json()["event_ids"] == ["climax", "opening"]
    assert [
        scene["id"] for scene in section.get(CARDS).get_json()["sections"][0]["scenes"]
    ] == ["climax", "opening"]


def test_the_cards_and_choices_are_the_writers_alone(section, reader):
    # A reader is offered titles and timeframes in Full View, not who and where.
    assert reader.get(CARDS).status_code == 403
    assert reader.get(CHOICES).status_code == 403


def test_the_cards_need_a_live_volume(client):
    assert client.get(CARDS).status_code == 404
    assert client.get(f"/books/{BOOK}/volumes/nope/ui/scene-cards").status_code == 404


# -- through the real stores ------------------------------------------------------


def _event(event_id, start, title, location=("places", "gate"), characters=()):
    return Event(
        event_id,
        EntityRef(WORLD, *location),
        start,
        None if start is None else start + 1,
        title=title,
        characters=[EntityRef(WORLD, "characters", c) for c in characters],
    )


def test_the_real_gateway_lists_scenes_in_story_order(mongo_client):
    stories = StoryStore(mongo_client)
    stories.create_book(BOOK, Book(BOOK, title="The Ember Pact").to_storage(), "mara")
    for event in (
        _event("late", 9, "Late"),
        _event("drifting", None, "drifting"),
        _event("early", 2, "Early"),
        _event("adrift", None, "Adrift"),
    ):
        stories.create_event(BOOK, event.id, event.to_storage(), "mara")
    gateway = InProcessChronosGateway(stories)

    assert [scene["id"] for scene in gateway.scene_choices(BOOK)] == [
        "early", "late", "adrift", "drifting",
    ]
    assert gateway.scene_choices("no-such-book") == []
    (detail, gone) = gateway.scene_details(BOOK, ["early", "nope"])
    assert detail["location"] == GATE
    assert detail["description"] == ""
    assert gone == {"id": "nope", "title": "nope", "when": "", "missing": True,
                    "description": "", "location": None, "characters": []}


def test_names_come_only_from_articles_the_writer_may_read(
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
    stories = StoryStore(mongo_client)
    stories.create_book(BOOK, Book(BOOK, title="The Ember Pact").to_storage(), "mara")
    opening = _event("opening", 0, "Opening", characters=["lyra"])
    stories.create_event(BOOK, opening.id, opening.to_storage(), "mara")

    chronos = InProcessChronosGateway(stories)
    articles = InProcessArticleGateway(documents)
    volumes = VolumeService(logos_store, chronos, articles)
    volumes.create(BOOK, VOLUME, {"title": "One"}, "mara")
    SectionService(logos_store, chronos, articles).create(
        BOOK, VOLUME, SECTION, section_payload(), "mara"
    )

    (scene,) = volumes.scene_details(
        BOOK, VOLUME, auth_store.grants_for("mara")
    )["sections"][0]["scenes"]

    assert scene["cast"] == [{**LYRA, "title": "Lyra Venn"}]
    assert scene["place"] is None
    assert scene["unseen"] == 1
