"""Integration tests for the read-only visualiser endpoints (mongomock)."""

import pytest

from tests.chronos.conftest import WRITER, ref

BOOK = "ember-pact"


@pytest.fixture
def seeded(app, fake_gate):
    """A gate that knows the cast/places, each with a small article body."""
    fake_gate.add(ref("aldric"), {"title": "Sir Aldric", "race": "Human"})
    fake_gate.add(ref("lyra"), {"title": "Lyra Vane"})
    for loc in ("highkeep", "emberport", "throne-hall"):
        fake_gate.add(ref(loc, "locations"), {"title": loc.title()})
    return app


def _event(client, eid, location="highkeep", start=0, end=10, characters=("aldric",), title=None):
    body = {
        "location": ref(location, "locations").to_dict(),
        "start_tick": start,
        "end_tick": end,
        "characters": [ref(c).to_dict() for c in characters],
    }
    if title:
        body["title"] = title
    return client.post(f"/books/{BOOK}/events/{eid}", json=body)


def _plotline(client, pid, events, goals=("Win",), title=None):
    body = {"events": list(events), "goals": list(goals)}
    if title:
        body["title"] = title
    return client.post(f"/books/{BOOK}/plotlines/{pid}", json=body)


@pytest.fixture
def book_with_plotlines(seeded, client, auth_store):
    client.post(f"/books/{BOOK}", json={"title": "The Ember Pact"})
    _event(client, "aldric-departs", "highkeep", 0, 10, title="Aldric Departs")
    _event(client, "harbor-exchange", "emberport", 20, 30, title="The Harbor Exchange")
    _event(client, "coronation", "throne-hall", 40, 50, title="The Coronation")
    _plotline(client, "knights-road", ["aldric-departs", "coronation"],
              goals=["Deliver the Seal"], title="The Knight's Road")
    _plotline(client, "spys-shadow", ["harbor-exchange", "coronation"],
              goals=["Infiltrate"], title="The Spy's Shadow")
    # Give the writer Akasha read on the *character* articles (collection scope,
    # so it also covers a not-yet-created 'ghost'), but deliberately NOT on
    # 'locations' -- so we can exercise both the allowed and forbidden paths.
    auth_store.grant_owner(WRITER, BOOK, "characters", None, ["read"])
    return client


# -- the SPA shell -----------------------------------------------------------


def test_index_serves_the_spa(seeded, client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.mimetype == "text/html"
    assert b"Chronos" in resp.data
    assert b"js/app.js" in resp.data  # the module entrypoint is wired in


def test_index_requires_auth(seeded):
    resp = seeded.test_client().get("/")
    assert resp.status_code in (302, 401)


def test_static_assets_are_served(seeded, client):
    # The SPA is useless if its module/stylesheet aren't discoverable.
    assert client.get("/static/js/app.js").status_code == 200
    assert client.get("/static/visualizer.css").status_code == 200


def test_header_switcher_links_to_akasha(seeded, client):
    html = client.get("/").get_data(as_text=True)
    assert "service-switch" in html
    assert "Articles" in html and "Timeline" in html
    assert "http://localhost:5002" in html            # default akasha URL
    assert ">Admin<" not in html                        # writer is not an admin


def test_header_has_account_link(seeded, client):
    # akasha_url defaults to http://localhost:5002 in the test app, so the link
    # is that base + /account (relative "/account" under the single-origin gateway).
    html = client.get("/").get_data(as_text=True)
    assert ">Account<" in html and "/account" in html


def test_header_switcher_shows_admin_for_admins(seeded, app):
    from tests.chronos.conftest import _login

    admin = app.test_client()
    _login(admin, "admin", "admin-pass")
    html = admin.get("/").get_data(as_text=True)
    assert ">Admin<" in html
    assert "http://localhost:5002/admin" in html


def test_switcher_urls_are_configurable(story_store, fake_gate, auth_store):
    from visualizer.chronos.app import create_app

    app = create_app(
        story_store, fake_gate, auth_store, secret_key="s",
        akasha_url="https://world.example/akasha",
        chronos_url="https://world.example/chronos",
    )
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)
    c = app.test_client()
    assert c.post("/login", json={"username": "mara", "password": "mara-pass"}).status_code == 200
    html = c.get("/").get_data(as_text=True)
    assert "https://world.example/akasha" in html
    assert 'aria-current="page"' in html               # chronos tab marked active


# -- listing / ordering / filter / pagination --------------------------------


