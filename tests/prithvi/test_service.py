"""The rules that are neither storage nor HTTP: visibility, bounds, and history.

These run against a dictionary-backed article gateway, so what is being tested
is the service's own reasoning rather than Akasha's.
"""

import pytest

from visualizer.prithvi.errors import (
    ArticleNotFound,
    Forbidden,
    MapNotFound,
    PinNotFound,
    RevisionNotRetained,
    ViewBoxLocked,
    WorldNotFound,
)
from visualizer.prithvi.models import ArticleRef
from visualizer.prithvi.services import PrithviService
from visualizer.prithvi.svg import sanitize_svg

from .conftest import CLOSED_ARTICLE, COLLECTION, MAP, OPEN_ARTICLE, WORLD

WIDE = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50"/>'
NARROW = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 20"/>'

ANYTHING = ArticleRef(WORLD, COLLECTION, OPEN_ARTICLE)


def everything(ref):
    return True


def all_but_the_closed_one(ref):
    return ref.article_id != CLOSED_ARTICLE


@pytest.fixture
def service(prithvi_store, fake_articles):
    return PrithviService(
        prithvi_store,
        fake_articles,
        lambda upload: sanitize_svg(upload, 10_000),
        akasha_url="/",
    )


@pytest.fixture
def mapped_service(service):
    service.create_map(WORLD, MAP, WIDE, "mara")
    return service


def pin(service, article=OPEN_ARTICLE, x=10, y=10, may_read=everything):
    return service.create_pin(
        WORLD, MAP, COLLECTION, article, {"x": x, "y": y}, may_read, "mara"
    )


# -- maps ---------------------------------------------------------------------


def test_a_map_needs_a_world_that_exists(service):
    with pytest.raises(WorldNotFound):
        service.create_map("nowhere", MAP, WIDE, "mara")


def test_the_drawing_can_be_replaced(mapped_service):
    updated = mapped_service.replace_svg(WORLD, MAP, WIDE, 1, "mara")
    assert updated["rev"] == 2


def test_the_coordinate_space_is_frozen_while_pins_sit_in_it(mapped_service):
    """Changing the box would silently move every pin measured against it."""
    pin(mapped_service)

    with pytest.raises(ViewBoxLocked) as raised:
        mapped_service.replace_svg(WORLD, MAP, NARROW, 1, "mara")

    assert raised.value.evidence == {
        "current": [0.0, 0.0, 100.0, 50.0],
        "submitted": [0.0, 0.0, 40.0, 20.0],
    }


def test_the_coordinate_space_may_change_when_nothing_is_pinned(mapped_service):
    updated = mapped_service.replace_svg(WORLD, MAP, NARROW, 1, "mara")
    assert updated["view_box"] == [0.0, 0.0, 40.0, 20.0]


def test_a_scale_is_recorded_and_survives_a_redraw(mapped_service):
    scaled = mapped_service.set_scale(
        WORLD, MAP, {"across": 400, "unit": "leagues"}, 1, "mara"
    )
    assert scaled["scale"] == {"across": 400.0, "unit": "leagues"}

    redrawn = mapped_service.replace_svg(WORLD, MAP, WIDE, 2, "mara")
    assert redrawn["scale"] == {"across": 400.0, "unit": "leagues"}


def test_restoring_a_map_cannot_smuggle_in_a_different_space(mapped_service):
    """A restore reaches past the moment the box was legitimately reshaped."""
    mapped_service.replace_svg(WORLD, MAP, NARROW, 1, "mara")
    pin(mapped_service, x=5, y=5)

    with pytest.raises(ViewBoxLocked):
        mapped_service.restore_map(WORLD, MAP, 1, 2, "mara")


def test_a_deletion_is_not_a_revision_to_restore_to(mapped_service):
    mapped_service.delete_map(WORLD, MAP, 1, "mara")
    with pytest.raises(RevisionNotRetained):
        mapped_service.restore_map(WORLD, MAP, 2, 2, "mara")


def test_deleting_a_map_takes_its_pins_out_of_sight_and_restoring_brings_them_back(
    mapped_service,
):
    pin(mapped_service)
    mapped_service.delete_map(WORLD, MAP, 1, "mara")

    with pytest.raises(MapNotFound):
        mapped_service.list_pins(WORLD, MAP, everything)

    mapped_service.restore_map(WORLD, MAP, 1, 2, "mara")
    assert len(mapped_service.list_pins(WORLD, MAP, everything)) == 1


# -- pins ---------------------------------------------------------------------


def test_a_pin_names_an_article_that_exists(mapped_service):
    with pytest.raises(ArticleNotFound):
        pin(mapped_service, article="never-written")


