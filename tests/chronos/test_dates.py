"""Scheduling a scene by date instead of by tick (design §4.1, the input half).

Writers think in "Year 3, Month 4, Day 12", not ``19704``. The mechanism that
lets them say so is one method on the codec -- ``span``, the inverse of
``components`` -- plus one branch in timeframe validation. Everything after that
still sees ``int``.

Three claims are under test. The inverse is *exact*: ``span(components(t))``
recovers the tick it came from, including the negative ones a pre-epoch
flashback lives on. A partial date names a **period**, so the same date at both
ends of a timeframe covers exactly that period and no more. And a scene written
in dates is indistinguishable, once stored, from the same scene written in
ticks -- which is what keeps every continuity rule ignorant of calendars.
"""

import pytest
from werkzeug.security import generate_password_hash

from tests.chronos.conftest import WRITER, ref
from visualizer.chronos.calendar import (
    EraCodec,
    IdentityCodec,
    MixedRadixCodec,
    codec_for_descriptor,
)
from visualizer.chronos.errors import InvalidTimeframe
from visualizer.chronos.validation import validate_event_payload

BOOK = "ember-pact"

# Hours nesting into days, months and years -- the demo story's calendar, and
# deep enough that partial precision has somewhere to land.
HOURS = {
    "base_unit": "hour",
    "cycles": [
        {"name": "day", "size": 24},
        {"name": "month", "size": 30},
        {"name": "year", "size": 12},
    ],
    "epoch_label": "AF",
}
# One day = 24 ticks, one month = 720, one year = 8640.
DAY, MONTH, YEAR = 24, 720, 8640

LOC = ref("highkeep", "locations")


@pytest.fixture
def codec():
    return codec_for_descriptor(HOURS)


# -- the odometer, run backwards ----------------------------------------------


def test_a_full_date_names_the_tick_it_formats_as(codec):
    assert codec.format(19704) == "Year 3, Month 4, Day 12, 00:00 AF"
    assert codec.span({"year": 3, "month": 4, "day": 12, "hour": 0}) == (19704, 19705)


@pytest.mark.parametrize("tick", [-8641, -720, -1, 0, 1, 240, 19704, 123456])
def test_the_round_trip_is_exact(codec, tick):
    """The property the design has asked for since §4.1. Negative ticks are in
    the list deliberately: the top cycle is open-ended, so a pre-epoch scene
    already prints as Year 0 or below and has to parse back."""
    assert codec.span(codec.components(tick)) == (tick, tick + 1)


def test_year_zero_is_a_real_date_not_an_error(codec):
    """What the odometer prints for the tick before the epoch. Refusing to read
    back a label we are willing to print would strand every flashback."""
    assert codec.components(-1)["year"] == 0
    assert codec.span({"year": 0}) == (-YEAR, 0)


# -- a date names a period ----------------------------------------------------


@pytest.mark.parametrize("date,expected", [
    ({"year": 3}, (2 * YEAR, 3 * YEAR)),
    ({"year": 3, "month": 4}, (2 * YEAR + 3 * MONTH, 2 * YEAR + 4 * MONTH)),
    ({"year": 3, "month": 4, "day": 12}, (19704, 19704 + DAY)),
    ({"year": 3, "month": 4, "day": 12, "hour": 7}, (19711, 19712)),
])
def test_omitting_the_finer_units_widens_the_period(codec, date, expected):
    """Each level of precision dropped makes the date one unit coarser -- and a
    whole year is exactly as legitimate a period as a single hour."""
    assert codec.span(date) == expected


def test_the_same_date_at_both_ends_covers_that_day_and_no_more():
    """The reason ``span`` returns a range at all. "This scene happens on Day
    12" is the commonest thing a writer means, and the half-open convention the
    rest of Chronos already uses spells it without a special case."""
    event = validate_event_payload("scene", {
        "location": LOC.to_dict(),
        "start_date": {"year": 3, "month": 4, "day": 12},
        "end_date": {"year": 3, "month": 4, "day": 12},
    }, codec_for_descriptor(HOURS))
    assert (event.start_tick, event.end_tick) == (19704, 19728)
    assert event.end_tick - event.start_tick == DAY


def test_a_scene_can_span_two_dates(codec):
    event = validate_event_payload("scene", {
        "location": LOC.to_dict(),
        "start_date": {"year": 1, "month": 1, "day": 1},
        "end_date": {"year": 1, "month": 1, "day": 3},
    }, codec)
    assert (event.start_tick, event.end_tick) == (0, 3 * DAY)


