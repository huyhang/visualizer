"""The Akasha seam, against the real ``DocumentStore`` rather than a stand-in."""

import pytest

from visualizer.prithvi.errors import ArticleNotFound, WorldNotFound
from visualizer.prithvi.models import ArticleRef

from .conftest import CLOSED_ARTICLE, COLLECTION, OPEN_ARTICLE, WORLD


def test_a_real_article_comes_back_with_its_document(article_gateway):
    found = article_gateway.fetch(ArticleRef(WORLD, COLLECTION, OPEN_ARTICLE))
    assert found["document"]["title"] == "Highkeep"


def test_an_absent_article_names_itself_in_the_error(article_gateway):
    with pytest.raises(ArticleNotFound) as raised:
        article_gateway.fetch(ArticleRef(WORLD, COLLECTION, "never-written"))
    assert raised.value.evidence["article"]["id"] == "never-written"


def test_a_world_akasha_has_never_heard_of_is_refused(article_gateway):
    """Prithvi will not be the thing that brings a world into existence."""
    with pytest.raises(WorldNotFound):
        article_gateway.require_world("no-such-world")


def test_a_world_with_articles_in_it_is_accepted(article_gateway):
    article_gateway.require_world(WORLD)


def test_the_worlds_akasha_knows_can_be_listed(article_gateway):
    assert article_gateway.list_worlds() == [WORLD]


def test_articles_come_back_as_flat_rows_the_picker_can_shape(article_gateway):
    rows = article_gateway.list_articles(WORLD)
    assert [(row["collection"], row["id"]) for row in rows] == [
        (COLLECTION, OPEN_ARTICLE),
        (COLLECTION, CLOSED_ARTICLE),
    ]
    assert all(row["database"] == WORLD for row in rows)
    assert rows[0]["document"]["title"] == "Highkeep"


def test_listing_is_unfiltered_because_only_the_route_knows_who_is_asking(
    article_gateway,
):
    """The seam answers "what exists"; grants are applied a layer up.

    Worth pinning: if this ever started filtering, the route's own check would
    become a second, weaker copy of the same rule.
    """
    assert len(article_gateway.list_articles(WORLD)) == 2


def test_listing_a_world_that_is_not_there_is_refused_like_any_other_read(
    article_gateway,
):
    with pytest.raises(WorldNotFound):
        article_gateway.list_articles("no-such-world")
