"""The presenters: ranking, flattening and the card's shape, as arithmetic."""

import pytest

from visualizer.prithvi.models import ArticleRef
from visualizer.prithvi.presenters import (
    article_choices,
    article_preview,
    article_url,
    excerpt,
)

REF = ArticleRef("ember-pact", "locations", "highkeep")


def row(article_id, title=None, collection="locations", **document):
    return {
        "database": "ember-pact",
        "collection": collection,
        "id": article_id,
        "document": {"title": title, **document} if title else dict(document),
    }


# -- the picker's ordering --------------------------------------------------------


def test_an_exact_match_outranks_a_prefix_which_outranks_a_substring():
    found = article_choices(
        [row("old-keep", "The Old Keep"), row("keeps", "Keeps"), row("keep", "Keep")],
        "keep",
    )
    assert [choice["id"] for choice in found] == ["keep", "keeps", "old-keep"]


def test_a_collection_only_match_sorts_last():
    found = article_choices(
        [row("ashford", "Ashford"), row("locations-primer", "Locations Primer")],
        "locations",
    )
    # Both match -- one by title, one only because its collection is "locations".
    assert [choice["id"] for choice in found] == ["locations-primer", "ashford"]


def test_an_unfiltered_list_is_alphabetical_rather_than_arbitrary():
    found = article_choices([row("c", "Cinder"), row("a", "Ash"), row("b", "Bell")])
    assert [choice["title"] for choice in found] == ["Ash", "Bell", "Cinder"]


def test_the_choice_list_is_capped():
    rows = [row(f"place-{n:02}", f"Place {n:02}") for n in range(40)]
    assert len(article_choices(rows)) == 20
    assert len(article_choices(rows, limit=5)) == 5


def test_an_article_with_no_title_is_offered_under_its_id():
    assert article_choices([row("ember-road")])[0]["title"] == "ember-road"


def test_matching_is_case_insensitive():
    assert article_choices([row("highkeep", "Highkeep")], "HIGH")


# -- flattening a body ------------------------------------------------------------


@pytest.mark.parametrize(
    "body,expected",
    [
        ("''' Bold ''' and ''italic''", "Bold and italic"),
        ("[[locations/ember-road|the Ember Road]]", "the Ember Road"),
        ("[[locations/ember-road]]", "ember-road"),
        ("== History ==\nRaised in the third age.", "History Raised in the third age."),
        ("line one\n\n   line two", "line one line two"),
        ("", ""),
        (None, ""),
        (42, ""),
    ],
)
def test_a_body_becomes_plain_prose(body, expected):
    assert excerpt(body) == expected


def test_a_long_body_is_truncated_on_a_character_budget():
    result = excerpt("word " * 200, limit=40)
    assert len(result) == 40
    assert result.endswith("…")


# -- the card ---------------------------------------------------------------------


def test_the_card_carries_title_excerpt_facts_and_a_link():
    card = article_preview(
        REF,
        {"document": {
            "title": "Highkeep",
            "body": "Above the [[locations/ember-road|Ember Road]].",
            "kind": "Fortress",
            "ruling_house": "Vane",
        }},
        "/",
    )
    assert card["title"] == "Highkeep"
    assert card["collection_title"] == "Locations"
    assert card["excerpt"] == "Above the Ember Road."
    assert card["facts"] == [
        {"key": "Kind", "value": "Fortress"},
        {"key": "Ruling House", "value": "Vane"},
    ]
    assert card["url"] == "/#/ember-pact/locations/highkeep"


@pytest.mark.parametrize(
    "value,shown",
    [(True, "Yes"), (False, "No"), (["a", "b"], "a, b"), (3, "3")],
)
def test_fact_values_are_rendered_for_a_human(value, shown):
    card = article_preview(REF, {"document": {"held": value}}, "/")
    assert card["facts"] == [{"key": "Held", "value": shown}]


@pytest.mark.parametrize("empty", [None, "", [], ()])
def test_a_field_with_nothing_in_it_is_left_off_the_card(empty):
    assert article_preview(REF, {"document": {"held": empty}}, "/")["facts"] == []


def test_the_card_shows_at_most_six_facts():
    document = {f"field_{n}": n for n in range(20)}
    assert len(article_preview(REF, {"document": document}, "/")["facts"]) == 6


def test_an_untitled_article_falls_back_to_its_id():
    assert article_preview(REF, {"document": {}}, "/")["title"] == "highkeep"


def test_a_missing_document_does_not_raise():
    card = article_preview(REF, {}, "/")
    assert card["title"] == "highkeep" and card["facts"] == []


# -- the link back to Akasha -------------------------------------------------------


@pytest.mark.parametrize("base", ["/", "", "https://example/akasha/"])
def test_the_article_link_survives_any_mount(base):
    url = article_url(base, "ember-pact", "locations", "highkeep")
    assert url.endswith("/#/ember-pact/locations/highkeep")


def test_address_segments_are_escaped_into_the_link():
    url = article_url("/", "ember pact", "loc/ations", "a?b#c")
    assert url == "/#/ember%20pact/loc%2Fations/a%3Fb%23c"