def test_a_pin_carries_the_article_title_as_it_is_now(mapped_service, fake_articles):
    placed = pin(mapped_service)
    assert placed["article"]["title"] == "Highkeep"

    fake_articles.add(ArticleRef(WORLD, COLLECTION, OPEN_ARTICLE), {"title": "The Keep"})
    assert mapped_service.get_pin(
        WORLD, MAP, COLLECTION, OPEN_ARTICLE, everything
    )["article"]["title"] == "The Keep"


def test_a_pin_whose_article_is_deleted_says_so_rather_than_disappearing(
    mapped_service, fake_articles
):
    pin(mapped_service)
    fake_articles.remove(ArticleRef(WORLD, COLLECTION, OPEN_ARTICLE))

    article = mapped_service.get_pin(
        WORLD, MAP, COLLECTION, OPEN_ARTICLE, everything
    )["article"]

    assert article["status"] == "missing"
    assert article["title"] is None


def test_pinning_an_article_you_cannot_read_is_refused(mapped_service):
    with pytest.raises(Forbidden):
        pin(mapped_service, article=CLOSED_ARTICLE, may_read=all_but_the_closed_one)


def test_a_pin_you_cannot_read_is_invisible_rather_than_forbidden(mapped_service):
    """Saying "forbidden" would confirm that something is pinned there."""
    pin(mapped_service, article=CLOSED_ARTICLE)

    with pytest.raises(PinNotFound):
        mapped_service.get_pin(
            WORLD, MAP, COLLECTION, CLOSED_ARTICLE, all_but_the_closed_one
        )


def test_invisible_pins_are_absent_from_listings_and_from_the_drawing(mapped_service):
    pin(mapped_service, article=OPEN_ARTICLE)
    pin(mapped_service, article=CLOSED_ARTICLE, x=20, y=20)

    visible = mapped_service.list_pins(WORLD, MAP, all_but_the_closed_one)
    drawn = mapped_service.render(WORLD, MAP, all_but_the_closed_one)

    assert [row["article"]["id"] for row in visible] == [OPEN_ARTICLE]
    assert "Oathstone" not in drawn
    assert "Highkeep" in drawn


def test_a_moved_pin_keeps_its_history(mapped_service):
    pin(mapped_service, x=10, y=10)
    mapped_service.update_pin(
        WORLD, MAP, COLLECTION, OPEN_ARTICLE, {"x": 20, "y": 20}, everything, 1, "mara"
    )

    history = mapped_service.pin_history(
        WORLD, MAP, COLLECTION, OPEN_ARTICLE, everything
    )
    older = mapped_service.pin_revision(
        WORLD, MAP, COLLECTION, OPEN_ARTICLE, 1, everything
    )

    assert [v["op"] for v in history] == ["update", "create"]
    assert older["position"] == {"x": 10.0, "y": 10.0}


def test_a_removed_pin_can_simply_be_placed_again(mapped_service):
    pin(mapped_service, x=10, y=10)
    mapped_service.delete_pin(
        WORLD, MAP, COLLECTION, OPEN_ARTICLE, everything, 1, "mara"
    )

    replaced = pin(mapped_service, x=30, y=30)

    assert replaced["position"] == {"x": 30.0, "y": 30.0}
    assert replaced["rev"] == 3


def test_a_removed_pin_can_also_be_restored_where_it_was(mapped_service):
    pin(mapped_service, x=10, y=10)
    mapped_service.delete_pin(
        WORLD, MAP, COLLECTION, OPEN_ARTICLE, everything, 1, "mara"
    )

    restored = mapped_service.restore_pin(
        WORLD, MAP, COLLECTION, OPEN_ARTICLE, 1, everything, 2, "mara"
    )

    assert restored["position"] == {"x": 10.0, "y": 10.0}


def test_the_rendered_map_links_each_pin_to_its_article(mapped_service):
    pin(mapped_service)
    drawn = mapped_service.render(WORLD, MAP, everything)
    assert f'href="/#/{WORLD}/{COLLECTION}/{OPEN_ARTICLE}"' in drawn
    assert "prithvi-pins" in drawn


def test_a_deleted_pin_revision_is_not_something_to_restore_to(mapped_service):
    pin(mapped_service)
    mapped_service.delete_pin(
        WORLD, MAP, COLLECTION, OPEN_ARTICLE, everything, 1, "mara"
    )
    with pytest.raises(RevisionNotRetained):
        mapped_service.restore_pin(
            WORLD, MAP, COLLECTION, OPEN_ARTICLE, 2, everything, 2, "mara"
        )


def test_a_pin_whose_article_is_gone_is_drawn_but_not_linked(
    mapped_service, fake_articles
):
    """A dangling pin still marks the spot; there is just nowhere to send you."""
    pin(mapped_service)
    fake_articles.remove(ArticleRef(WORLD, COLLECTION, OPEN_ARTICLE))

    drawn = mapped_service.render(WORLD, MAP, everything)

    assert "prithvi-pin" in drawn
    assert "<a " not in drawn
