"""Unit tests for the pure logic: no DB, no Flask, literal events and ticks."""

import pytest

from visualizer.chronos.book_rules import (
    build_graph,
    graph_view,
    is_acyclic,
    neighborhood,
    validate_convergence,
)
from visualizer.chronos.calendar import (
    EraCodec,
    IdentityCodec,
    MixedRadixCodec,
    codec_for,
    codec_for_attachment,
    codec_for_descriptor,
)
from visualizer.chronos.conflicts import find_temporal_conflicts
from visualizer.chronos.continuation import effective_paths
from visualizer.chronos.errors import (
    CalendarNotFound,
    InvalidBook,
    InvalidCalendar,
    InvalidPlotline,
    InvalidTimeframe,
)
from visualizer.chronos.models import (
    DEFAULT_CALENDAR_ID,
    Book,
    CalendarAttachment,
    EntityRef,
    Event,
    Plotline,
)
from visualizer.chronos.ordering import validate_order
from visualizer.chronos.timeline import overlaps
from visualizer.chronos.validation import (
    MAX_CALENDARS,
    MAX_OVERVIEW,
    validate_book_payload,
    validate_calendar_payload,
    validate_plotline_payload,
)


def ref(id_, collection="characters"):
    return EntityRef("ember-pact", collection, id_)


def ev(id_, start, end, location="highkeep", characters=()):
    return Event(
        id=id_,
        location=ref(location, "locations"),
        start_tick=start,
        end_tick=end,
        characters=[ref(c) for c in characters],
    )


# -- timeline ----------------------------------------------------------------


@pytest.mark.parametrize(
    "a,b,expected",
    [
        ((0, 10), (5, 15), True),    # overlap
        ((0, 10), (10, 20), False),  # touching -> not overlap (half-open)
        ((0, 10), (20, 30), False),  # disjoint
        ((0, 10), (2, 8), True),     # contained
    ],
)
def test_overlaps_half_open(a, b, expected):
    assert overlaps(*a, *b) is expected


# -- temporal conflict -------------------------------------------------------


def test_conflict_when_different_location_overlapping_shared_character():
    a = ev("a", 0, 24, "highkeep", ["aldric"])
    b = ev("b", 10, 30, "emberport", ["aldric"])
    conflicts = find_temporal_conflicts(a, [b])
    assert [c.other_id for c in conflicts] == ["b"]
    assert conflicts[0].characters == [ref("aldric")]


def test_no_conflict_same_location():
    a = ev("a", 0, 24, "emberport", ["aldric"])
    b = ev("b", 10, 30, "emberport", ["aldric"])
    assert find_temporal_conflicts(a, [b]) == []


def test_no_conflict_when_touching():
    a = ev("a", 0, 10, "highkeep", ["aldric"])
    b = ev("b", 10, 20, "emberport", ["aldric"])
    assert find_temporal_conflicts(a, [b]) == []


def test_no_conflict_without_shared_character():
    a = ev("a", 0, 24, "highkeep", ["aldric"])
    b = ev("b", 10, 30, "emberport", ["lyra"])
    assert find_temporal_conflicts(a, [b]) == []


def test_conflict_ignores_self():
    a = ev("a", 0, 24, "highkeep", ["aldric"])
    assert find_temporal_conflicts(a, [a]) == []


# -- ordering ----------------------------------------------------------------


def test_order_ok_when_sequential():
    events = [ev("a", 0, 10), ev("b", 10, 20), ev("c", 25, 30)]
    assert validate_order(events) is None


def test_order_violation_returns_first_pair():
    events = [ev("a", 0, 72), ev("b", 0, 48), ev("c", 100, 110)]
    v = validate_order(events)
    assert (v.before_id, v.after_id) == ("a", "b")
    assert "end(72) > start(0)" == v.reason


# -- convergence -------------------------------------------------------------


def test_convergence_ok_when_all_end_at_terminus():
    pls = [
        Plotline("knights", ["a", "m", "t"], ["g"]),
        Plotline("spys", ["b", "m", "t"], ["g"]),
    ]
    report = validate_convergence(effective_paths(pls), "t")
    assert report.ok and report.failures == []


