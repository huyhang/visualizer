"""Integration tests through the real Flask app (mongomock + fake gate).

Exercises status codes, auth/grant enforcement, ETag/If-Match, and the shape of
the key responses.
"""

import pytest

from tests.chronos.conftest import ref

BOOK = "ember-pact"


@pytest.fixture
def seeded(app, fake_gate):
    for c in ("aldric", "lyra"):
        fake_gate.add(ref(c))
    for loc in ("highkeep", "emberport", "throne-hall"):
        fake_gate.add(ref(loc, "locations"))
    return app


def _event(location="highkeep", start=0, end=10, characters=("aldric",)):
    return {
        "location": ref(location, "locations").to_dict(),
        "start_tick": start,
        "end_tick": end,
        "characters": [ref(c).to_dict() for c in characters],
    }


def _make_book(client, calendar=None):
    body = {"title": "The Ember Pact"}
    if calendar:
        body["calendar"] = calendar
    return client.post(f"/books/{BOOK}", json=body)


# -- basics ------------------------------------------------------------------


def test_health_no_auth(seeded):
    resp = seeded.test_client().get("/health")
    assert resp.status_code == 200 and resp.get_json()["service"] == "chronos"


def test_requires_auth(seeded):
    resp = seeded.test_client().get(f"/books/{BOOK}")
    assert resp.status_code in (302, 401)  # redirect to login or unauthorized


def test_create_and_get_book(seeded, client):
    resp = _make_book(client)
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["status"] == "consistent" and body["rev"] == 1
    assert resp.headers["ETag"] == '"1"'
    got = client.get(f"/books/{BOOK}")
    assert got.status_code == 200 and got.get_json()["title"] == "The Ember Pact"


def test_creating_a_book_is_all_a_new_writer_needs(seeded, client):
    """The whole "+ New book" flow in one assertion: an authenticated writer with
    no grants creates a book and immediately holds write on it -- so the UI can
    offer "+ New plotline" on the very next screen."""
    assert _make_book(client).status_code == 201
    assert client.get(f"/books/{BOOK}").get_json()["permissions"]["write"] is True


def test_creating_a_book_that_exists_is_409_already_exists(seeded, client):
    """The code the new-book form branches on to say "choose another id"."""
    _make_book(client)
    resp = _make_book(client)
    assert resp.status_code == 409 and resp.get_json()["code"] == "ALREADY_EXISTS"


def test_book_created_with_a_calendar_reads_it_back_unchanged(seeded, client):
    calendar = {
        "cycles": [{"name": "day", "size": 24}], "base_unit": "hour", "epoch_label": "AF",
    }
    assert _make_book(client, calendar=calendar).status_code == 201
    assert client.get(f"/books/{BOOK}").get_json()["calendar"] == calendar


@pytest.mark.parametrize("calendar", [
    pytest.param({"cycles": []}, id="no-cycles"),
    pytest.param({"cycles": [{"name": "day", "size": 0}]}, id="cycle-of-no-length"),
    pytest.param({"cycles": [{"name": "day"}]}, id="cycle-without-a-size"),
])
def test_a_calendar_no_codec_could_be_built_from_is_refused_at_the_write(
    seeded, client, calendar,
):
    """Refused up front, not on the next read. Without this the book stores fine
    and every subsequent GET fails with INVALID_TIMEFRAME -- the wrong code, and
    long after the mistake."""
    resp = client.post(f"/books/{BOOK}", json={"title": "x", "calendar": calendar})
    assert resp.status_code == 400 and resp.get_json()["code"] == "INVALID_BOOK"
    # And nothing was written -- the refusal happens before the store is touched.
    assert client.get("/books").get_json()["books"] == []


def test_updating_a_book_replaces_it_whole_rather_than_patching_it(seeded, client):
    """The trap the Edit-book form has to work around.

    ``PUT /books/<book>`` swaps the stored document, so a body carrying only the
    field the writer changed silently erases the two it left out. Nothing about
    the route says so, and the loss is quiet: an un-designated terminus does not
    error, it just stops every convergence verdict from having anything to
    check. Pinned here so the day someone "simplifies" the form's payload, a
    test fails instead of a book."""
    calendar = {"cycles": [{"name": "day", "size": 24}], "base_unit": "hour"}
    _make_book(client, calendar=calendar)
    client.post(f"/books/{BOOK}/events/finale", json=_event())
    client.post(f"/books/{BOOK}/terminus/finale")

    rev = client.get(f"/books/{BOOK}").get_json()["rev"]
    client.put(f"/books/{BOOK}", json={"title": "Renamed"}, headers={"If-Match": str(rev)})

    after = client.get(f"/books/{BOOK}").get_json()
    assert after["title"] == "Renamed"
    assert after["terminus"] is None, "a partial PUT drops the terminus"
    assert after["calendar"] is None, "a partial PUT drops the calendar"


