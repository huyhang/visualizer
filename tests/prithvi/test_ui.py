"""The browser UI: its shell, its catalog routes, and who each shows what.

The interesting cases here are all about disagreement between what the page
*offers* and what the API will *allow*. A UI that lists a world you cannot open,
or shows an upload button the server will refuse, is worse than one that shows
nothing: it turns a permission boundary into a dead end the reader discovers by
clicking. So these tests check both halves of each pair.
"""

import pytest
from werkzeug.security import generate_password_hash

from .conftest import (
    CLOSED_ARTICLE,
    COLLECTION,
    MAP_URL,
    OPEN_ARTICLE,
    SVG,
    WORLD,
    login,
)

ARTICLES_URL = f"/ui/worlds/{WORLD}/articles"
PREVIEW_URL = f"{ARTICLES_URL}/{COLLECTION}/{OPEN_ARTICLE}"


# -- the shell -------------------------------------------------------------------


def test_the_map_browser_is_served_at_the_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    body = response.get_data(as_text=True)
    assert 'id="world-grid"' in body
    assert 'id="map-stage"' in body
    assert "js/app.js" in body


def test_the_map_browser_needs_a_login(app):
    assert app.test_client().get("/").status_code in (302, 401)


def test_the_header_offers_all_three_services(client):
    body = client.get("/").get_data(as_text=True)
    assert "Articles" in body and "Timeline" in body and "Maps" in body
    assert 'aria-current="page"' in body


@pytest.mark.parametrize(
    "path",
    [
        "/static/maps.css",
        "/static/js/app.js",
        "/static/js/shared/slug.js",
        "/static/prithvi-glyph.svg",
        "/static/prithvi-icon.svg",
    ],
)
def test_the_frontend_assets_are_reachable(client, path):
    assert client.get(path).status_code == 200


def test_the_page_wears_prithvis_own_mark(client):
    body = client.get("/").get_data(as_text=True)
    assert "prithvi-glyph.svg" in body       # the header square
    assert "prithvi-icon.svg" in body        # the browser tab
    assert 'rel="icon"' in body


# -- the world catalog -----------------------------------------------------------


def test_a_writer_sees_what_they_may_do_in_each_world(client):
    worlds = client.get("/ui/worlds").get_json()["worlds"]
    assert worlds == [
        {
            "id": WORLD,
            "title": "Ember Pact",
            "map_count": 0,
            "can_write": True,
            "can_delete": True,
        }
    ]


def test_a_reader_is_offered_no_write_or_delete(reader):
    world = reader.get("/ui/worlds").get_json()["worlds"][0]
    assert world["can_write"] is False
    assert world["can_delete"] is False


def test_the_world_list_counts_its_maps(mapped):
    assert mapped.get("/ui/worlds").get_json()["worlds"][0]["map_count"] == 1


def test_the_world_list_and_the_map_routes_agree(app, auth_store):
    """A grant too narrow to open a world must also be too narrow to list it.

    ``read`` on a single article is not ``read`` on the world, so Prithvi's map
    routes refuse it. If the catalog used a looser rule -- "any grant touching
    this database" -- the world would appear on the landing page and 403 on
    click. Both questions go through one predicate so they cannot drift.
    """
    auth_store.create_user("nell", generate_password_hash("nell-pw"))
    auth_store.add_grant(
        "nell", WORLD, COLLECTION, OPEN_ARTICLE, ["read"], granted_by="admin"
    )
    narrow = app.test_client()
    assert login(narrow, "nell").status_code == 200

    assert narrow.get("/ui/worlds").get_json() == {"worlds": []}
    assert narrow.get(f"/worlds/{WORLD}/maps").status_code == 403


# -- the article picker ----------------------------------------------------------


def test_the_picker_offers_only_articles_the_caller_may_read(client, reader):
    def ids(browser):
        page = browser.get(ARTICLES_URL).get_json()
        return {article["id"] for article in page["articles"]}

    assert ids(client) == {OPEN_ARTICLE, CLOSED_ARTICLE}
    assert ids(reader) == {OPEN_ARTICLE}


def test_the_picker_searches_titles_and_ids(client):
    found = client.get(f"{ARTICLES_URL}?q=high").get_json()["articles"]
    assert [article["id"] for article in found] == [OPEN_ARTICLE]


def test_the_picker_ships_the_readable_name_beside_the_slug(client):
    first = client.get(ARTICLES_URL).get_json()["articles"][0]
    assert first["title"] == "Highkeep"
    assert first["collection_title"] == "Locations"


def test_the_picker_refuses_a_world_the_caller_cannot_read(client):
    assert client.get("/ui/worlds/no-such-world/articles").status_code == 403


# -- the pin preview -------------------------------------------------------------


def test_a_preview_is_the_compact_card_the_map_shows(client):
    card = client.get(PREVIEW_URL).get_json()
    assert card["title"] == "Highkeep"
    assert card["collection_title"] == "Locations"
    # Wikitext is flattened server-side; the page prints it with textContent.
    assert card["excerpt"] == "A fortress above the Ember Road."
    assert card["facts"] == [{"key": "Kind", "value": "Fortress"}]
    assert card["url"] == f"/#/{WORLD}/{COLLECTION}/{OPEN_ARTICLE}"


def test_an_article_you_cannot_read_answers_exactly_as_one_that_is_gone(client, reader):
    """Forbidden and missing must be indistinguishable, or the 404 leaks.

    Telling the two apart -- a different status, code or message -- would
    confirm that the article exists, which is the one fact the grant is meant
    to withhold. This is the pin rule from ``services`` applied to the card.
    """
    forbidden = reader.get(f"{ARTICLES_URL}/{COLLECTION}/{CLOSED_ARTICLE}")
    missing = client.get(f"{ARTICLES_URL}/{COLLECTION}/nothing-here")

    assert forbidden.status_code == missing.status_code
    assert forbidden.get_json()["code"] == missing.get_json()["code"]
    assert forbidden.get_json()["error"] == missing.get_json()["error"]
    assert forbidden.get_json()["evidence"]["article"]["status"] == "missing"


# -- the write path --------------------------------------------------------------


def test_the_ui_adds_no_second_way_to_write(app):
    """Every mutation still goes through the documented map and pin routes."""
    rules = app.url_map.iter_rules()
    ui_routes = [rule for rule in rules if str(rule).startswith("/ui")]
    assert ui_routes, "expected the catalog routes to exist"
    for rule in ui_routes:
        assert rule.methods & {"POST", "PUT", "PATCH", "DELETE"} == set()


def test_a_map_uploaded_through_the_api_carries_its_display_title(client):
    created = client.post(MAP_URL, data=SVG, content_type="image/svg+xml")
    assert created.status_code == 201
    assert created.get_json()["title"] == "Western Realms"