def test_convergence_reports_offenders():
    pls = [Plotline("knights", ["a", "t"], ["g"]), Plotline("spys", ["b", "x"], ["g"])]
    report = validate_convergence(effective_paths(pls), "t")
    assert not report.ok
    assert report.failures == [
        {"plotline": "spys", "reason": "does not end at terminus", "last_event": "x"}
    ]


def test_convergence_requires_terminus():
    report = validate_convergence(effective_paths([Plotline("p", ["a"], ["g"])]), None)
    assert not report.ok


# -- graph & neighborhood ----------------------------------------------------


def _ember_plotlines():
    return [
        Plotline("knights-road", ["aldric-departs", "meet-at-emberport", "the-coronation"], ["g"]),
        Plotline("spys-shadow", ["lyra-infiltrates", "meet-at-emberport", "the-coronation"], ["g"]),
    ]


def test_graph_is_acyclic_and_marks_convergence():
    view = graph_view(effective_paths(_ember_plotlines()), "the-coronation")
    # the-coronation has a single distinct predecessor (both threads arrive via
    # meet-at-emberport), so the merge is at meet-at-emberport, not the terminus.
    assert set(view["convergence"]) == {"meet-at-emberport"}
    assert view["divergence"] == []
    assert view["terminus"] == "the-coronation"
    assert is_acyclic(build_graph(effective_paths(_ember_plotlines())))


def test_graph_view_exposes_each_plotlines_resolved_path():
    # A client draws one lane per thread from these, order preserved, without
    # re-deriving the path from the edges.
    view = graph_view(effective_paths(_ember_plotlines()), "the-coronation")
    assert view["paths"] == {
        "knights-road": ["aldric-departs", "meet-at-emberport", "the-coronation"],
        "spys-shadow": ["lyra-infiltrates", "meet-at-emberport", "the-coronation"],
    }


def test_neighborhood_convergence_point():
    n = neighborhood(effective_paths(_ember_plotlines()), "meet-at-emberport", "the-coronation")
    assert n.role == "convergence"
    assert n.is_convergence and not n.is_divergence
    incoming = {g.node: g.plotlines for g in n.incoming}
    assert incoming == {
        "aldric-departs": ["knights-road"],
        "lyra-infiltrates": ["spys-shadow"],
    }
    assert [g.node for g in n.outgoing] == ["the-coronation"]


def test_neighborhood_divergence_point():
    pls = [
        Plotline("a", ["start", "left"], ["g"]),
        Plotline("b", ["start", "right"], ["g"]),
    ]
    n = neighborhood(effective_paths(pls), "start", "left")
    assert n.role == "divergence"
    assert n.is_divergence and n.is_origin


def test_neighborhood_terminus_role():
    n = neighborhood(effective_paths(_ember_plotlines()), "the-coronation", "the-coronation")
    assert n.role == "terminus" and n.is_terminus


# -- calendar codec ----------------------------------------------------------


def test_identity_codec_roundtrip():
    codec = IdentityCodec()
    assert codec.format(42) == "42"
    assert codec.parse("42") == 42
    assert codec.parse(" -7 ") == -7


def test_identity_codec_rejects_garbage():
    with pytest.raises(InvalidTimeframe):
        IdentityCodec().parse("not-a-tick")


def test_mixed_radix_format():
    codec = MixedRadixCodec(
        cycles=[{"name": "day", "size": 24}, {"name": "month", "size": 30},
                {"name": "year", "size": 12}],
        base_unit="hour",
        epoch_label="AF",
    )
    # 200 hours = 8 days + 8 hours -> Day 9, Month 1, Year 1, 08:00 AF
    assert codec.format(200) == "Year 1, Month 1, Day 9, 08:00 AF"


