"""Earth dates as one more reading of the same tick line.

The pure half checks the two things a Gregorian calendar does that no fixed-cycle
calendar can -- variable month lengths, and years running back past 1 -- plus the
one thing it must *not* do, which is let an era move where it starts.

The API half checks that a writer can get at all of it, and that a book carrying
a broken alignment is refused at the save rather than stored and then unreadable.
"""

import pytest

from tests.chronos.conftest import WRITER, ref
from visualizer.chronos.calendar import (
    GregorianCodec,
    MixedRadixCodec,
    codec_for_attachment,
)
from visualizer.chronos.errors import InvalidTimeframe
from visualizer.chronos.models import CalendarAttachment

EARTH_DAYS = {"kind": "gregorian", "tick_unit": "day"}
EARTH_HOURS = {"kind": "gregorian", "tick_unit": "hour"}
LOCATION = ref("highkeep", "locations")


# -- what only a Gregorian calendar does ---------------------------------------


@pytest.mark.parametrize("year,month,days", [
    (2024, 2, 29),   # leap
    (2023, 2, 28),
    (2000, 2, 29),   # the century exception's exception
    (1900, 2, 28),
    (2024, 4, 30),
    (2024, 7, 31),
])
def test_a_month_is_as_long_as_that_month_actually_is(year, month, days):
    codec = GregorianCodec("2024-01-01", "day")
    start, end = codec.span({"year": year, "month": month})
    assert end - start == days


@pytest.mark.parametrize("year,days", [(2024, 366), (2023, 365), (1900, 365), (2000, 366)])
def test_a_year_is_as_long_as_that_year_actually_is(year, days):
    codec = GregorianCodec("2024-01-01", "day")
    start, end = codec.span({"year": year})
    assert end - start == days


def test_a_period_is_measured_in_ticks_however_fine_they_are():
    """February is 29 days whatever a tick is; only the count of them changes."""
    for unit, origin, per_day in [
        ("day", "2024-01-01", 1),
        ("hour", "2024-01-01T00:00Z", 24),
        ("minute", "2024-01-01T00:00Z", 1440),
    ]:
        codec = GregorianCodec(origin, unit)
        start, end = codec.span({"year": 2024, "month": 2})
        assert end - start == 29 * per_day, unit


def test_the_day_a_date_may_reach_depends_on_its_own_month():
    codec = GregorianCodec("2024-01-01", "day")

    assert codec.span({"year": 2024, "month": 2, "day": 29}) == (59, 60)
    with pytest.raises(InvalidTimeframe, match="between 1 and 28"):
        codec.span({"year": 2023, "month": 2, "day": 29})
    with pytest.raises(InvalidTimeframe, match="between 1 and 30"):
        codec.span({"year": 2024, "month": 4, "day": 31})


@pytest.mark.parametrize("unit,origin", [
    ("day", "2024-02-27"),
    ("hour", "2024-02-27T06:00-08:00"),
    ("minute", "0001-01-01T00:00+05:30"),
])
@pytest.mark.parametrize("tick", [-100_000, -1, 0, 1, 1_000, 100_000])
def test_a_tick_read_as_a_date_and_written_back_is_the_same_tick(unit, origin, tick):
    codec = GregorianCodec(origin, unit)
    assert codec.span(codec.components(tick)) == (tick, tick + 1)


def test_years_before_1_read_as_a_historian_writes_them():
    codec = GregorianCodec("0001-01-01", "day")

    ides = codec.span({"year": -43, "month": 3, "day": 15})[0]
    assert codec.format(ides) == "March 15, 44 BCE"
    assert codec.parts(ides) == ["44 BCE", "March", "Day 15"]
    # The components stay the plain integers every other calendar sends; the
    # BCE spelling is a label, not a second way of writing a date.
    assert codec.components(ides) == {"year": -43, "month": 3, "day": 15}
    year_zero = codec.span({"year": 0, "month": 1, "day": 1})[0]
    assert codec.format(year_zero) == "January 1, 1 BCE"


def test_a_year_before_1_still_leaps_on_the_gregorian_rule():
    codec = GregorianCodec("0001-01-01", "day")
    start, end = codec.span({"year": -4, "month": 2})  # 5 BCE, divisible by 4
    assert end - start == 29


def test_labels_carry_the_time_and_its_offset_only_when_ticks_are_finer_than_a_day():
    day = GregorianCodec("2024-02-27", "day")
    hour = GregorianCodec("2024-02-27T00:00-08:00", "hour")

    assert day.format(2) == "February 29, 2024"
    assert day.parts(2) == ["2024", "February", "Day 29"]
    assert hour.format(14) == "February 27, 2024, 14:00 UTC-08:00"
    assert hour.parts(14) == ["2024", "February", "Day 27", "14:00 UTC-08:00"]


