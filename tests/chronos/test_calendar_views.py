"""Reading one book through several parallel calendars.

The claim under test is narrow and absolute: choosing a reckoning changes
**labels and nothing else**. Same ticks, same ordering, same conflicts, same
verdict. If any of that moved, parallel calendars would be parallel timelines,
and every continuity check in Chronos would have to learn about them.
"""

import pytest

from tests.chronos.conftest import WRITER, ref

HOURS = {
    "base_unit": "hour",
    "cycles": [{"name": "day", "size": 24}, {"name": "month", "size": 30}],
    "epoch_label": "AF",
}
BELLS = {"base_unit": "bell", "cycles": [{"name": "moon", "size": 10}], "epoch_label": "SR"}

BOOK = "ember-pact"


@pytest.fixture
def two_calendars(client, fake_gate):
    """A book keeping two reckonings, the second of which ends mid-story.

    Both come from the library, because that is now the only way a book can get
    a calendar: it names one, and the server copies the descriptor in. The era
    stays on the *attachment* -- when a culture kept its calendar is a fact
    about this story, not about the calendar.
    """
    fake_gate.add(ref("highkeep", "locations"))
    client.post(f"/calendars/{WRITER}/imperial",
                json={"name": "Imperial Reckoning", "descriptor": HOURS})
    client.post(f"/calendars/{WRITER}/elvish",
                json={"name": "Elvish Count", "descriptor": BELLS})
    client.post(f"/books/{BOOK}", json={
        "title": "The Ember Pact",
        "calendars": [
            {"id": "imperial", "label": "Imperial Reckoning",
             "source": {"owner": WRITER, "calendar": "imperial"}},
            {"id": "elvish", "label": "Elvish Count",
             "source": {"owner": WRITER, "calendar": "elvish"},
             "from_tick": 100, "until_tick": 300},
        ],
    })
    client.post(f"/books/{BOOK}/events/dawn", json={
        "location": {"database": "ember-pact", "collection": "locations", "id": "highkeep"},
        "start_tick": 120, "end_tick": 140, "title": "Dawn at Highkeep",
    })
    return client


def _event(client, calendar=None):
    q = f"?calendar={calendar}" if calendar else ""
    return client.get(f"/books/{BOOK}/events/dawn{q}").get_json()


# -- the same tick, two readings ----------------------------------------------


def test_a_scene_reads_differently_through_each_calendar(two_calendars):
    imperial = _event(two_calendars, "imperial")
    elvish = _event(two_calendars, "elvish")
    assert imperial["start_label"] != elvish["start_label"]
    # ...but the tick itself has not moved an inch.
    assert imperial["start_tick"] == elvish["start_tick"] == 120


def test_no_calendar_named_means_the_first_one(two_calendars):
    assert _event(two_calendars)["start_label"] == _event(two_calendars, "imperial")["start_label"]


def test_an_unattached_calendar_is_a_404_not_a_silent_fallback(two_calendars):
    resp = two_calendars.get(f"/books/{BOOK}/events/dawn?calendar=dwarvish")
    assert resp.status_code == 404
    assert resp.get_json()["code"] == "CALENDAR_NOT_FOUND"


def test_the_choice_is_refused_on_every_book_scoped_read(two_calendars):
    """So a stale bookmark fails the same way everywhere, rather than only on
    the pages that happen to format a tick."""
    assert two_calendars.get(f"/books/{BOOK}/plotlines?calendar=nope").status_code == 404
    assert two_calendars.get(f"/books/{BOOK}/ui/plotlines?calendar=nope").status_code == 404


@pytest.mark.parametrize("path", [
    "/books/{b}/validate",
    "/books/{b}/graph",
    "/books/{b}/events",
    "/books/{b}/events/dawn",
    "/books/{b}/ui/plotlines",
    "/books/{b}/ui/ticks?tick=120&",
])
def test_every_read_that_formats_a_tick_accepts_the_choice(two_calendars, path):
    url = path.format(b=BOOK)
    joiner = "" if url.endswith("&") else "?"
    assert two_calendars.get(f"{url}{joiner}calendar=elvish").status_code == 200