def test_mixed_radix_parts_are_coarse_to_fine():
    codec = MixedRadixCodec(
        cycles=[{"name": "day", "size": 24}, {"name": "month", "size": 30},
                {"name": "year", "size": 12}],
        base_unit="hour", epoch_label="AF",
    )
    assert codec.parts(200) == ["Year 1", "Month 1", "Day 9", "08:00 AF"]
    # parts join back to exactly the formatted label.
    assert ", ".join(codec.parts(200)) == codec.format(200)


def test_mixed_radix_parts_use_fantasy_cycle_names():
    codec = MixedRadixCodec(
        cycles=[{"name": "span", "size": 10}, {"name": "moon", "size": 8},
                {"name": "age", "size": 100}],
        base_unit="bell", epoch_label="SR",
    )
    # Age/Moon/Span, coarse-to-fine, plus the clock -- no hardcoded year/month.
    assert codec.parts(0) == ["Age 1", "Moon 1", "Span 1", "00:00 SR"]


def test_identity_codec_parts_is_single_component():
    assert IdentityCodec().parts(200) == ["200"]


def test_codec_for_defaults_to_identity():
    assert isinstance(codec_for(Book("b")), IdentityCodec)
    assert isinstance(codec_for(Book.from_storage({"id": "b", "calendar": None})), IdentityCodec)


def test_codec_for_builds_mixed_radix():
    book = _book_with(_attachment("main", DAYS))
    assert isinstance(codec_for(book), MixedRadixCodec)


# -- several calendars over one tick line -------------------------------------
#
# The feature's whole claim: parallel reckonings are parallel *labellings*, never
# parallel timelines. Nothing below moves a tick.

DAYS = {"cycles": [{"name": "day", "size": 10}], "base_unit": "hour"}
MOONS = {"cycles": [{"name": "moon", "size": 8}], "base_unit": "bell", "epoch_label": "SR"}


def _attachment(id_, descriptor=None, **kw):
    return CalendarAttachment(id=id_, descriptor=descriptor, **kw)


def _book_with(*attachments):
    return Book("b", calendars=list(attachments))


def test_the_first_attachment_is_what_an_unqualified_read_uses():
    book = _book_with(_attachment("imperial", DAYS), _attachment("elvish", MOONS))
    assert codec_for(book).format(20) == codec_for(book, "imperial").format(20)
    assert codec_for(book, "elvish").format(20) != codec_for(book, "imperial").format(20)


def test_two_calendars_disagree_only_about_the_label():
    """The assertion this whole feature exists to make: same tick, two readings."""
    book = _book_with(_attachment("imperial", DAYS), _attachment("elvish", MOONS))
    assert codec_for(book, "imperial").format(20) == "Day 3, 00:00"
    assert codec_for(book, "elvish").format(20) == "Moon 3, 04:00 SR"


def test_an_unattached_calendar_is_refused_rather_than_guessed_at():
    """A stale bookmark must say so. Falling back to the primary would misreport
    every date on screen while looking entirely healthy."""
    book = _book_with(_attachment("imperial", DAYS))
    with pytest.raises(CalendarNotFound) as raised:
        codec_for(book, "elvish")
    assert raised.value.evidence["attached"] == ["imperial"]


def test_a_book_with_no_calendars_still_reads_through_a_default():
    assert codec_for(_book_with()).format(7) == "7"


# -- eras: calendars that begin, and end --------------------------------------


def test_an_era_counts_from_its_own_beginning():
    """A reckoning founded at tick 100 reads Day 1 there, not Day 11."""
    codec = EraCodec(codec_for_descriptor(DAYS), from_tick=100)
    assert codec.format(100) == "Day 1, 00:00"
    assert codec.format(120) == "Day 3, 00:00"


def test_an_era_refuses_to_date_what_it_did_not_witness():
    codec = EraCodec(
        codec_for_descriptor(DAYS), from_tick=100, until_tick=200, label="Imperial Reckoning"
    )
    assert codec.format(50) == "before Imperial Reckoning"
    assert codec.format(300) == "after Imperial Reckoning"
    assert codec.format(150) == "Day 6, 00:00"


