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


def test_graph(seeded, client):
    _build_converging_story(client)
    view = client.get(f"/books/{BOOK}/graph").get_json()
    assert view["convergence"] == ["m"]
    assert view["terminus"] == "t"


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