def test_a_fixed_offset_labels_the_clock_without_moving_the_date():
    """Being constant, the offset cancels out of every conversion. It says which
    wall clock these dates are told by, and nothing else."""
    utc = GregorianCodec("2024-02-27T00:00Z", "hour")
    pacific = GregorianCodec("2024-02-27T00:00-08:00", "hour")

    assert utc.components(30) == pacific.components(30)
    assert utc.format(30).endswith("UTC")
    assert pacific.format(30).endswith("UTC-08:00")


# -- the origin ----------------------------------------------------------------


def test_a_day_counting_calendar_takes_a_date_and_nothing_finer():
    assert GregorianCodec("2024-02-27", "day").format(0) == "February 27, 2024"
    with pytest.raises(InvalidTimeframe, match="no time of day"):
        GregorianCodec("2024-02-27T00:00Z", "day")


def test_a_finer_calendar_needs_a_time_and_a_fixed_offset():
    for unit in ("hour", "minute"):
        with pytest.raises(InvalidTimeframe, match="needs a time"):
            GregorianCodec("2024-02-27", unit)


def test_an_origin_must_begin_on_a_whole_tick():
    with pytest.raises(InvalidTimeframe, match="whole hours"):
        GregorianCodec("2024-02-27T06:30Z", "hour")
    with pytest.raises(InvalidTimeframe, match="whole minutes"):
        GregorianCodec("2024-02-27T06:30:15Z", "minute")


@pytest.mark.parametrize("origin,complaint", [
    (None, "needs an 'origin'"),
    ("", "needs an 'origin'"),
    ("last tuesday", "not a date this calendar can start from"),
    ("2024-02-30", "no real date"),
    ("2024-13-01", "no real date"),
    ("2023-02-29", "no real date"),
])
def test_an_origin_that_names_no_moment_is_refused(origin, complaint):
    with pytest.raises(InvalidTimeframe, match=complaint):
        GregorianCodec(origin, "day")


def test_an_origin_may_reach_back_before_year_1():
    codec = GregorianCodec("-0043-03-15", "day")
    assert codec.format(0) == "March 15, 44 BCE"


@pytest.mark.parametrize("offset,shown", [
    ("Z", "UTC"), ("+00:00", "UTC"), ("-08:00", "UTC-08:00"), ("+05:30", "UTC+05:30"),
])
def test_a_fixed_offset_reads_the_way_it_was_written(offset, shown):
    codec = GregorianCodec(f"2024-02-27T00:00{offset}", "hour")
    assert codec.format(0).endswith(shown)


def test_a_tick_unit_the_calendar_does_not_keep_is_refused():
    with pytest.raises(InvalidTimeframe, match="day, an hour or a minute"):
        GregorianCodec("2024-02-27", "week")


# -- the seam every calendar shares --------------------------------------------


def test_a_gap_in_a_date_is_refused_in_the_same_words_whatever_the_calendar():
    """``read_components`` is shared so a writer moving between their invented
    calendar and Earth is corrected the same way, not in two dialects."""
    fantasy = MixedRadixCodec(
        [{"name": "day", "size": 24}, {"name": "month", "size": 30}], base_unit="hour"
    )
    earth = GregorianCodec("2024-01-01", "day")

    with pytest.raises(InvalidTimeframe) as fantasy_said:
        fantasy.span({"month": 3, "hour": 4})
    with pytest.raises(InvalidTimeframe) as earth_said:
        earth.span({"year": 2024, "day": 12})

    for said in (fantasy_said, earth_said):
        assert "start from the largest unit and leave no gaps" in said.value.message
    assert earth_said.value.evidence["missing"] == ["month"]


@pytest.mark.parametrize("date,complaint", [
    ({"year": 2024, "month": 13}, "'month' must be between 1 and 12"),
    ({"year": 2024, "month": 2, "day": 0}, "'day' must be between 1 and 29"),
    ({"year": 2024, "month": 2, "day": 1, "hour": 24}, "'hour' must be between 0 and 23"),
    ({"month": 2}, "start from the largest unit"),
    ({"year": 2024, "week": 3}, "no 'week'"),
    ({"year": True}, "must be a whole number"),
])
def test_a_date_outside_the_calendar_is_reported_not_rolled_forward(date, complaint):
    with pytest.raises(InvalidTimeframe, match=complaint):
        GregorianCodec("2024-02-27T00:00Z", "hour").span(date)


# -- eras ----------------------------------------------------------------------


def _attached(**kwargs):
    return codec_for_attachment(CalendarAttachment(
        id="earth", label="Earth", descriptor=EARTH_DAYS, origin="2024-02-27", **kwargs
    ))