@pytest.mark.parametrize("bounds,tick,expected", [
    pytest.param({"from_tick": 100}, 50, "before the Count", id="only-a-start"),
    # The case a book actually hits first: a reckoning that was always kept and
    # simply stopped. With no ``from_tick`` there is only one way out of range,
    # and asking which side we fell off must not compare a tick against None.
    pytest.param({"until_tick": 100}, 150, "after the Count", id="only-an-end"),
    pytest.param({"from_tick": 10, "until_tick": 100}, 5, "before the Count", id="both-before"),
    pytest.param({"from_tick": 10, "until_tick": 100}, 500, "after the Count", id="both-after"),
])
def test_an_era_says_which_side_of_itself_a_tick_fell_off(bounds, tick, expected):
    codec = EraCodec(codec_for_descriptor(DAYS), label="the Count", **bounds)
    assert codec.format(tick) == expected
    assert codec.parts(tick) == [expected]


def test_an_era_ends_half_open_like_every_other_interval():
    """``until_tick`` is the first tick *not* covered -- the same convention
    ``timeline.overlaps`` uses, so the two can never disagree at a boundary."""
    codec = EraCodec(codec_for_descriptor(DAYS), from_tick=0, until_tick=200)
    assert codec.covers(199)
    assert not codec.covers(200)


def test_an_out_of_era_tick_is_one_component_so_a_ui_can_band_it():
    codec = EraCodec(codec_for_descriptor(DAYS), from_tick=100, label="the Pact")
    assert codec.parts(10) == ["before the Pact"]
    # In era, the inner codec's structure survives the decoration untouched.
    assert codec.parts(120) == codec_for_descriptor(DAYS).parts(20)


def test_an_era_survives_the_round_trip_wherever_its_inner_codec_does():
    codec = EraCodec(IdentityCodec(), from_tick=100)
    assert codec.parse(codec.format(137)) == 137


def test_a_calendar_without_an_era_is_not_decorated_at_all():
    """Spanning the whole story is the common case; it should cost nothing."""
    assert isinstance(codec_for_attachment(_attachment("x", DAYS)), MixedRadixCodec)
    assert isinstance(
        codec_for_attachment(_attachment("x", DAYS, from_tick=3)), EraCodec
    )


def test_an_era_over_no_descriptor_still_bounds_plain_numbers():
    codec = codec_for_attachment(_attachment("x", None, from_tick=10, label="the Vigil"))
    assert codec.format(5) == "before the Vigil"
    assert codec.format(14) == "4"


# -- reading a book stored before the library existed -------------------------


def test_a_pre_library_book_is_promoted_to_one_attachment():
    """No migration runs; the old field is simply read as a list of one."""
    book = Book.from_storage({"id": "b", "calendar": DAYS})
    assert [c.id for c in book.calendars] == [DEFAULT_CALENDAR_ID]
    assert book.calendars[0].descriptor == DAYS
    assert codec_for(book).format(20) == "Day 3, 00:00"


def test_promotion_is_one_way_so_no_document_carries_both_spellings():
    stored = Book.from_storage({"id": "b", "calendar": DAYS}).to_storage()
    assert "calendar" not in stored
    assert stored["calendars"][0]["descriptor"] == DAYS


def test_the_legacy_calendar_field_is_derived_not_stored():
    book = _book_with(_attachment("imperial", DAYS), _attachment("elvish", MOONS))
    # A pre-library reader asking for "the" calendar gets the primary one.
    assert book.calendar == DAYS


# -- book payload validation -------------------------------------------------
#
# The calendar descriptor is checked at the write because ``codec_for`` builds
# from it on every *read*: an unbuildable one would store fine and then break
# every later request, blaming a timeframe for a mistake made at creation.

DEMO_CALENDAR = {
    "base_unit": "hour",
    "cycles": [{"name": "day", "size": 24}, {"name": "month", "size": 30}],
    "epoch_label": "AF",
}


