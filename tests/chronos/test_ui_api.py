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


def _plotline(client, pid, events, goals=(), title=None):
    body = {"events": list(events), "goals": list(goals)}
    if title:
        body["title"] = title
    return client.post(f"/books/{BOOK}/plotlines/{pid}", json=body)


def _goal(client, gid, title, **body):
    return client.post(f"/books/{BOOK}/goals/{gid}", json={"title": title, **body})


@pytest.fixture
def book_with_plotlines(seeded, client, auth_store):
    client.post(f"/books/{BOOK}", json={"title": "The Ember Pact"})
    _event(client, "aldric-departs", "highkeep", 0, 10, title="Aldric Departs")
    _event(client, "harbor-exchange", "emberport", 20, 30, title="The Harbor Exchange")
    _event(client, "coronation", "throne-hall", 40, 50, title="The Coronation")
    # Two goals, each pursued by a thread and neither anchored to a scene --
    # which is what a book in progress looks like, and leaves these threads with
    # nothing said about them beyond "no scene achieves this yet".
    _goal(client, "seal", "Deliver the Seal")
    _goal(client, "set-out", "Set out")
    _goal(client, "infiltrate", "Infiltrate")
    _plotline(client, "knights-road", ["aldric-departs", "coronation"],
              goals=["seal"], title="The Knight's Road")
    _plotline(client, "spys-shadow", ["harbor-exchange", "coronation"],
              goals=["infiltrate"], title="The Spy's Shadow")
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
    assert "Articles" in html and "Timeline" in html and "Maps" in html
    assert "http://localhost:5002" in html            # default akasha URL
    assert "http://localhost:5004" in html            # default prithvi URL
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


def test_switcher_urls_are_configurable(story_store, fake_gate, auth_store, calendar_store):
    from visualizer.chronos.app import create_app

    app = create_app(
        story_store, fake_gate, auth_store, calendar_store=calendar_store, secret_key="s",
        akasha_url="https://world.example/akasha",
        chronos_url="https://world.example/chronos",
        prithvi_url="https://world.example/maps",
    )
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)
    c = app.test_client()
    assert c.post("/login", json={"username": "mara", "password": "mara-pass"}).status_code == 200
    html = c.get("/").get_data(as_text=True)
    assert "https://world.example/akasha" in html
    assert "https://world.example/maps" in html
    assert 'aria-current="page"' in html               # chronos tab marked active


# -- listing / ordering / filter / pagination --------------------------------


def test_lists_plotlines_ordered_by_name(book_with_plotlines):
    resp = book_with_plotlines.get(f"/books/{BOOK}/ui/plotlines")
    assert resp.status_code == 200
    body = resp.get_json()
    assert [p["name"] for p in body["plotlines"]] == ["The Knight's Road", "The Spy's Shadow"]
    assert body["total"] == 2 and body["page"] == 1 and body["pages"] == 1
    # Filter-only fields are not leaked into the table rows. `overview` is not
    # one of them: it is filtered on *and* rendered, under the thread's name.
    assert set(body["plotlines"][0]) == {
        "id", "book", "name", "overview", "goals", "conflicts",
    }
    assert "event_titles" not in body["plotlines"][0]


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


# -- what the writer may do --------------------------------------------------


def test_book_says_what_the_current_user_may_do(book_with_plotlines):
    # The writer created the book, so they own it outright.
    perms = book_with_plotlines.get(f"/books/{BOOK}").get_json()["permissions"]
    assert perms == {"write": True, "delete": True}


def test_a_reader_is_told_they_may_not_edit(book_with_plotlines, app, auth_store):
    from tests.chronos.conftest import ADMIN_USER, _login
    from visualizer.chronos.app import BOOK_RESOURCE

    auth_store.grant_owner(ADMIN_USER, BOOK, None, None, ["read"], resource_type=BOOK_RESOURCE)
    reader = app.test_client()
    _login(reader, ADMIN_USER, "admin-pass")
    perms = reader.get(f"/books/{BOOK}").get_json()["permissions"]
    assert perms == {"write": False, "delete": False}


def test_the_table_flags_threads_that_have_problems(book_with_plotlines):
    # Neither seeded thread reaches a terminus (none is set) and both run
    # forwards, so both are clean.
    rows = book_with_plotlines.get(f"/books/{BOOK}/ui/plotlines").get_json()["plotlines"]
    assert [r["conflicts"] for r in rows] == [0, 0]

    # Put the knight's two scenes in the wrong order: one problem, one thread.
    book_with_plotlines.put(
        f"/books/{BOOK}/plotlines/knights-road",
        json={"events": ["coronation", "aldric-departs"], "goals": ["seal"]},
    )
    rows = book_with_plotlines.get(f"/books/{BOOK}/ui/plotlines").get_json()["plotlines"]
    assert {r["id"]: r["conflicts"] for r in rows} == {"knights-road": 1, "spys-shadow": 0}


# -- the scene picker --------------------------------------------------------