def test_a_rename_that_resends_everything_keeps_the_terminus_and_calendar(seeded, client):
    """...and the shape the form actually sends, which must not lose either."""
    calendar = {"cycles": [{"name": "day", "size": 24}], "base_unit": "hour"}
    _make_book(client, calendar=calendar)
    client.post(f"/books/{BOOK}/events/finale", json=_event())
    client.post(f"/books/{BOOK}/terminus/finale")

    rev = client.get(f"/books/{BOOK}").get_json()["rev"]
    resp = client.put(
        f"/books/{BOOK}",
        json={"title": "Renamed", "calendar": calendar, "terminus": "finale"},
        headers={"If-Match": str(rev)},
    )
    assert resp.status_code == 200

    after = client.get(f"/books/{BOOK}").get_json()
    assert after["title"] == "Renamed"
    assert after["terminus"] == "finale"
    assert after["calendar"] == calendar


def test_swapping_a_books_calendar_relabels_without_moving_a_scene(seeded, client):
    """Why replacing a calendar is safe to offer at all: ticks are canonical and
    the calendar formats output only, so a swap changes labels and nothing else
    -- not the timing, and not the book's verdict."""
    _make_book(client, calendar={"cycles": [{"name": "day", "size": 24}], "base_unit": "hour"})
    client.post(f"/books/{BOOK}/events/meet", json=_event("emberport", 200, 210))
    before = client.get(f"/books/{BOOK}/events/meet").get_json()
    assert before["start_label"] == "Day 9, 08:00"

    rev = client.get(f"/books/{BOOK}").get_json()["rev"]
    client.put(f"/books/{BOOK}", json={
        "title": "The Ember Pact",
        "calendar": {"cycles": [{"name": "watch", "size": 8}], "base_unit": "hour",
                     "epoch_label": "AF"},
    }, headers={"If-Match": str(rev)})

    after = client.get(f"/books/{BOOK}/events/meet").get_json()
    assert after["start_tick"] == before["start_tick"] == 200  # unmoved
    assert after["start_label"] == "Watch 26, 00:00 AF"        # re-read
    assert client.get(f"/books/{BOOK}").get_json()["status"] == "consistent"


def test_updating_a_book_from_a_stale_revision_is_refused(seeded, client):
    """The Edit-book form sends the rev it loaded; a second writer must not win
    silently."""
    _make_book(client)
    stale = client.get(f"/books/{BOOK}").get_json()["rev"]
    client.put(f"/books/{BOOK}", json={"title": "First"}, headers={"If-Match": str(stale)})

    resp = client.put(f"/books/{BOOK}", json={"title": "Second"}, headers={"If-Match": str(stale)})
    assert resp.status_code == 409 and resp.get_json()["code"] == "REVISION_CONFLICT"


def test_a_bad_calendar_is_refused_on_update_too(seeded, client):
    _make_book(client)
    resp = client.put(f"/books/{BOOK}", json={"title": "x", "calendar": {"cycles": []}})
    assert resp.status_code == 400 and resp.get_json()["code"] == "INVALID_BOOK"


def test_calendar_labels_on_event(seeded, client):
    _make_book(client, calendar={
        "cycles": [{"name": "day", "size": 24}, {"name": "month", "size": 30},
                   {"name": "year", "size": 12}],
        "base_unit": "hour", "epoch_label": "AF",
    })
    resp = client.post(f"/books/{BOOK}/events/meet", json=_event("emberport", 200, 210))
    assert resp.status_code == 201
    assert resp.get_json()["start_label"] == "Year 1, Month 1, Day 9, 08:00 AF"


# -- invariants over HTTP ----------------------------------------------------


def test_missing_entity_is_422(seeded, client):
    _make_book(client)
    resp = client.post(f"/books/{BOOK}/events/e1", json=_event(characters=("ghost",)))
    assert resp.status_code == 422
    assert resp.get_json()["code"] == "ENTITY_NOT_FOUND"


def test_bad_timeframe_is_400(seeded, client):
    _make_book(client)
    resp = client.post(f"/books/{BOOK}/events/e1", json=_event(start=10, end=5))
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "INVALID_TIMEFRAME"