# -- a calendar that had not started, and one that ended ----------------------


def test_a_scene_outside_the_era_is_not_given_an_invented_date(two_calendars):
    """The destroyed-culture case. Nobody was keeping the Elvish Count at tick
    40, so it does not get to claim a date there."""
    two_calendars.post(f"/books/{BOOK}/events/prologue", json={
        "location": {"database": "ember-pact", "collection": "locations", "id": "highkeep"},
        "start_tick": 40, "end_tick": 50, "title": "Long before",
    })
    early = two_calendars.get(f"/books/{BOOK}/events/prologue?calendar=elvish").get_json()
    assert early["start_label"] == "before Elvish Count"
    # The Imperial reckoning, which spans everything, still dates it.
    imperial = two_calendars.get(f"/books/{BOOK}/events/prologue?calendar=imperial").get_json()
    assert imperial["start_label"] == "Month 1, Day 2, 16:00 AF"


def test_a_span_entirely_outside_the_era_reads_once_not_twice(two_calendars):
    """Both ends of the span land on the same marker, and "before X → before X"
    tells the writer nothing except that something is wrong with the renderer."""
    two_calendars.post(f"/books/{BOOK}/events/prologue", json={
        "location": {"database": "ember-pact", "collection": "locations", "id": "highkeep"},
        "start_tick": 10, "end_tick": 20, "title": "Long before",
    })
    rows = two_calendars.get(f"/books/{BOOK}/events?calendar=elvish").get_json()["events"]
    prologue = next(r for r in rows if r["id"] == "prologue")
    assert prologue["when"] == "before Elvish Count"


def test_an_era_counts_from_its_own_founding(two_calendars):
    """Tick 120 is 20 bells into a count that began at 100 -- Moon 3, not Moon 13."""
    assert _event(two_calendars, "elvish")["start_label"] == "Moon 3, 00:00 SR"


# -- goals read through the same reckoning ------------------------------------


def _with_a_goal(client):
    client.post(f"/books/{BOOK}/goals/crown",
                json={"title": "Aldric is crowned", "achieved_at": "dawn"})
    client.post(f"/books/{BOOK}/plotlines/road",
                json={"events": ["dawn"], "goals": ["crown"]})
    return client


def test_a_goal_is_dated_through_the_chosen_calendar(two_calendars):
    """A goal has no date of its own -- it borrows the one belonging to the
    scene that delivers it, which means it changes with the reckoning like
    everything else on the page."""
    book = _with_a_goal(two_calendars)
    imperial = book.get(f"/books/{BOOK}/goals/crown?calendar=imperial").get_json()
    elvish = book.get(f"/books/{BOOK}/goals/crown?calendar=elvish").get_json()
    assert imperial["achieved_scene"]["when"] == "Month 1, Day 6, 00:00 AF → Month 1, Day 6, 20:00 AF"
    assert elvish["achieved_scene"]["when"] == "Moon 3, 00:00 SR → Moon 5, 00:00 SR"
    # Same scene, same ticks: only the reading moved.
    assert imperial["achieved_at"] == elvish["achieved_at"] == "dawn"


@pytest.mark.parametrize("path", [
    "/books/{b}/goals",
    "/books/{b}/goals/crown",
    "/books/{b}/plotlines/road",
    "/books/{b}/graph",
    "/books/{b}/ui/plotlines",
])
def test_every_surface_that_draws_a_goal_chip_dates_it_the_same_way(two_calendars, path):
    """The chip is drawn in five places. A date that differed between two of
    them would be the writer's problem to reconcile, so none of them formats
    anything itself -- they all read the one ``when`` the codec produced."""
    book = _with_a_goal(two_calendars)
    body = book.get(f"{path.format(b=BOOK)}?calendar=elvish").get_json()
    whens = {
        scene["when"]
        for scene in _scenes_under(body)
        if scene is not None
    }
    assert whens == {"Moon 3, 00:00 SR → Moon 5, 00:00 SR"}