def test_lists_plotlines_ordered_by_name(book_with_plotlines):
    resp = book_with_plotlines.get(f"/books/{BOOK}/ui/plotlines")
    assert resp.status_code == 200
    body = resp.get_json()
    assert [p["name"] for p in body["plotlines"]] == ["The Knight's Road", "The Spy's Shadow"]
    assert body["total"] == 2 and body["page"] == 1 and body["pages"] == 1
    # Filter-only fields are not leaked into the table rows.
    assert set(body["plotlines"][0]) == {"id", "book", "name", "goals"}


def test_filter_matches_event_title_on_effective_path(book_with_plotlines):
    # "harbor" appears only as an event title in the spy's thread.
    resp = book_with_plotlines.get(f"/books/{BOOK}/ui/plotlines?filter=harbor")
    body = resp.get_json()
    assert [p["id"] for p in body["plotlines"]] == ["spys-shadow"]


def test_filter_requires_all_words(book_with_plotlines):
    resp = book_with_plotlines.get(f"/books/{BOOK}/ui/plotlines?filter=knight+deliver")
    assert [p["id"] for p in resp.get_json()["plotlines"]] == ["knights-road"]
    resp = book_with_plotlines.get(f"/books/{BOOK}/ui/plotlines?filter=knight+infiltrate")
    assert resp.get_json()["plotlines"] == []


def test_pagination(book_with_plotlines):
    resp = book_with_plotlines.get(f"/books/{BOOK}/ui/plotlines?per_page=1&page=2")
    body = resp.get_json()
    assert body["per_page"] == 1 and body["pages"] == 2 and body["page"] == 2
    assert [p["name"] for p in body["plotlines"]] == ["The Spy's Shadow"]


def test_unknown_book_is_forbidden(seeded, client):
    # Authorize-first, like every content route: an unreadable book is 403
    # whether or not it exists, so existence is never leaked.
    resp = client.get("/books/nope/ui/plotlines")
    assert resp.status_code == 403


def test_listing_requires_read_permission(book_with_plotlines, app):
    from tests.chronos.conftest import _login

    other = app.test_client()
    _login(other, "admin", "admin-pass")  # admin holds no book grants by default
    assert other.get(f"/books/{BOOK}/ui/plotlines").status_code == 403


# -- entity proxy ------------------------------------------------------------


def test_fetch_entity_returns_article(book_with_plotlines):
    resp = book_with_plotlines.get(
        f"/books/{BOOK}/ui/entity/ember-pact/characters/aldric"
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["document"]["title"] == "Sir Aldric"
    assert body["document"]["race"] == "Human"


def test_fetch_missing_entity_reports_entity_not_found(book_with_plotlines):
    # A ref can dangle (article deleted after the event was written); the proxy
    # surfaces Chronos's ENTITY_NOT_FOUND rather than a 500.
    resp = book_with_plotlines.get(
        f"/books/{BOOK}/ui/entity/ember-pact/characters/ghost"
    )
    assert resp.status_code == 422
    assert resp.get_json()["code"] == "ENTITY_NOT_FOUND"


def test_fetch_entity_forbidden_without_article_grant(book_with_plotlines):
    # The writer can read the book, but was never granted read on 'locations'.
    # The per-article check must refuse even though the book check passes.
    resp = book_with_plotlines.get(
        f"/books/{BOOK}/ui/entity/ember-pact/locations/highkeep"
    )
    assert resp.status_code == 403
    assert resp.get_json()["code"] == "FORBIDDEN"


def test_article_grant_check_does_not_leak_existence(book_with_plotlines):
    # Whether or not the article exists, lacking the grant yields the same 403 --
    # so the proxy never reveals a forbidden article's existence.
    forbidden_real = book_with_plotlines.get(
        f"/books/{BOOK}/ui/entity/ember-pact/locations/highkeep"
    )
    forbidden_ghost = book_with_plotlines.get(
        f"/books/{BOOK}/ui/entity/ember-pact/locations/nowhere"
    )
    assert forbidden_real.status_code == forbidden_ghost.status_code == 403


def test_entity_proxy_requires_book_read_permission(book_with_plotlines, app):
    # No book grant at all -> refused at the book gate, before the article is
    # ever consulted.
    from tests.chronos.conftest import _login

    other = app.test_client()
    _login(other, "admin", "admin-pass")
    resp = other.get(f"/books/{BOOK}/ui/entity/ember-pact/characters/aldric")
    assert resp.status_code == 403


def test_entity_proxy_requires_auth(seeded):
    resp = seeded.test_client().get(f"/books/{BOOK}/ui/entity/ember-pact/characters/aldric")
    assert resp.status_code in (302, 401)