def test_an_era_hides_the_ticks_outside_it():
    codec = _attached(from_tick=10, until_tick=20)
    assert codec.format(9) == "before Earth"
    assert codec.format(20) == "after Earth"


def test_an_era_does_not_move_where_earth_starts():
    """``from_tick`` fixes a *fictional* calendar's year 1, because nothing else
    could. Earth already knows, and shifting it would silently re-date every
    scene against the alignment the writer stated."""
    bounded = _attached(from_tick=10, until_tick=90)
    unbounded = _attached()

    for tick in (10, 42, 89):
        assert bounded.format(tick) == unbounded.format(tick)
    assert bounded.format(10) == "March 8, 2024"
    assert bounded.span(bounded.components(42)) == (42, 43)


def test_an_era_still_moves_an_invented_calendar_to_its_own_year_one():
    attachment = CalendarAttachment(
        id="elvish", label="Elvish Count", from_tick=100,
        descriptor={"base_unit": "day", "cycles": [{"name": "month", "size": 30}]},
    )
    assert codec_for_attachment(attachment).format(100).startswith("Month 1")


# -- through the API -----------------------------------------------------------


def _library(client, calendar_id, descriptor, name="Earth"):
    return client.post(
        f"/calendars/{WRITER}/{calendar_id}", json={"name": name, "descriptor": descriptor}
    )


@pytest.fixture
def earth_book(client, fake_gate):
    """A book reading one tick line through both an invented calendar and Earth."""
    fake_gate.add(LOCATION)
    assert _library(client, "earth", EARTH_HOURS).status_code == 201
    assert _library(client, "imperial", {
        "base_unit": "hour", "cycles": [{"name": "day", "size": 24}],
    }, name="Imperial").status_code == 201
    made = client.post("/books/two-worlds", json={
        "title": "Two Worlds",
        "calendars": [
            {"id": "imperial", "label": "Imperial",
             "source": {"owner": WRITER, "calendar": "imperial"}},
            {"id": "earth", "label": "Earth",
             "source": {"owner": WRITER, "calendar": "earth"},
             "origin": "2024-02-27T00:00Z"},
        ],
    })
    assert made.status_code == 201, made.get_json()
    return client


def test_a_writer_can_keep_a_reusable_earth_calendar_in_the_library(client):
    made = _library(client, "earth", EARTH_DAYS)
    assert made.status_code == 201
    assert made.get_json()["descriptor"] == EARTH_DAYS


@pytest.mark.parametrize("descriptor,complaint", [
    ({"kind": "gregorian"}, "'tick_unit'"),
    ({"kind": "gregorian", "tick_unit": "week"}, "'tick_unit'"),
    ({**EARTH_DAYS, "cycles": [{"name": "month", "size": 30}]}, "no fixed cycles"),
    ({**EARTH_DAYS, "base_unit": "hour"}, "no fixed cycles"),
    ({**EARTH_DAYS, "origin": "2024-02-27"}, "belongs to each book"),
])
def test_a_library_calendar_cannot_say_what_only_a_book_can(client, descriptor, complaint):
    refused = _library(client, "earth", descriptor)
    assert refused.status_code == 400
    assert refused.get_json()["code"] == "INVALID_CALENDAR"
    assert complaint in refused.get_json()["error"]


def test_a_scene_written_as_an_earth_date_is_stored_as_plain_ticks(earth_book):
    made = earth_book.post("/books/two-worlds/events/leap-day?calendar=earth", json={
        "title": "Leap Day",
        "location": LOCATION.to_dict(),
        "start_date": {"year": 2024, "month": 2, "day": 29},
        "end_date": {"year": 2024, "month": 2, "day": 29},
    })
    assert made.status_code == 201, made.get_json()
    scene = made.get_json()
    assert (scene["start_tick"], scene["end_tick"]) == (48, 72)
    assert scene["start_label"] == "February 29, 2024, 00:00 UTC"


def test_the_same_scene_reads_two_ways_and_moves_neither(earth_book):
    earth_book.post("/books/two-worlds/events/meeting", json={
        "location": LOCATION.to_dict(), "start_tick": 48, "end_tick": 72,
    })
    read = {
        which: earth_book.get(
            f"/books/two-worlds/events/meeting?calendar={which}"
        ).get_json()
        for which in ("earth", "imperial")
    }

    assert read["earth"]["start_tick"] == read["imperial"]["start_tick"] == 48
    assert read["earth"]["start_label"] == "February 29, 2024, 00:00 UTC"
    assert read["imperial"]["start_label"] != read["earth"]["start_label"]