def test_lists_scenes_in_story_order(book_with_plotlines):
    resp = book_with_plotlines.get(f"/books/{BOOK}/events")
    assert resp.status_code == 200
    body = resp.get_json()
    assert [e["id"] for e in body["events"]] == [
        "aldric-departs", "harbor-exchange", "coronation",
    ]
    assert body["events"][0]["when"] == "0 → 10"
    assert body["events"][0]["plotlines"] == ["knights-road"]


def test_undated_scenes_come_last(book_with_plotlines):
    _event(book_with_plotlines, "someday", start=None, end=None, title="Someday")
    ids = [e["id"] for e in book_with_plotlines.get(f"/books/{BOOK}/events").get_json()["events"]]
    assert ids[-1] == "someday"


def test_scenes_are_findable_by_cast_and_place(book_with_plotlines):
    _event(book_with_plotlines, "lyras-errand", "emberport", 60, 70,
           characters=("lyra",), title="Lyra's Errand")
    found = book_with_plotlines.get(f"/books/{BOOK}/events?filter=lyra").get_json()
    assert [e["id"] for e in found["events"]] == ["lyras-errand"]
    at_port = book_with_plotlines.get(f"/books/{BOOK}/events?filter=emberport").get_json()
    assert {e["id"] for e in at_port["events"]} == {"harbor-exchange", "lyras-errand"}


def test_scene_listing_requires_read_permission(book_with_plotlines, app):
    from tests.chronos.conftest import _login

    other = app.test_client()
    _login(other, "admin", "admin-pass")
    assert other.get(f"/books/{BOOK}/events").status_code == 403


# -- preview -----------------------------------------------------------------


def _preview(client, **body):
    return client.post(f"/books/{BOOK}/ui/plotline-preview", json=body)