def test_reopening_a_scene_as_dates_must_not_grow_it(codec):
    """The rule a form filling its date boxes from a stored scene has to follow.

    ``end_tick`` is exclusive, but a date box says the period the scene *covers*
    -- so the end is filled from the last tick inside the scene. Filling it from
    ``end_tick`` itself resolves one unit later, and a writer who opened a scene
    and saved it untouched would lengthen it by a tick every time.
    """
    start, end = 19704, 19728  # the whole of Year 3, Month 4, Day 12
    assert codec.span(codec.components(start))[0] == start
    assert codec.span(codec.components(end - 1))[1] == end
    # The tempting version, and why it is wrong:
    assert codec.span(codec.components(end))[1] == end + 1


# -- what a date may not say --------------------------------------------------


def test_a_gap_in_the_date_is_refused_rather_than_guessed(codec):
    """A day without its month would need Chronos to pick one."""
    with pytest.raises(InvalidTimeframe, match="largest unit"):
        codec.span({"year": 3, "day": 12})


def test_a_bare_finer_unit_is_refused_for_the_same_reason(codec):
    with pytest.raises(InvalidTimeframe, match="largest unit"):
        codec.span({"day": 12})


def test_an_empty_date_names_nothing(codec):
    with pytest.raises(InvalidTimeframe, match="at least a 'year'"):
        codec.span({})


@pytest.mark.parametrize("date", [
    {"year": 1, "month": 13},
    {"year": 1, "month": 0},
    {"year": 1, "month": 1, "day": 31},
    {"year": 1, "month": 1, "day": 1, "hour": 24},
])
def test_a_digit_outside_its_cycle_is_a_mistake_to_report(codec, date):
    """Day 31 of a 30-day month is a typo. Rolling it forward into the next
    month would schedule the scene somewhere the writer never said."""
    with pytest.raises(InvalidTimeframe, match="must be between"):
        codec.span(date)


def test_a_unit_this_calendar_does_not_keep_is_named_as_such(codec):
    with pytest.raises(InvalidTimeframe, match="no 'week'") as caught:
        codec.span({"year": 1, "week": 2})
    assert caught.value.evidence["expected"] == ["year", "month", "day", "hour"]


@pytest.mark.parametrize("value", [True, 1.5, "3", None])
def test_a_component_must_be_a_whole_number(codec, value):
    with pytest.raises(InvalidTimeframe, match="whole number"):
        codec.span({"year": value})


def test_unit_names_are_matched_case_insensitively(codec):
    assert codec.span({"Year": 3, "MONTH": 4}) == codec.span({"year": 3, "month": 4})


def test_a_calendar_that_names_two_units_alike_has_no_date_vocabulary():
    """Repeated cycle names are legal -- they only read oddly -- but a date is
    keyed by name, so such a book schedules in ticks. It says so rather than
    picking one of the two."""
    muddled = MixedRadixCodec(
        [{"name": "cycle", "size": 10}, {"name": "cycle", "size": 10}], "cycle"
    )
    assert muddled.components(5) is None
    with pytest.raises(InvalidTimeframe, match="more than one unit the same"):
        muddled.span({"cycle": 1})


# -- the two decorations ------------------------------------------------------


def test_a_plain_tick_line_takes_a_date_of_one_component():
    """``IdentityCodec`` is a calendar too, so the protocol stays total."""
    assert IdentityCodec().span({"tick": 5}) == (5, 6)
    assert IdentityCodec().components(5) == {"tick": 5}


def test_an_era_offsets_the_date_by_its_founding(codec):
    """Year 1 of a reckoning founded at tick 1000 *is* tick 1000 -- the same
    offset ``format`` removes on the way out."""
    era = EraCodec(codec, from_tick=1000, until_tick=2000, label="the Founding")
    assert era.span({"year": 1, "month": 1, "day": 1}) == (1000, 1000 + DAY)
    assert era.components(1000) == {"year": 1, "month": 1, "day": 1, "hour": 0}


def test_a_date_the_reckoning_was_not_keeping_is_refused(codec):
    """The write-side twin of "before Elvish Count": inventing a tick from a
    year nobody counted is as dishonest as inventing a label for one."""
    era = EraCodec(codec, from_tick=1000, until_tick=2000, label="the Founding")
    assert era.components(50) is None
    with pytest.raises(InvalidTimeframe, match="outside the Founding"):
        era.span({"year": 5})


def test_a_scene_may_start_inside_an_era_and_run_past_its_end(codec):
    """Only the start has to be covered. The tick line is global; it is the
    labelling that stops, and a scene is free to outlast it."""
    era = EraCodec(codec, from_tick=0, until_tick=100, label="the Founding")
    start, end = era.span({"year": 1, "month": 1, "day": 1})
    assert start == 0 and end > 0


