"""The demo seed's data, replayed through the real app.

``docker/seed_demo.py`` is the first thing anyone runs, and the verdict it prints
is quoted in two READMEs -- so the one thing worse than the demo being wrong is
the demo being wrong quietly. It cannot run here (it drives a live stack over
HTTP), but its *data* is plain tables, and those are what break: a goal that
names a scene the book does not have, or a thread naming a goal that was never
created, now fails the write rather than being stored as typed.

So this feeds those tables to the same routes the script posts to and checks the
two claims the docs make: a fresh seed leaves the book **conflicted** with three
findings and no goal faults, and ``--fix`` leaves it **consistent**.
"""

import importlib.util
from pathlib import Path

import pytest

from tests.chronos.conftest import ref

_SEED = Path(__file__).resolve().parents[2] / "docker" / "seed_demo.py"


def _load_seed():
    spec = importlib.util.spec_from_file_location("seed_demo", _SEED)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # importing is side-effect free; main() is guarded
    return module


seed = _load_seed()
BOOK = seed.BOOK


@pytest.fixture
def gated(app, fake_gate):
    """A gate holding every article the demo's scenes reference."""
    for collection, names in (
        ("characters", [*seed.CHARACTERS, "mira-the-cartographer", "elin-the-bellfounder"]),
        ("items", list(seed.ITEMS)),
        ("locations", list(seed.LOCATIONS)),
    ):
        for name in names:
            fake_gate.add(ref(name, collection, seed.DB))
    return app


def _post(client, path, payload):
    resp = client.post(path, json=payload)
    assert resp.status_code < 400, (path, resp.get_json())
    return resp.get_json()


def _put(client, path, payload):
    resp = client.put(path, json=payload)
    assert resp.status_code < 400, (path, resp.get_json())
    return resp.get_json()


def _events(client, specs):
    for spec in specs:
        eid, payload = seed.event_payload(spec)
        _post(client, f"/books/{BOOK}/events/{eid}", payload)


def _goals(client, goals):
    for gid, title, description, depends_on, achieved_at in goals:
        _post(client, f"/books/{BOOK}/goals/{gid}", {
            "title": title, "description": description,
            "depends_on": depends_on, "achieved_at": achieved_at,
        })


def _plotline(client, plotline, write=_post):
    pid, title, goal_ids, events, into = plotline
    body = {"title": title, "goals": goal_ids, "events": events}
    if into:
        body["continues_into"] = into
    return write(client, f"/books/{BOOK}/plotlines/{pid}", body)


@pytest.fixture
def seeded(gated, client):
    """Exactly what ``python docker/seed_demo.py`` builds, in the same order."""
    _post(client, f"/books/{BOOK}", {"title": "The Ember Pact"})
    _events(client, [*seed.EVENTS, seed.SIGHTING_BROKEN])
    _goals(client, seed.GOALS)
    for plotline in [*seed.SOUND_PLOTLINES, seed.WITNESS_BROKEN]:
        _plotline(client, plotline)
    _post(client, f"/books/{BOOK}/terminus/{seed.TERMINUS}", {})
    return client


def _findings(client):
    return client.get(f"/books/{BOOK}/validate").get_json()


def test_the_seed_writes_without_a_single_refusal(seeded):
    """The fixture asserts it call by call; this names why it matters."""
    assert seeded.get(f"/books/{BOOK}/goals").get_json()["goals"]


def test_a_fresh_seed_leaves_the_book_conflicted(seeded):
    report = _findings(seeded)
    assert report["status"] == "conflicted"
    assert len(report["temporal_conflicts"]) == 1
    assert len(report["ordering"]) == 1
    assert not report["convergence"]["ok"]


def test_the_demos_goals_hold_together(seeded):
    """The three faults the demo means to show are all about scenes. Its goals
    are sound, so nothing here adds a fourth -- only notes."""
    faults = [f for f in _findings(seeded)["goals"] if f["severity"] == "conflict"]
    assert faults == []


def test_the_one_goal_with_no_scene_yet_is_reported_as_a_note(seeded):
    notes = {f["goal"]: f for f in _findings(seeded)["goals"] if f["code"] == "GOAL_UNACHIEVED"}
    assert set(notes) == {"who-was-where"}


def test_the_ending_rests_on_the_goals_that_lead_to_it(seeded):
    """The demo exists to be read, and this is the shape it is meant to show:
    one goal resting on two others, all three achieved in an order that holds."""
    charter = seeded.get(f"/books/{BOOK}/goals/charter-sealed").get_json()
    assert [d["id"] for d in charter["dependencies"]] == ["seal-delivered", "traitor-exposed"]
    assert charter["depth"] == 1
    assert charter["status"]["state"] == "achieved"
    assert charter["plotlines"] == [{"id": "trunk", "title": "The Road to the Crown"}]


def test_fix_leaves_the_book_consistent(seeded):
    eid, payload = seed.event_payload(seed.SIGHTING_FIXED)
    _put(seeded, f"/books/{BOOK}/events/{eid}", payload)
    _plotline(seeded, seed.WITNESS_FIXED, write=_put)
    assert _findings(seeded)["status"] == "consistent"


@pytest.mark.parametrize("events,plotline,goals", [
    (seed.MIXED_EVENTS, seed.MIXED_PLOTLINE, seed.MIXED_GOALS),
    (seed.SOLO_EVENTS, seed.SOLO_PLOTLINE, seed.SOLO_GOALS),
    (seed.LONG_SURVEY_EVENTS, seed.LONG_SURVEY_PLOTLINE, seed.LONG_SURVEY_GOALS),
], ids=["mixed", "solo", "periods"])
def test_each_optional_thread_seeds_with_its_goals(seeded, events, plotline, goals):
    _events(seeded, events)
    _goals(seeded, goals)
    _plotline(seeded, plotline)
    # The long survey runs past the terminus by design (a convergence finding),
    # but no thread the script adds may bring a *goal* fault with it.
    faults = [f for f in _findings(seeded)["goals"] if f["severity"] == "conflict"]
    assert faults == []