def test_preview_marks_an_out_of_order_pair_without_saving_it(book_with_plotlines):
    resp = _preview(
        book_with_plotlines,
        id="knights-road",
        events=["coronation", "aldric-departs"],
        goals=["seal"],
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"]["ordering"]["state"] == "conflicted"
    marked = {e["id"]: [f["code"] for f in e["findings"]] for e in body["effective_events"]}
    assert marked == {
        "coronation": ["ORDERING_VIOLATION"], "aldric-departs": ["ORDERING_VIOLATION"],
    }
    # ...and the stored thread is untouched.
    stored = book_with_plotlines.get(f"/books/{BOOK}/plotlines/knights-road").get_json()
    assert stored["events"] == ["aldric-departs", "coronation"]
    assert stored["rev"] == 1


def test_preview_of_a_sound_order_reports_nothing(book_with_plotlines):
    body = _preview(
        book_with_plotlines, id="knights-road",
        events=["aldric-departs", "coronation"], goals=["seal"],
    ).get_json()
    assert all(e["findings"] == [] for e in body["effective_events"])
    assert body["status"]["ordering"]["state"] == "ok"


def test_preview_works_for_a_plotline_that_does_not_exist_yet(book_with_plotlines):
    # A brand-new thread has no id and no goals yet; it must still be judged, or
    # the editor would give no feedback until after the first save.
    resp = _preview(book_with_plotlines, events=["coronation", "harbor-exchange"])
    assert resp.status_code == 200
    body = resp.get_json()
    assert [e["id"] for e in body["effective_events"]] == ["coronation", "harbor-exchange"]
    assert body["status"]["ordering"]["state"] == "conflicted"


def test_preview_does_not_pretend_to_be_a_saved_plotline(book_with_plotlines):
    # It runs through the same presenter, which is the point -- but a draft has
    # no revision, and its id may name nothing, so a `self` link would 404.
    body = _preview(book_with_plotlines, events=["coronation"]).get_json()
    assert body["kind"] == "plotline-preview"
    assert "rev" not in body
    assert "self" not in body["_links"]
    assert set(body["_links"]) == {"book", "validate"}
    # ...while still carrying everything the editor draws.
    assert body["effective_events"] and "status" in body


def test_preview_resolves_a_candidate_continuation(book_with_plotlines):
    body = _preview(
        book_with_plotlines, events=["aldric-departs"], continues_into="spys-shadow"
    ).get_json()
    # The inherited tail shows up in the path, marked as not this thread's own.
    assert [e["id"] for e in body["effective_events"]] == [
        "aldric-departs", "harbor-exchange", "coronation",
    ]
    assert [e["owned"] for e in body["effective_events"]] == [True, False, False]


def test_preview_rejects_a_scene_that_does_not_exist(book_with_plotlines):
    resp = _preview(book_with_plotlines, events=["ghost-scene"])
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "INVALID_PLOTLINE"


def test_preview_rejects_an_empty_thread(book_with_plotlines):
    # A plotline needs at least one of its own scenes, continuation or not.
    assert _preview(book_with_plotlines, events=[]).status_code == 400


def test_preview_requires_write_permission(book_with_plotlines, app, auth_store):
    from tests.chronos.conftest import ADMIN_USER, _login
    from visualizer.chronos.app import BOOK_RESOURCE

    auth_store.grant_owner(ADMIN_USER, BOOK, None, None, ["read"], resource_type=BOOK_RESOURCE)
    reader = app.test_client()
    _login(reader, ADMIN_USER, "admin-pass")
    resp = reader.post(f"/books/{BOOK}/ui/plotline-preview", json={"events": ["coronation"]})
    assert resp.status_code == 403


# -- the article picker ------------------------------------------------------


def test_entity_search_offers_readable_articles(book_with_plotlines):
    body = book_with_plotlines.get(
        f"/books/{BOOK}/ui/entities?q=al&collection=characters"
    ).get_json()
    assert body["database"] == BOOK           # read off the book's existing scenes
    assert body["collections"] == ["characters", "locations"]
    assert [r["id"] for r in body["results"]] == ["aldric"]
    assert body["results"][0]["title"] == "Sir Aldric"


def test_entity_search_hides_what_akasha_would_refuse(book_with_plotlines):
    # The writer holds read on 'characters' only -- locations must not be
    # offered, exactly as the article proxy refuses to open them.
    body = book_with_plotlines.get(
        f"/books/{BOOK}/ui/entities?q=highkeep&collection=locations"
    ).get_json()
    assert body["results"] == []


def test_entity_search_requires_book_read_permission(book_with_plotlines, app):
    from tests.chronos.conftest import _login

    other = app.test_client()
    _login(other, "admin", "admin-pass")
    assert other.get(f"/books/{BOOK}/ui/entities?q=a").status_code == 403


# -- the editing round trip --------------------------------------------------


def test_a_thread_can_be_reordered_and_the_problem_goes_away(book_with_plotlines):
    broken = book_with_plotlines.put(
        f"/books/{BOOK}/plotlines/knights-road",
        json={"events": ["coronation", "aldric-departs"], "goals": ["seal"]},
    ).get_json()
    assert broken["status"]["ordering"]["state"] == "conflicted"

    fixed = book_with_plotlines.put(
        f"/books/{BOOK}/plotlines/knights-road",
        json={"events": ["aldric-departs", "coronation"], "goals": ["seal"]},
        headers={"If-Match": str(broken["rev"])},
    )
    assert fixed.status_code == 200
    assert fixed.get_json()["status"]["ordering"]["state"] == "ok"


def test_a_stale_edit_is_refused_rather_than_overwriting(book_with_plotlines):
    book_with_plotlines.put(
        f"/books/{BOOK}/plotlines/knights-road",
        json={"events": ["coronation"], "goals": ["seal"]},
    )
    stale = book_with_plotlines.put(
        f"/books/{BOOK}/plotlines/knights-road",
        json={"events": ["aldric-departs"], "goals": ["seal"]},
        headers={"If-Match": "1"},
    )
    assert stale.status_code == 409
    assert stale.get_json()["code"] == "REVISION_CONFLICT"


def test_expanded_events_mark_which_scenes_this_thread_owns(book_with_plotlines):
    book_with_plotlines.post(
        f"/books/{BOOK}/plotlines/prelude",
        json={
            "events": ["aldric-departs"],
            "goals": ["set-out"],
            "continues_into": "spys-shadow",
        },
    )
    body = book_with_plotlines.get(
        f"/books/{BOOK}/plotlines/prelude?expand=events"
    ).get_json()
    assert [(e["id"], e["owned"]) for e in body["effective_events"]] == [
        ("aldric-departs", True), ("harbor-exchange", False), ("coronation", False),
    ]


def test_plotline_status_counts_its_problems(book_with_plotlines):
    sound = book_with_plotlines.get(f"/books/{BOOK}/plotlines/knights-road").get_json()
    assert sound["status"]["conflicts"] == 0

    broken = book_with_plotlines.put(
        f"/books/{BOOK}/plotlines/knights-road",
        json={"events": ["coronation", "aldric-departs"], "goals": ["seal"]},
    ).get_json()
    # One problem the writer would recognise as one, though both scenes are marked.
    assert broken["status"]["conflicts"] == 1


# -- naming a tick in the book's calendar ------------------------------------


@pytest.fixture
def calendared(book_with_plotlines):
    """The demo calendar: hours, 24 to a day, 30 days to a month, 12 to a year."""
    book = book_with_plotlines.get(f"/books/{BOOK}").get_json()
    book_with_plotlines.put(f"/books/{BOOK}", json={
        "title": book["title"],
        "calendar": {
            "base_unit": "hour",
            "cycles": [
                {"name": "day", "size": 24},
                {"name": "month", "size": 30},
                {"name": "year", "size": 12},
            ],
            "epoch_label": "AF",
        },
    })
    return book_with_plotlines


def test_ticks_are_named_by_the_books_calendar(calendared):
    resp = calendared.get(f"/books/{BOOK}/ui/ticks?tick=240&tick=264")
    assert resp.status_code == 200
    ticks = resp.get_json()["ticks"]
    assert [t["tick"] for t in ticks] == [240, 264]  # answered in the order asked
    assert ticks[0]["label"] == "Year 1, Month 1, Day 11, 00:00 AF"
    assert ticks[0]["parts"] == ["Year 1", "Month 1", "Day 11", "00:00 AF"]


def test_ticks_match_what_a_saved_scene_will_show(calendared):
    # The form's preview and the timeline must agree, or the writer is being
    # told two different things about the same number.
    _event(calendared, "trial", "highkeep", 240, 264, title="The Trial")
    event = calendared.get(f"/books/{BOOK}/events/trial").get_json()
    preview = calendared.get(f"/books/{BOOK}/ui/ticks?tick=240").get_json()["ticks"][0]
    assert preview["label"] == event["start_label"]


def test_a_book_without_a_calendar_just_echoes_the_number(book_with_plotlines):
    ticks = book_with_plotlines.get(f"/books/{BOOK}/ui/ticks?tick=240").get_json()["ticks"]
    assert ticks[0]["label"] == "240"


def test_ticks_rejects_something_that_is_not_a_tick(calendared):
    resp = calendared.get(f"/books/{BOOK}/ui/ticks?tick=soon")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "INVALID_TIMEFRAME"


def test_ticks_asks_for_no_more_than_a_handful(calendared):
    # A timeframe has two ends; the cap keeps one caller from asking for a
    # thousand labels.
    many = "&".join(f"tick={n}" for n in range(50))
    assert len(calendared.get(f"/books/{BOOK}/ui/ticks?{many}").get_json()["ticks"]) == 8


def test_ticks_needs_book_read_permission(calendared, app):
    from tests.chronos.conftest import _login

    other = app.test_client()
    _login(other, "admin", "admin-pass")
    assert other.get(f"/books/{BOOK}/ui/ticks?tick=0").status_code == 403


def test_findings_hand_over_the_articles_they_name(book_with_plotlines):
    # 'aldric' is at highkeep 0-10 on the knight's thread; put him at emberport
    # over the same hours and the thread has a contradiction to explain.
    _event(book_with_plotlines, "quay-sighting", "emberport", 5, 15, title="The Quay Sighting")
    book_with_plotlines.put(
        f"/books/{BOOK}/plotlines/knights-road",
        json={"events": ["aldric-departs", "quay-sighting", "coronation"],
              "goals": ["seal"]},
    )
    body = book_with_plotlines.get(
        f"/books/{BOOK}/plotlines/knights-road?expand=events"
    ).get_json()
    finding = next(
        f for e in body["effective_events"] for f in e["findings"]
        if f["code"] == "TEMPORAL_CONFLICT"
    )
    # Ids are quoted so a client can substitute titles by exact match...
    assert "'aldric'" in finding["message"]
    # ...and the articles to resolve come with the finding.
    assert {(r["collection"], r["id"]) for r in finding["refs"]} == {
        ("characters", "aldric"), ("locations", "emberport"),
    }


def test_the_scene_a_finding_names_uses_its_own_title_not_its_id(book_with_plotlines):
    # Event titles are Chronos's own data, so they are resolved server-side --
    # only Akasha articles are left as ids for the client to look up.
    book_with_plotlines.put(
        f"/books/{BOOK}/plotlines/knights-road",
        json={"events": ["coronation", "aldric-departs"], "goals": ["seal"]},
    )
    body = book_with_plotlines.get(
        f"/books/{BOOK}/plotlines/knights-road?expand=events"
    ).get_json()
    messages = [f["message"] for e in body["effective_events"] for f in e["findings"]]
    assert any("'The Coronation'" in m for m in messages)
    assert not any("'coronation'" in m for m in messages)


def test_the_table_and_the_plotline_view_agree_about_a_thread(book_with_plotlines):
    # Two different code paths compute this number; a writer must never see the
    # table say 1 and the thread itself say 2.
    book_with_plotlines.put(
        f"/books/{BOOK}/plotlines/knights-road",
        json={"events": ["coronation", "aldric-departs"], "goals": ["seal"]},
    )
    _event(book_with_plotlines, "quay-sighting", "emberport", 5, 15, title="The Quay Sighting")
    rows = book_with_plotlines.get(f"/books/{BOOK}/ui/plotlines").get_json()["plotlines"]
    for row in rows:
        thread = book_with_plotlines.get(f"/books/{BOOK}/plotlines/{row['id']}").get_json()
        assert row["conflicts"] == thread["status"]["conflicts"], row["id"]


# -- the whole-book report ----------------------------------------------------


def _issues(client, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    resp = client.get(f"/books/{BOOK}/ui/issues" + (f"?{query}" if query else ""))
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _codes(section):
    return [i["code"] for group in section for i in group["issues"]]


def test_the_report_gathers_problems_from_every_thread(book_with_plotlines):
    # One contradiction on each thread: the knight's road runs backwards, and the
    # spy is put in two places at once.
    book_with_plotlines.put(
        f"/books/{BOOK}/plotlines/knights-road",
        json={"events": ["coronation", "aldric-departs"], "goals": ["seal"]},
    )
    # The harbour exchange puts aldric at emberport 20-30; this puts him at
    # highkeep over the same hours.
    _event(book_with_plotlines, "quay-sighting", "highkeep", 25, 35, title="The Quay Sighting")
    book_with_plotlines.put(
        f"/books/{BOOK}/plotlines/spys-shadow",
        json={"events": ["harbor-exchange", "quay-sighting", "coronation"],
              "goals": ["infiltrate"]},
    )
    body = _issues(book_with_plotlines)
    assert "ORDERING_VIOLATION" in _codes(body["problems"])
    assert "TEMPORAL_CONFLICT" in _codes(body["problems"])
    assert body["summary"]["problems"] == len(_codes(body["problems"]))


def test_the_report_says_which_threads_a_problem_lands_on(book_with_plotlines):
    # Both threads end at the coronation, so a conflict against it is visible
    # from each of them — which is the thing no single-thread view can say.
    _event(book_with_plotlines, "quay-sighting", "emberport", 45, 55, title="The Quay Sighting")
    book_with_plotlines.put(
        f"/books/{BOOK}/plotlines/knights-road",
        json={"title": "The Knight's Road", "goals": ["seal"],
              "events": ["aldric-departs", "quay-sighting", "coronation"]},
    )
    body = _issues(book_with_plotlines)
    conflict = next(
        i for g in body["problems"] for i in g["issues"] if i["code"] == "TEMPORAL_CONFLICT"
    )
    assert {p["id"] for p in conflict["plotlines"]} == {"knights-road", "spys-shadow"}
    # Named by title, not by id: the report is read, not parsed.
    assert {p["title"] for p in conflict["plotlines"]} == {
        "The Knight's Road", "The Spy's Shadow",
    }


def test_the_report_names_the_scene_a_message_is_about(book_with_plotlines):
    book_with_plotlines.put(
        f"/books/{BOOK}/plotlines/knights-road",
        json={"events": ["coronation", "aldric-departs"], "goals": ["seal"]},
    )
    issue = next(
        i for g in _issues(book_with_plotlines)["problems"] for i in g["issues"]
        if i["code"] == "ORDERING_VIOLATION"
    )
    assert issue["scene"]["title"] == "The Coronation"
    assert issue["events"] == [{"id": "aldric-departs", "title": "Aldric Departs"}]


# -- the report and the book card must never disagree -------------------------
#
# A book card reading `conflicted` is a link to this report now, so a card that
# says one thing and a page that says the other is the exact failure the
# click-through was built to prevent. And they are computed *independently*: the
# card from `reports.BookReport.ok`, the report from whether any issue came back
# at conflict severity.
#
# Each case below drives the book into one — and deliberately only one — of the
# ways `ok` can be false, and asserts both halves agree. The `code` is what pins
# the case honestly: without it a mutation that stopped the report noticing
# *this* category could still pass on some other fault firing at the same time.
#
# An empty plotline is the one member of `ok` missing here: a write refuses a
# thread with no scenes of its own, so it cannot be reached through the API.
# `test_book_health` covers it directly.

TERMINUS = f"/books/{BOOK}/terminus/coronation"


def _undated(client, event_id, title):
    return client.post(f"/books/{BOOK}/events/{event_id}", json={
        "location": ref("highkeep", "locations").to_dict(), "title": title,
    })


def _thread(client, events):
    return client.put(f"/books/{BOOK}/plotlines/knights-road", json={
        "title": "The Knight's Road", "goals": ["seal"], "events": events,
    })


def _sound(client, gate):
    client.post(TERMINUS)


def _only_an_undated_scene(client, gate):
    client.post(TERMINUS)
    _undated(client, "the-vigil", "The Vigil")
    # Between hours 10 and 40 — a window it can fit in, so a note, not a fault.
    _thread(client, ["aldric-departs", "the-vigil", "coronation"])


def _a_character_in_two_places(client, gate):
    client.post(TERMINUS)
    # The harbour exchange has aldric at emberport 20-30; this has him at
    # highkeep over the same hours, on a thread of its own.
    _event(client, "vigil-at-keep", "highkeep", 20, 30, title="Vigil At The Keep")
    _plotline(client, "kings-watch", ["vigil-at-keep", "coronation"], title="The King's Watch")


def _a_conflict_on_a_scene_no_thread_uses(client, gate):
    client.post(TERMINUS)
    # Never threaded: the case every per-thread pass is blind to by construction.
    _event(client, "stray-sighting", "emberport", 0, 10, title="A Stray Sighting")


def _scenes_out_of_order(client, gate):
    client.post(TERMINUS)
    _event(client, "dawn-ride", "highkeep", 60, 70, characters=("lyra",), title="The Dawn Ride")
    _thread(client, ["dawn-ride", "aldric-departs", "coronation"])


def _a_scene_with_no_room(client, gate):
    client.post(TERMINUS)
    _undated(client, "the-vigil", "The Vigil")
    # Must start after hour 30 and end before hour 0: no room at all.
    _thread(client, ["harbor-exchange", "the-vigil", "aldric-departs", "coronation"])


def _an_article_deleted_underneath_a_scene(client, gate):
    client.post(TERMINUS)
    gate.remove(ref("aldric"))


def _no_ending_designated(client, gate):
    pass  # the fixture never designates one


def _a_thread_that_stops_short(client, gate):
    client.post(TERMINUS)
    _thread(client, ["aldric-departs"])


@pytest.mark.parametrize("mutate,code", [
    (_sound, None),
    (_only_an_undated_scene, None),
    (_a_character_in_two_places, "TEMPORAL_CONFLICT"),
    (_a_conflict_on_a_scene_no_thread_uses, "TEMPORAL_CONFLICT"),
    (_scenes_out_of_order, "ORDERING_VIOLATION"),
    (_a_scene_with_no_room, "IMPOSSIBLE_WINDOW"),
    (_an_article_deleted_underneath_a_scene, "MISSING_ENTITY"),
    (_no_ending_designated, "NO_TERMINUS"),
    (_a_thread_that_stops_short, "TERMINUS_VIOLATION"),
], ids=lambda v: v.__name__.strip("_") if callable(v) else (v or ""))
def test_the_report_and_the_book_card_never_disagree(
    book_with_plotlines, fake_gate, mutate, code
):
    mutate(book_with_plotlines, fake_gate)

    body = _issues(book_with_plotlines)
    card = book_with_plotlines.get(f"/books/{BOOK}").get_json()["status"]
    assert body["status"] == card

    # ...and the case really did exercise the category it claims to.
    assert (code in _codes(body["problems"])) if code else body["status"] == "consistent"


def test_an_undated_scene_is_a_note_rather_than_a_problem(book_with_plotlines):
    book_with_plotlines.post(f"/books/{BOOK}/terminus/coronation")
    book_with_plotlines.post(
        f"/books/{BOOK}/events/the-vigil",
        json={"location": ref("highkeep", "locations").to_dict(),
              "characters": [ref("lyra").to_dict()], "title": "The Vigil"},
    )
    book_with_plotlines.put(
        f"/books/{BOOK}/plotlines/knights-road",
        json={"events": ["aldric-departs", "the-vigil", "coronation"],
              "goals": ["seal"]},
    )
    body = _issues(book_with_plotlines)
    assert _codes(body["problems"]) == []
    # The goal notes come from the fixture's three goals -- none of them anchored
    # to a scene yet, one of them pursued by nobody. Notes, all of them: the
    # point of this test is that a book mid-draft has plenty to say and nothing
    # wrong with it.
    assert _codes(body["notes"]) == [
        "UNSCHEDULED", "GOAL_UNSERVED", *["GOAL_UNACHIEVED"] * 3,
    ]
    assert body["summary"]["unscheduled"] == 1


def test_the_report_says_when_the_book_has_no_ending(book_with_plotlines):
    # The book fixture never designates one, so this is what a writer sees first.
    body = _issues(book_with_plotlines)
    assert _codes(body["problems"]) == ["NO_TERMINUS"]
    # Once said, once — not repeated at every thread in the book.
    assert body["problems"][0]["issues"][0]["plotlines"] == []


def test_the_report_names_a_thread_that_stops_short_of_the_ending(book_with_plotlines):
    book_with_plotlines.post(f"/books/{BOOK}/terminus/coronation")
    book_with_plotlines.put(
        f"/books/{BOOK}/plotlines/knights-road",
        json={"events": ["aldric-departs"], "goals": ["seal"]},
    )
    issue = next(
        i for g in _issues(book_with_plotlines)["problems"] for i in g["issues"]
        if i["code"] == "TERMINUS_VIOLATION"
    )
    assert [p["id"] for p in issue["plotlines"]] == ["knights-road"]
    assert "'Aldric Departs'" in issue["message"]
    assert "'The Coronation'" in issue["message"]


def test_the_report_lists_the_books_threads_so_it_can_be_narrowed(book_with_plotlines):
    body = _issues(book_with_plotlines)
    assert {p["id"] for p in body["plotlines"]} == {"knights-road", "spys-shadow"}
    # Named and counted, so the same answer serves as the filter's menu and as
    # the "which thread do I open first" triage list.
    assert {p["title"] for p in body["plotlines"]} == {
        "The Knight's Road", "The Spy's Shadow",
    }
    assert all(isinstance(p["problems"], int) for p in body["plotlines"])


def test_the_rollup_agrees_with_the_issues_on_the_page(book_with_plotlines):
    # Two numbers on one screen that could drift: the triage table at the foot
    # and the entries above it.
    book_with_plotlines.post(f"/books/{BOOK}/terminus/coronation")
    book_with_plotlines.put(
        f"/books/{BOOK}/plotlines/knights-road",
        json={"events": ["coronation", "aldric-departs"], "goals": ["seal"]},
    )
    body = _issues(book_with_plotlines)
    named = {}
    for group in body["problems"]:
        for issue in group["issues"]:
            for pl in issue["plotlines"]:
                named[pl["id"]] = named.get(pl["id"], 0) + 1
    for row in body["plotlines"]:
        assert row["problems"] == named.get(row["id"], 0), row["id"]
    assert named["knights-road"] >= 2  # runs backwards *and* misses the ending


def test_the_report_and_the_table_agree_about_a_thread(book_with_plotlines):
    """The same invariant the pure tests pin, through the real app.

    The report folds per-thread findings across the book; the table counts them
    in one pass. A writer sees both on adjacent screens.
    """
    book_with_plotlines.post(f"/books/{BOOK}/terminus/coronation")
    _event(book_with_plotlines, "quay-sighting", "emberport", 5, 15, title="The Quay Sighting")
    book_with_plotlines.put(
        f"/books/{BOOK}/plotlines/knights-road",
        json={"events": ["coronation", "aldric-departs", "quay-sighting"],
              "goals": ["seal"]},
    )
    body = _issues(book_with_plotlines)
    whole_thread = {"TERMINUS_VIOLATION", "EMPTY_PLOTLINE", "NO_TERMINUS"}
    rows = book_with_plotlines.get(f"/books/{BOOK}/ui/plotlines").get_json()["plotlines"]
    for row in rows:
        mine = [
            i for g in body["problems"] for i in g["issues"]
            if i["code"] not in whole_thread
            and any(p["id"] == row["id"] for p in i["plotlines"])
        ]
        assert len(mine) == row["conflicts"], row["id"]


def test_the_report_is_read_through_the_books_calendar(calendared):
    """Two of the messages quote ticks, so they are the calendar's to name."""
    calendared.post(
        f"/books/{BOOK}/events/the-vigil",
        json={"location": ref("highkeep", "locations").to_dict(), "title": "The Vigil"},
    )
    calendared.put(
        f"/books/{BOOK}/plotlines/knights-road",
        json={"events": ["aldric-departs", "the-vigil", "coronation"],
              "goals": ["seal"]},
    )
    note = next(
        i for g in _issues(calendared)["notes"] for i in g["issues"]
        if i["code"] == "UNSCHEDULED"
    )
    assert "Day" in note["message"], note["message"]


def test_the_report_needs_read_permission_on_the_book(book_with_plotlines, app):
    from tests.chronos.conftest import _login

    other = app.test_client()
    _login(other, "admin", "admin-pass")  # no grant on this book
    assert other.get(f"/books/{BOOK}/ui/issues").status_code == 403


def test_the_report_needs_a_session(seeded):
    assert seeded.test_client().get(f"/books/{BOOK}/ui/issues").status_code in (302, 401)


# -- the world a book draws its cast from ------------------------------------
#
# Before this existed the scope could only be *inferred* from scenes that were
# already written, so a brand-new book's article picker searched a database
# named after the book -- which is nothing -- and told the writer to go create
# articles that were sitting right there. Declaring a world breaks that
# chicken-and-egg. It stays a default, not a rule: an EntityRef still names its
# own database, so a scene may reach into another world deliberately.


def _grant_world(auth_store, user, database, perms=("read",)):
    auth_store.grant_owner(user, database, None, None, list(perms))


def test_a_declared_world_gives_a_scene_picker_something_to_search(seeded, client, auth_store):
    _grant_world(auth_store, WRITER, "ember-pact")
    client.post(f"/books/{BOOK}", json={"title": "T", "world": "ember-pact"})
    scope = client.get(f"/books/{BOOK}/ui/entities?collection=characters&q=").get_json()
    assert scope["database"] == "ember-pact"
    assert [r["id"] for r in scope["results"]] == ["aldric", "lyra"]


def test_without_one_a_brand_new_book_has_nowhere_to_look(seeded, client):
    """The gap this closes, pinned so it cannot quietly come back."""
    client.post(f"/books/{BOOK}", json={"title": "T"})
    scope = client.get(f"/books/{BOOK}/ui/entities?collection=characters&q=").get_json()
    assert scope["database"] == BOOK      # the book's own id, standing in for a world
    assert scope["collections"] == []
    assert scope["results"] == []


def test_a_book_written_before_the_field_existed_still_infers_its_scope(seeded, client, auth_store):
    """No migration: an old book has no 'world', and its scenes answer for it."""
    _grant_world(auth_store, WRITER, "ember-pact")
    client.post(f"/books/{BOOK}", json={"title": "T"})
    _event(client, "meet")
    assert client.get(f"/books/{BOOK}").get_json()["world"] is None
    scope = client.get(f"/books/{BOOK}/ui/entities?collection=characters&q=").get_json()
    assert scope["database"] == "ember-pact"
    assert scope["results"]


def test_the_declared_world_wins_over_what_the_scenes_suggest(seeded, client):
    """Declared beats inferred -- otherwise moving a book to a new world would
    be overruled by every scene already written against the old one."""
    # The scenes below reference ember-pact; the book is then moved elsewhere.
    client.post(f"/books/{BOOK}", json={"title": "T", "world": "ember-pact"})
    _event(client, "meet")
    rev = client.get(f"/books/{BOOK}").get_json()["rev"]
    client.put(f"/books/{BOOK}", json={"title": "T", "world": "second-age"},
               headers={"If-Match": str(rev)})
    scope = client.get(f"/books/{BOOK}/ui/entities?collection=characters&q=").get_json()
    assert scope["database"] == "second-age"


def test_a_world_is_a_default_not_a_fence(seeded, client):
    """A scene may still reference another world on purpose; declaring one
    points the picker, it does not police the write."""
    client.post(f"/books/{BOOK}", json={"title": "T", "world": "somewhere-else"})
    assert _event(client, "meet").status_code == 201   # refs point at ember-pact


def test_renaming_a_book_does_not_drop_its_world(seeded, client):
    """`world` is stored, so it is presented, so a client can send it back --
    the round trip the whole-document PUT depends on."""
    client.post(f"/books/{BOOK}", json={"title": "T", "world": "ember-pact"})
    before = client.get(f"/books/{BOOK}").get_json()
    assert before["world"] == "ember-pact"

    writable = {k: before[k] for k in ("title", "terminus", "calendar", "world")}
    writable["title"] = "Renamed"
    client.put(f"/books/{BOOK}", json=writable, headers={"If-Match": str(before["rev"])})

    after = client.get(f"/books/{BOOK}").get_json()
    assert after["title"] == "Renamed" and after["world"] == "ember-pact"


@pytest.mark.parametrize("world", ["", "   ", 7, []])
def test_a_world_that_is_not_a_name_is_refused(seeded, client, world):
    resp = client.post(f"/books/{BOOK}", json={"title": "T", "world": world})
    assert resp.status_code == 400 and resp.get_json()["code"] == "INVALID_BOOK"


# -- the world chooser --------------------------------------------------------


def test_worlds_lists_only_what_this_writer_can_read(seeded, client, auth_store, app):
    """Not book-scoped -- the writer picks a world while creating a book, when
    there is no book to authorize against -- so the Akasha grant is the only
    gate, and it has to actually hold."""
    other = app.test_client()
    other.post("/login", json={"username": "admin", "password": "admin-pass"})

    _grant_world(auth_store, WRITER, "ember-pact")
    mine = client.get("/ui/worlds").get_json()["worlds"]
    assert [w["database"] for w in mine] == ["ember-pact"]
    assert mine[0]["collections"] == ["characters", "locations"]

    # An admin holds no content grants unless given them: content access is not
    # an admin power (see conftest).
    assert other.get("/ui/worlds").get_json()["worlds"] == []


def test_worlds_needs_a_session(app):
    assert app.test_client().get("/ui/worlds").status_code in (302, 401)

# -- the auth pages Chronos serves --------------------------------------------
#
# The auth blueprint is mounted on *both* services, and its templates extend
# "base.html" -- which only Akasha defined. So every auth page Chronos served
# raised TemplateNotFound and 500'd. Logging out of Chronos redirects straight
# to /login, which meant the last thing the app did before handing you back to
# the login screen was fail.


@pytest.mark.parametrize("path", ["/login", "/register"])
def test_the_auth_pages_render_on_chronos_too(client, app, path):
    """A blueprint that ships routes and templates must not depend on a template
    only one of its hosts happens to define."""
    anonymous = app.test_client()
    resp = anonymous.get(path)
    assert resp.status_code == 200, f"{path} did not render"
    assert "<form" in resp.get_data(as_text=True)


@pytest.mark.parametrize("path", ["/login", "/register"])
def test_the_auth_pages_name_the_service_serving_them(client, app, path):
    """One login, two hosts -- so a shared page cannot hard-code either name.
    Reached under Chronos, it should not introduce itself as Akasha."""
    html = app.test_client().get(path).get_data(as_text=True)
    assert "— Chronos</title>" in html, "the Chronos login page names the wrong service"
    assert "Akasha" not in html


def test_logging_out_of_chronos_lands_somewhere_that_works(client, app):
    """The whole round trip, which is how this was found."""
    out = client.post("/logout", data={})
    assert out.status_code in (204, 302)
    if out.status_code == 302:
        landing = client.get(out.headers["Location"])
        assert landing.status_code == 200, "logout redirected to a broken page"


def test_the_change_password_page_renders_on_chronos_too(client):
    assert client.get("/change-password").status_code == 200