def test_book_payload_keeps_the_calendar_exactly_as_sent():
    """Checked, never rewritten -- design §4.1 leaves cycle names open, so there
    is no canonical form to normalise towards."""
    book = validate_book_payload("b", {"title": "T", "calendar": DEMO_CALENDAR})
    assert book.calendar == DEMO_CALENDAR
    assert book.title == "T"


def test_book_payload_allows_no_calendar():
    assert validate_book_payload("b", {"title": "T"}).calendar is None
    assert validate_book_payload("b", {"calendar": None}).calendar is None


def test_book_payload_allows_the_identity_calendar_without_cycles():
    """`kind: identity` says "ticks are their own labels", so cycles are moot."""
    assert validate_book_payload("b", {"calendar": {"kind": "identity"}}).calendar


@pytest.mark.parametrize("calendar", [
    pytest.param("hours", id="not-an-object"),
    pytest.param({"kind": "julian", "cycles": [{"name": "day", "size": 24}]}, id="unknown-kind"),
    pytest.param({"cycles": []}, id="no-cycles"),
    pytest.param({"cycles": "day"}, id="cycles-not-a-list"),
    pytest.param({"cycles": ["day"]}, id="cycle-not-an-object"),
    pytest.param({"cycles": [{"size": 24}]}, id="cycle-without-a-name"),
    pytest.param({"cycles": [{"name": "  ", "size": 24}]}, id="cycle-with-a-blank-name"),
    pytest.param({"cycles": [{"name": 12, "size": 24}]}, id="cycle-named-with-a-number"),
    pytest.param({"cycles": [{"name": "day"}]}, id="cycle-without-a-size"),
    pytest.param({"cycles": [{"name": "day", "size": 0}]}, id="cycle-of-no-length"),
    pytest.param({"cycles": [{"name": "day", "size": -3}]}, id="cycle-of-negative-length"),
    pytest.param({"cycles": [{"name": "day", "size": 2.5}]}, id="fractional-cycle"),
    pytest.param({"cycles": [{"name": "day", "size": True}]}, id="boolean-cycle-size"),
    pytest.param({"cycles": [{"name": "day", "size": 24}], "base_unit": ""}, id="blank-base-unit"),
    pytest.param({"cycles": [{"name": "day", "size": 24}], "base_unit": 7}, id="numeric-base-unit"),
    pytest.param({"cycles": [{"name": "day", "size": 24}], "epoch_label": 7}, id="numeric-epoch"),
])
def test_book_payload_refuses_a_calendar_no_codec_could_be_built_from(calendar):
    with pytest.raises(InvalidBook):
        validate_book_payload("b", {"calendar": calendar})


def test_every_refused_calendar_would_indeed_have_broken_a_read():
    """The validator's job is to be no stricter than the codec it guards.

    A descriptor it accepts must build; one it rejects must be one that either
    fails to build or reads back nonsense. This pins the accept side, which is
    the direction that would silently block legal books."""
    book = validate_book_payload("b", {"calendar": DEMO_CALENDAR})
    assert codec_for(book).format(200) == "Month 1, Day 9, 08:00 AF"


# -- attaching several calendars ----------------------------------------------


def _payload(*calendars):
    return {"title": "T", "calendars": list(calendars)}


def _from(name, owner="mara"):
    return {"owner": owner, "calendar": name}


def test_book_payload_accepts_a_list_of_reckonings():
    """A book *names* its calendars; the service fills the descriptors in from
    the library, so nothing here carries content."""
    book = validate_book_payload("b", _payload(
        {"id": "imperial", "label": "Imperial Reckoning", "source": _from("imperial")},
        {"id": "elvish", "source": _from("elvish"), "until_tick": 900},
    ))
    assert [c.id for c in book.calendars] == ["imperial", "elvish"]
    assert book.calendars[0].display_label == "Imperial Reckoning"
    # An unlabelled reckoning falls back to its id rather than showing blank.
    assert book.calendars[1].display_label == "elvish"
    # Descriptors are the library's to supply, so validation leaves them empty.
    assert [c.descriptor for c in book.calendars] == [None, None]