def _scenes_under(body):
    """Every ``achieved_scene`` anywhere in a response, however it is nested."""
    if isinstance(body, dict):
        if "achieved_scene" in body:
            yield body["achieved_scene"]
        for value in body.values():
            yield from _scenes_under(value)
    elif isinstance(body, list):
        for item in body:
            yield from _scenes_under(item)


# -- what must not change -----------------------------------------------------


def test_the_verdict_is_the_same_whichever_calendar_is_chosen(two_calendars):
    """The load-bearing invariant. Ticks are canonical, so every continuity rule
    runs on integers and cannot see the choice at all."""
    plain = two_calendars.get(f"/books/{BOOK}/validate").get_json()
    elvish = two_calendars.get(f"/books/{BOOK}/validate?calendar=elvish").get_json()
    assert plain["status"] == elvish["status"]
    assert len(plain["temporal_conflicts"]) == len(elvish["temporal_conflicts"])
    assert plain["unscheduled"] == elvish["unscheduled"]


def test_scene_order_does_not_depend_on_the_calendar(two_calendars):
    two_calendars.post(f"/books/{BOOK}/events/later", json={
        "location": {"database": "ember-pact", "collection": "locations", "id": "highkeep"},
        "start_tick": 400, "end_tick": 410, "title": "After the fall",
    })
    def ids(calendar):
        rows = two_calendars.get(f"/books/{BOOK}/events?calendar={calendar}").get_json()
        return [r["id"] for r in rows["events"]]
    assert ids("imperial") == ids("elvish")


# -- the book response carries the switcher's data ----------------------------


def test_the_book_lists_its_calendars_with_the_primary_marked(two_calendars):
    book = two_calendars.get(f"/books/{BOOK}").get_json()
    assert [c["id"] for c in book["calendars"]] == ["imperial", "elvish"]
    assert [c["primary"] for c in book["calendars"]] == [True, False]
    assert book["calendars"][1]["until_tick"] == 300
    # The descriptor rides along, so the switcher needs no second request.
    assert book["calendars"][0]["descriptor"] == HOURS


def test_the_legacy_single_calendar_field_still_answers(two_calendars):
    """A pre-library client asking for "the" calendar gets the primary one."""
    assert two_calendars.get(f"/books/{BOOK}").get_json()["calendar"] == HOURS


def test_a_book_written_the_old_way_still_reads(client):
    """No migration runs, so the old spelling has to keep working on the way in
    as well as on the way out."""
    client.post("/books/old", json={"title": "Old", "calendar": HOURS})
    book = client.get("/books/old").get_json()
    assert book["calendar"] == HOURS
    assert [c["id"] for c in book["calendars"]] == ["default"]


# -- the scene form's live hint -----------------------------------------------


def test_ticks_are_dated_in_every_reckoning_at_once(two_calendars):
    """What a writer sees while typing a timeframe: one tick, every calendar's
    reading of it, including the ones that were not being kept then."""
    ticks = two_calendars.get(f"/books/{BOOK}/ui/ticks?tick=40").get_json()["ticks"]
    readings = {r["calendar"]: r["label"] for r in ticks[0]["readings"]}
    assert readings["imperial"] == "Month 1, Day 2, 16:00 AF"
    assert readings["elvish"] == "before Elvish Count"


def test_the_single_label_a_pre_library_client_reads_is_unchanged(two_calendars):
    ticks = two_calendars.get(f"/books/{BOOK}/ui/ticks?tick=120").get_json()["ticks"]
    assert ticks[0]["label"] == "Month 1, Day 6, 00:00 AF"
    assert ticks[0]["parts"][0] == "Month 1"