# -- ticks and dates are alternatives, never a mixture ------------------------


def test_ticks_still_work_exactly_as_before(codec):
    event = validate_event_payload("scene", {
        "location": LOC.to_dict(), "start_tick": 0, "end_tick": 10,
    }, codec)
    assert (event.start_tick, event.end_tick) == (0, 10)


def test_giving_both_spellings_at_once_is_refused(codec):
    """Two answers to one question is a client bug; picking a winner hides it."""
    with pytest.raises(InvalidTimeframe, match="not both"):
        validate_event_payload("scene", {
            "location": LOC.to_dict(),
            "start_tick": 0, "end_tick": 10,
            "start_date": {"year": 1}, "end_date": {"year": 1},
        }, codec)


@pytest.mark.parametrize("body", [
    {"start_date": {"year": 1}},
    {"end_date": {"year": 1}},
])
def test_a_half_known_date_is_refused_like_a_half_known_tick(codec, body):
    with pytest.raises(InvalidTimeframe, match="both 'start_date' and 'end_date'"):
        validate_event_payload("scene", {"location": LOC.to_dict(), **body}, codec)


def test_neither_end_is_still_an_unscheduled_scene(codec):
    """Dates change how timing is *said*, not whether it is required."""
    event = validate_event_payload("scene", {"location": LOC.to_dict()}, codec)
    assert not event.is_scheduled


def test_a_backwards_pair_of_dates_is_refused(codec):
    with pytest.raises(InvalidTimeframe, match="must not be after"):
        validate_event_payload("scene", {
            "location": LOC.to_dict(),
            "start_date": {"year": 5}, "end_date": {"year": 2},
        }, codec)


# -- end to end, through the API ----------------------------------------------


@pytest.fixture
def dated_book(client, fake_gate):
    """A book keeping two reckonings, the second founded partway in."""
    fake_gate.add(ref("highkeep", "locations"))
    client.post(f"/calendars/{WRITER}/imperial",
                json={"name": "Imperial Reckoning", "descriptor": HOURS})
    client.post(f"/calendars/{WRITER}/elvish",
                json={"name": "Elvish Count", "descriptor": HOURS})
    client.post(f"/books/{BOOK}", json={
        "title": "The Ember Pact",
        "calendars": [
            {"id": "imperial", "label": "Imperial Reckoning",
             "source": {"owner": WRITER, "calendar": "imperial"}},
            {"id": "elvish", "label": "Elvish Count",
             "source": {"owner": WRITER, "calendar": "elvish"}, "from_tick": YEAR},
        ],
    })
    return client


def _scene(**timing):
    return {"location": LOC.to_dict(), "title": "Dawn at Highkeep", **timing}


def test_a_scene_can_be_written_by_date(dated_book):
    resp = dated_book.post(f"/books/{BOOK}/events/dawn", json=_scene(
        start_date={"year": 3, "month": 4, "day": 12},
        end_date={"year": 3, "month": 4, "day": 12},
    ))
    assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()
    assert (body["start_tick"], body["end_tick"]) == (19704, 19728)
    assert body["start_label"] == "Year 3, Month 4, Day 12, 00:00 AF"


def test_the_stored_scene_is_the_one_ticks_would_have_written(dated_book):
    """The load-bearing claim. Dates are an input spelling; nothing downstream
    can tell which spelling was used, because nothing downstream sees one."""
    dated_book.post(f"/books/{BOOK}/events/by-date", json=_scene(
        start_date={"year": 3, "month": 4, "day": 12},
        end_date={"year": 3, "month": 4, "day": 12},
    ))
    dated_book.post(f"/books/{BOOK}/events/by-tick", json=_scene(
        start_tick=19704, end_tick=19728,
    ))
    both = [dated_book.get(f"/books/{BOOK}/events/{i}").get_json()
            for i in ("by-date", "by-tick")]
    assert both[0]["start_tick"] == both[1]["start_tick"]
    assert both[0]["end_tick"] == both[1]["end_tick"]
    # Nothing was stored to say which way each was written.
    assert not any("date" in key for row in both for key in row)


def test_the_calendar_argument_chooses_which_reckoning_a_date_is_in(dated_book):
    """The same date, written through two calendars whose descriptors match but
    whose eras do not, lands a year apart."""
    for name in ("imperial", "elvish"):
        assert dated_book.post(
            f"/books/{BOOK}/events/{name}-new-year?calendar={name}",
            json=_scene(start_date={"year": 1}, end_date={"year": 1}),
        ).status_code == 201
    ticks = {
        name: dated_book.get(f"/books/{BOOK}/events/{name}-new-year").get_json()["start_tick"]
        for name in ("imperial", "elvish")
    }
    assert ticks == {"imperial": 0, "elvish": YEAR}