def test_book_payload_refuses_two_calendars_with_the_same_id():
    """The id is what a read names to pick a reckoning, so a duplicate makes
    that choice ambiguous rather than merely untidy."""
    with pytest.raises(InvalidBook):
        validate_book_payload("b", _payload(
            {"id": "imperial", "descriptor": DEMO_CALENDAR},
            {"id": "imperial", "descriptor": None},
        ))


def test_book_payload_refuses_a_calendar_that_ends_before_it_began():
    with pytest.raises(InvalidBook):
        validate_book_payload("b", _payload(
            {"id": "x", "descriptor": None, "from_tick": 400, "until_tick": 100},
        ))


def test_book_payload_refuses_a_calendar_described_inline():
    """The library is where calendars are authored. Refused rather than ignored:
    whoever sent a descriptor meant it to be used, and quietly substituting the
    library's would be worse than saying no. "Plain numbers" is not a calendar
    described inline -- it is a book with no attachments at all."""
    with pytest.raises(InvalidBook):
        validate_book_payload("b", _payload(
            {"id": "mine", "descriptor": DEMO_CALENDAR, "source": _from("imperial")}))
    with pytest.raises(InvalidBook):
        validate_book_payload("b", _payload({"id": "mine", "descriptor": None}))
    # ...and a book with no calendars at all is exactly how plain ticks are said.
    assert validate_book_payload("b", {"title": "T", "calendars": []}).calendars == []


def test_an_attachment_must_name_a_library_calendar():
    with pytest.raises(InvalidBook):
        validate_book_payload("b", _payload({"id": "orphan"}))


def test_book_payload_refuses_both_spellings_at_once():
    """Ambiguous about which the writer meant. Picking one silently is how a
    calendar goes missing with nothing on screen to say so."""
    with pytest.raises(InvalidBook):
        validate_book_payload("b", {
            "calendar": DEMO_CALENDAR,
            "calendars": [{"id": "x", "descriptor": DEMO_CALENDAR}],
        })


def test_book_payload_caps_the_number_of_calendars():
    too_many = [{"id": f"c{i}", "descriptor": None} for i in range(MAX_CALENDARS + 1)]
    with pytest.raises(InvalidBook):
        validate_book_payload("b", _payload(*too_many))


def test_provenance_must_name_the_owner_as_well_as_the_calendar():
    """Library ids are unique per writer, so an unqualified pointer would let one
    writer's "imperial" be mistaken for another's."""
    with pytest.raises(InvalidBook):
        validate_book_payload("b", _payload({"id": "x", "source": {"calendar": "imperial"}}))
    book = validate_book_payload("b", _payload({"id": "x", "source": _from("imperial")}))
    assert book.calendars[0].source == {
        "owner": "mara", "calendar": "imperial", "rev": None,
    }


def test_a_revision_is_carried_as_an_intention_not_a_fact():
    """``rev`` says *which* copy the caller wants -- omit it for "as it stands
    today", send the one this book holds for "keep mine". The service decides
    what that means and stamps the revision it actually read."""
    asking = validate_book_payload("b", _payload(
        {"id": "x", "source": {"owner": "mara", "calendar": "imperial", "rev": 3}}))
    assert asking.calendars[0].source["rev"] == 3
    latest = validate_book_payload("b", _payload({"id": "x", "source": _from("imperial")}))
    assert latest.calendars[0].source["rev"] is None
    with pytest.raises(InvalidBook):
        validate_book_payload("b", _payload(
            {"id": "x", "source": {"owner": "m", "calendar": "i", "rev": "soon"}}))


# -- library calendars --------------------------------------------------------


def test_library_calendar_payload_parses():
    calendar = validate_calendar_payload("imperial", {
        "name": "Imperial Reckoning", "descriptor": DEMO_CALENDAR, "notes": "Used after AF 0.",
    })
    assert (calendar.id, calendar.name) == ("imperial", "Imperial Reckoning")


