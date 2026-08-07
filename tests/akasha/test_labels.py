"""Unit tests for the derived namespace titles.

Pure string work, so it is tested directly rather than through a route; the
route tests below only check that the derived title actually reaches the
browse responses the browser renders from.
"""

import pytest

from visualizer.akasha.labels import derive_title


@pytest.mark.parametrize(
    "slug, expected",
    [
        ("ember-pact", "Ember Pact"),
        ("characters", "Characters"),
        ("lord_of_the_rings", "Lord of the Rings"),
        ("the-two-towers", "The Two Towers"),   # a small word still leads
        ("a-tale-of", "A Tale Of"),             # ...and still ends
        ("book-2", "Book 2"),
        ("many---dashes", "Many Dashes"),
        ("2nd-age", "2nd Age"),                 # not "2Nd"
    ],
)
def test_slugs_read_as_titles(slug, expected):
    assert derive_title(slug) == expected


@pytest.mark.parametrize("name", ["McTavish", "iPhone", "The Ember Pact", "ARDA"])
def test_a_name_with_capitals_is_left_alone(name):
    """The writer chose that spelling; title-casing it would ruin it."""
    assert derive_title(name) == name


@pytest.mark.parametrize("name", ["", "-", "--"])
def test_degenerate_names_survive(name):
    assert derive_title(name) == name


# -- reaching the browse responses -------------------------------------------


def test_browse_responses_carry_the_derived_title(client):
    client.post("/databases/ember-pact/collections/the-cast")
    database = client.get("/databases").get_json()["databases"][0]
    assert (database["name"], database["title"]) == ("ember-pact", "Ember Pact")

    body = client.get("/databases/ember-pact/collections").get_json()
    assert body["title"] == "Ember Pact"  # the page's own heading
    assert body["collections"][0]["title"] == "The Cast"


def test_the_article_list_names_its_breadcrumb_trail(client):
    client.post("/databases/ember-pact/collections/the-cast")
    body = client.get(
        "/databases/ember-pact/collections/the-cast/documents"
    ).get_json()
    assert body["database_title"] == "Ember Pact"
    assert body["collection_title"] == "The Cast"


def test_recent_and_suggest_name_the_scope_they_came_from(client):
    client.post("/databases/ember-pact/collections/the-cast")
    client.post("/databases/ember-pact/collections/the-cast/documents/aldric",
                json={"title": "Sir Aldric"})

    recent = client.get("/recent").get_json()["documents"][0]
    assert (recent["database_title"], recent["collection_title"]) == ("Ember Pact", "The Cast")

    suggestion = client.get("/suggest?q=aldric").get_json()["suggestions"][0]
    assert (suggestion["database_title"], suggestion["collection_title"]) == (
        "Ember Pact", "The Cast",
    )
    # The slug is still there: it is what a [[link]] would have to say.
    assert suggestion["slug"] == "aldric"


def test_templates_can_render_a_title(client):
    """`| title_of` is registered, so the account page can use it too."""
    client.post("/databases/ember-pact/collections/the-cast")
    page = client.get("/account").get_data(as_text=True)
    assert "Ember Pact" in page
