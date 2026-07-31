"""Unit tests for the pure logic: no DB, no Flask, literal events and ticks."""

import pytest

from visualizer.chronos.book_rules import (
    build_graph,
    graph_view,
    is_acyclic,
    neighborhood,
    validate_convergence,
)
from visualizer.chronos.calendar import IdentityCodec, MixedRadixCodec, codec_for
from visualizer.chronos.conflicts import find_temporal_conflicts
from visualizer.chronos.errors import InvalidTimeframe
from visualizer.chronos.models import Book, EntityRef, Event, Plotline
from visualizer.chronos.ordering import validate_order
from visualizer.chronos.timeline import overlaps


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
    report = validate_convergence(pls, "t")
    assert report.ok and report.failures == []


def test_convergence_reports_offenders():
    pls = [Plotline("knights", ["a", "t"], ["g"]), Plotline("spys", ["b", "x"], ["g"])]
    report = validate_convergence(pls, "t")
    assert not report.ok
    assert report.failures == [
        {"plotline": "spys", "reason": "does not end at terminus", "last_event": "x"}
    ]


def test_convergence_requires_terminus():
    report = validate_convergence([Plotline("p", ["a"], ["g"])], None)
    assert not report.ok


# -- graph & neighborhood ----------------------------------------------------


def _ember_plotlines():
    return [
        Plotline("knights-road", ["aldric-departs", "meet-at-emberport", "the-coronation"], ["g"]),
        Plotline("spys-shadow", ["lyra-infiltrates", "meet-at-emberport", "the-coronation"], ["g"]),
    ]


def test_graph_is_acyclic_and_marks_convergence():
    view = graph_view(_ember_plotlines(), "the-coronation")
    # the-coronation has a single distinct predecessor (both threads arrive via
    # meet-at-emberport), so the merge is at meet-at-emberport, not the terminus.
    assert set(view["convergence"]) == {"meet-at-emberport"}
    assert view["divergence"] == []
    assert view["terminus"] == "the-coronation"
    assert is_acyclic(build_graph(_ember_plotlines()))


def test_neighborhood_convergence_point():
    n = neighborhood(_ember_plotlines(), "meet-at-emberport", "the-coronation")
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
    n = neighborhood(pls, "start", "left")
    assert n.role == "divergence"
    assert n.is_divergence and n.is_origin


def test_neighborhood_terminus_role():
    n = neighborhood(_ember_plotlines(), "the-coronation", "the-coronation")
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


def test_codec_for_defaults_to_identity():
    assert isinstance(codec_for(Book("b")), IdentityCodec)
    assert isinstance(codec_for({"calendar": None}), IdentityCodec)


def test_codec_for_builds_mixed_radix():
    book = Book("b", calendar={"cycles": [{"name": "day", "size": 10}], "base_unit": "h"})
    assert isinstance(codec_for(book), MixedRadixCodec)
