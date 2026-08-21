"""The Akasha seam, against the real ``DocumentStore`` rather than a stand-in."""

import pytest

from visualizer.prithvi.errors import ArticleNotFound, WorldNotFound
from visualizer.prithvi.models import ArticleRef

from .conftest import COLLECTION, OPEN_ARTICLE, WORLD


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