def test_temporal_conflict_write_succeeds_but_status_conflicted(seeded, client):
    _make_book(client)
    assert client.post(f"/books/{BOOK}/events/e1",
                       json=_event("highkeep", 0, 24)).status_code == 201
    # different location, overlapping, same character -> conflict, but 201
    assert client.post(f"/books/{BOOK}/events/e2",
                       json=_event("emberport", 10, 30)).status_code == 201
    report = client.get(f"/books/{BOOK}/validate").get_json()
    assert report["status"] == "conflicted"
    assert report["temporal_conflicts"][0]["code"] == "TEMPORAL_CONFLICT"


def test_occ_if_match(seeded, client):
    _make_book(client)
    stale = client.put(f"/books/{BOOK}", json={"title": "x"}, headers={"If-Match": '"99"'})
    assert stale.status_code == 409 and stale.get_json()["code"] == "REVISION_CONFLICT"
    ok = client.put(f"/books/{BOOK}", json={"title": "x"}, headers={"If-Match": '"1"'})
    assert ok.status_code == 200 and ok.get_json()["rev"] == 2


# -- plotlines, graph, neighborhood ------------------------------------------


def _build_converging_story(client):
    _make_book(client)
    for eid, s, e in [("a", 0, 10), ("b", 0, 10), ("m", 20, 30), ("t", 40, 50)]:
        client.post(f"/books/{BOOK}/events/{eid}", json=_event("highkeep", s, e))
    client.post(f"/books/{BOOK}/plotlines/knights",
                json={"events": ["a", "m", "t"], "goals": ["g"]})
    client.post(f"/books/{BOOK}/plotlines/spies",
                json={"events": ["b", "m", "t"], "goals": ["g"]})
    client.post(f"/books/{BOOK}/terminus/t")


def test_full_story_is_consistent(seeded, client):
    _build_converging_story(client)
    assert client.get(f"/books/{BOOK}/validate").get_json()["status"] == "consistent"


def test_plotline_expand(seeded, client):
    _build_converging_story(client)
    resp = client.get(f"/books/{BOOK}/plotlines/knights?expand=events")
    body = resp.get_json()
    assert body["kind"] == "plotline"
    m = next(e for e in body["effective_events"] if e["id"] == "m")
    assert m["is_convergence"] and m["shared_with"] == ["spies"]


def test_expanded_summary_carries_structured_label_parts(seeded, client):
    _make_book(client, calendar={
        "cycles": [{"name": "day", "size": 24}, {"name": "month", "size": 30},
                   {"name": "year", "size": 12}],
        "base_unit": "hour", "epoch_label": "AF",
    })
    client.post(f"/books/{BOOK}/events/meet", json=_event("emberport", 200, 210))
    client.post(f"/books/{BOOK}/events/soon", json={"location": ref("emberport", "locations").to_dict()})
    client.post(f"/books/{BOOK}/plotlines/pl", json={"events": ["meet", "soon"], "goals": ["g"]})
    events = {e["id"]: e for e in
              client.get(f"/books/{BOOK}/plotlines/pl?expand=events").get_json()["effective_events"]}
    # Scheduled event: coarse-to-fine components straight from the codec.
    assert events["meet"]["start_parts"] == ["Year 1", "Month 1", "Day 9", "08:00 AF"]
    assert events["meet"]["end_parts"][:3] == ["Year 1", "Month 1", "Day 9"]
    # Unscheduled event: null parts.
    assert events["soon"]["start_parts"] is None and events["soon"]["end_parts"] is None


def test_graph(seeded, client):
    _build_converging_story(client)
    view = client.get(f"/books/{BOOK}/graph").get_json()
    assert view["convergence"] == ["m"]
    assert view["terminus"] == "t"


def test_graph_nodes_carry_timing_and_role_for_layout(seeded, client):
    # The connected-plots / story-map viewer lays out by tick and colours by role
    # from a single /graph call -- so every node carries its timing + flags.
    _build_converging_story(client)
    nodes = {n["id"]: n for n in client.get(f"/books/{BOOK}/graph").get_json()["nodes"]}
    assert nodes["m"]["start_tick"] == 20 and nodes["m"]["scheduled"]
    assert nodes["m"]["is_convergence"] and not nodes["m"]["is_divergence"]
    assert nodes["t"]["is_terminus"] and not nodes["a"]["is_terminus"]
    # Codec-split parts, so the view groups by period exactly like the timeline.
    assert nodes["m"]["start_parts"] == ["20"] and nodes["m"]["end_parts"] == ["30"]