def test_february_29_of_a_common_year_is_refused_through_the_api(earth_book):
    refused = earth_book.post("/books/two-worlds/events/nope?calendar=earth", json={
        "location": LOCATION.to_dict(),
        "start_date": {"year": 2023, "month": 2, "day": 29},
        "end_date": {"year": 2023, "month": 2, "day": 29},
    })
    assert refused.status_code == 400
    assert refused.get_json()["code"] == "INVALID_TIMEFRAME"


def test_a_whole_earth_month_spans_that_months_own_length(earth_book):
    resolved = earth_book.post("/books/two-worlds/ui/dates?calendar=earth", json={
        "start_date": {"year": 2024, "month": 2},
        "end_date": {"year": 2024, "month": 2},
    }).get_json()
    assert resolved["end_tick"] - resolved["start_tick"] == 29 * 24


def test_one_library_calendar_anchors_each_book_where_that_story_needs_it(client):
    assert _library(client, "earth", EARTH_HOURS).status_code == 201
    source = {"owner": WRITER, "calendar": "earth"}
    for book, origin in (("first", "2026-01-01T00:00Z"), ("second", "0044-03-15T00:00Z")):
        made = client.post(f"/books/{book}", json={
            "title": book,
            "calendars": [{"id": "earth", "source": source, "origin": origin}],
        })
        assert made.status_code == 201, made.get_json()
        assert made.get_json()["calendars"][0]["origin"] == origin

    labels = [
        client.get(f"/books/{book}/ui/ticks?tick=0").get_json()["ticks"][0]["label"]
        for book in ("first", "second")
    ]
    assert labels == ["January 1, 2026, 00:00 UTC", "March 15, 44, 00:00 UTC"]


# -- a book is never stored in a state it cannot be read in --------------------


@pytest.mark.parametrize("origin,complaint", [
    (None, "needs an 'origin'"),
    ("2024-02-27", "needs a time"),
    ("nonsense", "not a date this calendar can start from"),
])
def test_a_broken_earth_alignment_is_refused_at_the_save(client, origin, complaint):
    assert _library(client, "earth", EARTH_HOURS).status_code == 201
    attachment = {"id": "earth", "source": {"owner": WRITER, "calendar": "earth"}}
    if origin is not None:
        attachment["origin"] = origin

    refused = client.post("/books/broken", json={"title": "B", "calendars": [attachment]})

    assert refused.status_code == 400
    assert refused.get_json()["code"] == "INVALID_BOOK"
    assert complaint in refused.get_json()["error"]
    # And nothing was written: there is no book here to read back.
    assert client.get("/books/broken").status_code in (403, 404)


def test_only_an_earth_calendar_has_somewhere_to_be_anchored(client):
    assert _library(client, "imperial", {
        "base_unit": "hour", "cycles": [{"name": "day", "size": 24}],
    }, name="Imperial").status_code == 201

    refused = client.post("/books/confused", json={
        "title": "C",
        "calendars": [{
            "id": "imperial",
            "source": {"owner": WRITER, "calendar": "imperial"},
            "origin": "2024-02-27",
        }],
    })

    assert refused.status_code == 400
    assert "only a Gregorian calendar" in refused.get_json()["error"]


def test_the_pre_library_inline_shape_has_nowhere_to_put_an_origin(client):
    refused = client.post("/books/inline", json={"title": "I", "calendar": EARTH_DAYS})
    assert refused.status_code == 400
    assert "per-book 'origin'" in refused.get_json()["error"]


@pytest.mark.parametrize("origin,complaint", [
    ("2024-02-27T24:00Z", "no real time of day"),
    ("2024-02-27T06:60Z", "no real time of day"),
    ("2024-02-27T06:00+99:00", "not a UTC offset"),
])
def test_an_origin_naming_no_real_clock_time_is_refused(origin, complaint):
    with pytest.raises(InvalidTimeframe, match=complaint):
        GregorianCodec(origin, "minute")


def test_earth_labels_cannot_be_parsed_back(client):
    """Same answer every other calendar gives: send components or a tick. A
    label is prose, and "February 29, 2024" in one book is a different tick in
    the next."""
    with pytest.raises(InvalidTimeframe, match="send a date"):
        GregorianCodec("2024-02-27", "day").parse("February 29, 2024")


def test_an_origin_that_is_not_a_string_is_refused_by_shape(client):
    assert _library(client, "earth", EARTH_DAYS).status_code == 201
    refused = client.post("/books/typed", json={"title": "T", "calendars": [{
        "id": "earth", "source": {"owner": WRITER, "calendar": "earth"}, "origin": 20240227,
    }]})
    assert refused.status_code == 400
    assert "'origin' must be a string or null" in refused.get_json()["error"]