def test_library_calendar_needs_a_name_and_a_descriptor():
    with pytest.raises(InvalidCalendar):
        validate_calendar_payload("x", {"descriptor": DEMO_CALENDAR})
    with pytest.raises(InvalidCalendar):
        validate_calendar_payload("x", {"name": "X"})


def test_library_calendar_faces_exactly_the_rule_a_book_would_apply():
    """A library that stored a descriptor no book could accept would hand the
    writer a calendar that fails the moment they try to use it."""
    bad = {"cycles": [{"name": "day", "size": 0}]}
    with pytest.raises(InvalidCalendar):
        validate_calendar_payload("x", {"name": "X", "descriptor": bad})
    with pytest.raises(InvalidBook):
        validate_book_payload("b", _payload({"id": "x", "descriptor": bad}))


# -- the overview (books and plotlines) --------------------------------------
#
# Free prose that no rule reads, so there is little to check -- but the little
# there is matters: it must survive untouched, and "never written" and "written,
# then emptied" must stay the same state rather than becoming null and "".


def _book(**body):
    return validate_book_payload("b", body)


def _plotline(**body):
    return validate_plotline_payload("p", {"events": ["a"], "goals": ["g"], **body})


@pytest.mark.parametrize("parse", [_book, _plotline], ids=["book", "plotline"])
def test_overview_defaults_to_empty_when_absent(parse):
    assert parse().overview == ""


@pytest.mark.parametrize("parse", [_book, _plotline], ids=["book", "plotline"])
def test_overview_is_kept_exactly_as_written(parse):
    """Prose, not a slug: nothing is trimmed, collapsed or normalised. The
    writer's paragraph breaks are theirs."""
    prose = "  Two sisters,\n\nand the winter between them.  "
    assert parse(overview=prose).overview == prose


@pytest.mark.parametrize(
    "parse,err", [(_book, InvalidBook), (_plotline, InvalidPlotline)],
    ids=["book", "plotline"],
)
@pytest.mark.parametrize("value", [
    pytest.param(7, id="a-number"),
    pytest.param(["prose"], id="a-list"),
    pytest.param({"text": "prose"}, id="an-object"),
    # Null is refused rather than coerced: there is one empty overview, and it
    # is "". A client clearing the field sends the empty string it was given.
    pytest.param(None, id="null"),
])
def test_overview_must_be_a_string(parse, err, value):
    with pytest.raises(err):
        parse(overview=value)


@pytest.mark.parametrize(
    "parse,err", [(_book, InvalidBook), (_plotline, InvalidPlotline)],
    ids=["book", "plotline"],
)
def test_an_overview_at_the_limit_is_accepted_and_one_past_it_is_not(parse, err):
    """A sanity bound, not a style rule: the field is stored whole and returned
    in every listing, so an unbounded paste would bloat responses nothing
    paginates by size. The boundary itself is legal."""
    assert len(parse(overview="x" * MAX_OVERVIEW).overview) == MAX_OVERVIEW
    with pytest.raises(err) as ei:
        parse(overview="x" * (MAX_OVERVIEW + 1))
    assert ei.value.evidence == {"length": MAX_OVERVIEW + 1, "max": MAX_OVERVIEW}


def test_book_overview_round_trips_through_storage():
    stored = Book(id="b", overview="What it is about.").to_storage()
    assert Book.from_storage({"id": "b", **stored}).overview == "What it is about."


def test_plotline_overview_round_trips_through_storage():
    stored = Plotline(id="p", events=["a"], goals=["g"], overview="Her thread.").to_storage()
    assert Plotline.from_storage({"id": "p", **stored}).overview == "Her thread."


@pytest.mark.parametrize("model,doc", [
    (Book, {"id": "b"}),
    (Plotline, {"id": "p", "events": ["a"], "goals": ["g"]}),
], ids=["book", "plotline"])
def test_a_record_written_before_the_field_existed_reads_as_empty(model, doc):
    """No migration is needed: the key is simply absent on everything stored so
    far, and absent already means empty."""
    assert model.from_storage(doc).overview == ""