def test_graph_lanes_record_stored_and_resolved_paths(seeded, client):
    # One lane per thread, with stored-vs-inherited provenance kept recoverable so
    # a future editor can route an edit back to the right stored field.
    _make_book(client)
    for eid, s, e in [("a", 0, 10), ("m", 20, 30), ("t", 40, 50)]:
        client.post(f"/books/{BOOK}/events/{eid}", json=_event("highkeep", s, e))
    client.post(f"/books/{BOOK}/plotlines/trunk", json={"events": ["m", "t"], "goals": ["g"]})
    client.post(f"/books/{BOOK}/plotlines/knights",
                json={"title": "The Knight's Road", "events": ["a"], "goals": ["g"],
                      "continues_into": "trunk"})
    client.post(f"/books/{BOOK}/terminus/t")
    lanes = {p["id"]: p for p in client.get(f"/books/{BOOK}/graph").get_json()["plotlines"]}
    assert lanes["knights"]["title"] == "The Knight's Road"
    assert lanes["knights"]["events"] == ["a"]                 # stored own segment
    assert lanes["knights"]["continues_into"] == "trunk"
    assert lanes["knights"]["effective_events"] == ["a", "m", "t"]  # resolved path


def test_expanded_summary_marks_divergence(seeded, client):
    # A thread splitting off is now visible in the single-plotline timeline.
    _make_book(client)
    for eid, s, e in [("start", 0, 10), ("x", 20, 30), ("y", 20, 30), ("t", 40, 50)]:
        client.post(f"/books/{BOOK}/events/{eid}", json=_event("highkeep", s, e))
    client.post(f"/books/{BOOK}/plotlines/one", json={"events": ["start", "x", "t"], "goals": ["g"]})
    client.post(f"/books/{BOOK}/plotlines/two", json={"events": ["start", "y", "t"], "goals": ["g"]})
    client.post(f"/books/{BOOK}/terminus/t")
    body = client.get(f"/books/{BOOK}/plotlines/one?expand=events").get_json()
    start = next(e for e in body["effective_events"] if e["id"] == "start")
    assert start["is_divergence"] and not start["is_convergence"]


def test_neighborhood(seeded, client):
    _build_converging_story(client)
    n = client.get(f"/books/{BOOK}/events/m/plotlines").get_json()
    assert n["role"] == "convergence"
    assert {g["from"]["id"] for g in n["converging"]["incoming"]} == {"a", "b"}
    filtered = client.get(f"/books/{BOOK}/events/m/plotlines?relation=diverging").get_json()
    assert "diverging" in filtered and "converging" not in filtered


# -- deletion + authorization ------------------------------------------------


def test_delete_referenced_event_409(seeded, client):
    _build_converging_story(client)
    resp = client.delete(f"/books/{BOOK}/events/a")
    assert resp.status_code == 409 and resp.get_json()["code"] == "EVENT_IN_USE"
    detached = client.delete(f"/books/{BOOK}/events/a?detach=true")
    assert detached.status_code == 204


def test_delete_terminus_409(seeded, client):
    _build_converging_story(client)
    resp = client.delete(f"/books/{BOOK}/events/t?detach=true")
    assert resp.status_code == 409 and resp.get_json()["code"] == "TERMINUS_IN_USE"


def test_non_collaborator_cannot_read(seeded, client, admin_client):
    # 'client' (mara) owns the book; a different plain user must be forbidden.
    _make_book(client)
    app = seeded
    app.auth_store = None
    other = app.test_client()
    other.post("/register", json={"username": "outsider", "password": "correct-horse-battery",
                                  "email": "o@example.com"})
    assert other.post("/login", json={"username": "outsider", "password": "correct-horse-battery"}).status_code == 200
    assert other.get(f"/books/{BOOK}").status_code == 403


def test_collaborator_can_read_after_invite(seeded, client):
    _make_book(client)
    app = seeded
    other = app.test_client()
    other.post("/register", json={"username": "finn", "password": "correct-horse-battery", "email": "f@example.com"})
    other.post("/login", json={"username": "finn", "password": "correct-horse-battery"})
    assert other.get(f"/books/{BOOK}").status_code == 403
    # owner invites finn as editor
    assert client.put(f"/books/{BOOK}/collaborators/finn",
                      json={"role": "editor"}).status_code == 200
    assert other.get(f"/books/{BOOK}").status_code == 200