def test_a_date_before_a_reckoning_began_is_a_400(dated_book):
    resp = dated_book.post(f"/books/{BOOK}/events/too-early?calendar=elvish",
                           json=_scene(start_date={"year": 0}, end_date={"year": 0}))
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "INVALID_TIMEFRAME"


def test_a_bad_date_names_the_units_the_writer_could_have_used(dated_book):
    resp = dated_book.post(f"/books/{BOOK}/events/nope",
                           json=_scene(start_date={"fortnight": 2}, end_date={"year": 1}))
    assert resp.status_code == 400
    assert resp.get_json()["evidence"]["expected"] == ["year", "month", "day", "hour"]


def test_a_scene_can_be_retimed_by_date(dated_book):
    created = dated_book.post(f"/books/{BOOK}/events/dawn",
                              json=_scene(start_tick=0, end_tick=10)).get_json()
    resp = dated_book.put(f"/books/{BOOK}/events/dawn", headers={"If-Match": str(created["rev"])},
                          json=_scene(start_date={"year": 2}, end_date={"year": 2}))
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["start_tick"] == YEAR


# -- the form's live echo ------------------------------------------------------


def test_ui_dates_resolves_a_date_and_dates_it_back(dated_book):
    resp = dated_book.post(f"/books/{BOOK}/ui/dates", json={
        "start_date": {"year": 3, "month": 4, "day": 12},
        "end_date": {"year": 3, "month": 4, "day": 12},
    })
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert (body["start_tick"], body["end_tick"]) == (19704, 19728)
    assert body["ticks"][0]["label"] == "Year 3, Month 4, Day 12, 00:00 AF"
    # Every reckoning the book keeps, so the writer sees both at once.
    assert {r["calendar"] for r in body["ticks"][0]["readings"]} == {"imperial", "elvish"}


def test_ui_dates_refuses_exactly_what_the_save_would_refuse(dated_book):
    """Shared parsing, so the preview cannot be more permissive than the write."""
    resp = dated_book.post(f"/books/{BOOK}/ui/dates", json={"start_date": {"day": 3}})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "INVALID_TIMEFRAME"


def test_ui_dates_accepts_an_unscheduled_timeframe(dated_book):
    """The form asks on every keystroke, including before anything is typed."""
    body = dated_book.post(f"/books/{BOOK}/ui/dates", json={}).get_json()
    assert body == {"start_tick": None, "end_tick": None, "ticks": []}


def test_ui_ticks_returns_the_numbers_a_form_puts_back_in_its_inputs(dated_book):
    """How an existing scene prefills its date fields: the same round trip, in
    the direction the editor needs when it opens."""
    ticks = dated_book.get(f"/books/{BOOK}/ui/ticks?tick=19704").get_json()["ticks"]
    assert ticks[0]["components"] == {"year": 3, "month": 4, "day": 12, "hour": 0}


def test_ui_ticks_offers_no_components_outside_an_era(dated_book):
    ticks = dated_book.get(f"/books/{BOOK}/ui/ticks?tick=40&calendar=elvish").get_json()["ticks"]
    assert ticks[0]["components"] is None
    assert ticks[0]["label"] == "before Elvish Count"


def test_a_book_with_no_calendar_still_answers_in_ticks(client, fake_gate):
    fake_gate.add(ref("highkeep", "locations"))
    client.post("/books/plain", json={"title": "Plain"})
    ticks = client.get("/books/plain/ui/ticks?tick=240").get_json()["ticks"]
    assert ticks[0]["components"] == {"tick": 240}
    resolved = client.post("/books/plain/ui/dates", json={
        "start_date": {"tick": 240}, "end_date": {"tick": 264},
    }).get_json()
    assert (resolved["start_tick"], resolved["end_tick"]) == (240, 265)


def test_ui_dates_needs_only_read_permission(dated_book, app, auth_store):
    """It writes nothing, so a collaborator who may read the book may use the
    form's hint -- even though they could not save what it describes."""
    auth_store.create_user("finn", generate_password_hash("pw"))
    dated_book.put(f"/books/{BOOK}/collaborators/finn", json={"role": "reader"})
    other = app.test_client()
    other.post("/login", json={"username": "finn", "password": "pw"})
    resp = other.post(f"/books/{BOOK}/ui/dates", json={"start_date": {"year": 1},
                                                       "end_date": {"year": 1}})
    assert resp.status_code == 200
