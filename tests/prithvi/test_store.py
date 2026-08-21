"""What Prithvi's two identities mean, checked against an in-memory Mongo."""

import pytest

from visualizer.prithvi.errors import AlreadyExists, MapNotFound, PinNotFound

BODY = {"svg": "<svg/>", "view_box": [0.0, 0.0, 10.0, 10.0], "sanitization": {}}
AT = {"x": 1.0, "y": 2.0}


def test_a_map_belongs_to_its_world(prithvi_store):
    """Two worlds may each have a "capital"; neither takes the name from the other."""
    prithvi_store.create_map("ember-pact", "capital", BODY, "mara")
    prithvi_store.create_map("salt-road", "capital", BODY, "devi")

    assert prithvi_store.get_map("ember-pact", "capital")["created_by"] == "mara"
    assert prithvi_store.get_map("salt-road", "capital")["created_by"] == "devi"
    assert len(prithvi_store.list_maps("ember-pact")) == 1


def test_a_pin_is_an_article_on_a_map(prithvi_store):
    """Identity is the article's address, so one article has one place per map."""
    prithvi_store.create_map("ember-pact", "west", BODY, "mara")
    prithvi_store.create_pin("ember-pact", "west", "locations", "highkeep", AT, "mara")

    with pytest.raises(AlreadyExists):
        prithvi_store.create_pin(
            "ember-pact", "west", "locations", "highkeep", {"x": 9, "y": 9}, "mara"
        )
    assert prithvi_store.count_pins("ember-pact", "west") == 1


def test_the_same_article_may_be_pinned_on_a_second_map(prithvi_store):
    for name in ("west", "east"):
        prithvi_store.create_map("ember-pact", name, BODY, "mara")
        prithvi_store.create_pin("ember-pact", name, "locations", "highkeep", AT, "mara")

    assert prithvi_store.count_pins("ember-pact", "west") == 1
    assert prithvi_store.count_pins("ember-pact", "east") == 1


def test_pins_are_listed_per_map_only(prithvi_store):
    prithvi_store.create_map("ember-pact", "west", BODY, "mara")
    prithvi_store.create_map("ember-pact", "east", BODY, "mara")
    prithvi_store.create_pin("ember-pact", "west", "locations", "highkeep", AT, "mara")

    assert len(prithvi_store.list_pins("ember-pact", "west")) == 1
    assert prithvi_store.list_pins("ember-pact", "east") == []


def test_absent_records_are_named_by_the_right_error(prithvi_store):
    with pytest.raises(MapNotFound):
        prithvi_store.get_map("ember-pact", "nowhere")

    prithvi_store.create_map("ember-pact", "west", BODY, "mara")
    with pytest.raises(PinNotFound):
        prithvi_store.get_pin("ember-pact", "west", "locations", "nobody")


def test_maps_and_pins_keep_history_to_their_own_depths(mongo_client):
    """A map revision is a whole drawing; a pin revision is two numbers."""
    from visualizer.prithvi.store import PrithviStore

    store = PrithviStore(mongo_client, map_revisions_keep=2, pin_revisions_keep=4)
    store.create_map("ember-pact", "west", BODY, "mara")
    store.create_pin("ember-pact", "west", "locations", "highkeep", AT, "mara")
    for rev in range(1, 6):
        store.update_map("ember-pact", "west", BODY, rev, "mara")
        store.update_pin("ember-pact", "west", "locations", "highkeep", AT, rev, "mara")

    assert len(store.map_history("ember-pact", "west")) == 2
    assert len(store.pin_history("ember-pact", "west", "locations", "highkeep")) == 4
