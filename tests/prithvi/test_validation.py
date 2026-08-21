"""The pure checks: identifiers, pin bodies, scales. No DB, no Flask."""

import pytest

from visualizer.prithvi.errors import (
    InvalidArticleAddress,
    InvalidMapName,
    InvalidPosition,
    InvalidScale,
    InvalidWorld,
    PositionOutOfBounds,
)
from visualizer.prithvi.models import ViewBox
from visualizer.prithvi.validation import (
    validate_article_address,
    validate_map_name,
    validate_position,
    validate_scale,
    validate_world,
)

BOX = ViewBox(0.0, 0.0, 100.0, 50.0)


@pytest.mark.parametrize("world", ["", None, "_prithvi", "_auth"])
def test_reserved_and_missing_worlds_are_refused(world):
    with pytest.raises(InvalidWorld):
        validate_world(world)


@pytest.mark.parametrize("name", ["west", "west-2", "a.b_c", "9"])
def test_ordinary_map_names_are_accepted(name):
    assert validate_map_name(name) == name


@pytest.mark.parametrize("name", ["", None, "-leading", ".dot", "has space", "a" * 129])
def test_unusable_map_names_are_refused(name):
    with pytest.raises(InvalidMapName):
        validate_map_name(name)


def test_a_bad_map_name_says_so_rather_than_blaming_the_drawing():
    """The name and the SVG arrive on one request; the error must tell them apart."""
    with pytest.raises(InvalidMapName) as raised:
        validate_map_name("no spaces please")
    assert raised.value.code == "INVALID_MAP_NAME"


@pytest.mark.parametrize(
    "collection,article", [("", "x"), ("c", ""), ("c" * 256, "x"), ("c", "a" * 256)]
)
def test_unusable_article_addresses_are_refused(collection, article):
    with pytest.raises(InvalidArticleAddress):
        validate_article_address(collection, article)


# -- positions ----------------------------------------------------------------


def test_a_position_is_two_numbers_inside_the_box():
    position = validate_position({"x": 10, "y": 20.5}, BOX)
    assert position.to_dict() == {"x": 10.0, "y": 20.5}


@pytest.mark.parametrize(
    "payload",
    [
        {"x": 1},
        {"x": 1, "y": 2, "label": "no"},
        {"x": "1", "y": 2},
        {"x": True, "y": 2},
        {"x": float("nan"), "y": 2},
        {"x": float("inf"), "y": 2},
        [1, 2],
    ],
)
def test_a_position_that_is_not_exactly_two_numbers_is_refused(payload):
    with pytest.raises(InvalidPosition):
        validate_position(payload, BOX)


def test_unknown_keys_are_refused_rather_than_ignored():
    """Storing nothing would let a confused client stay confused for a while."""
    with pytest.raises(InvalidPosition) as raised:
        validate_position({"x": 1, "y": 2, "lat": 51.5}, BOX)
    assert raised.value.evidence["unexpected"] == ["lat"]


@pytest.mark.parametrize("point", [{"x": -1, "y": 5}, {"x": 5, "y": 51}, {"x": 101, "y": 5}])
def test_a_position_outside_the_box_is_refused(point):
    with pytest.raises(PositionOutOfBounds):
        validate_position(point, BOX)


def test_the_edges_of_the_box_count_as_inside():
    assert validate_position({"x": 0, "y": 0}, BOX)
    assert validate_position({"x": 100, "y": 50}, BOX)


# -- scale --------------------------------------------------------------------


def test_a_scale_is_a_distance_and_a_name_for_it():
    assert validate_scale({"across": 400, "unit": "leagues"}).to_dict() == {
        "across": 400.0,
        "unit": "leagues",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"across": 400},
        {"unit": "leagues"},
        {"across": 0, "unit": "leagues"},
        {"across": -1, "unit": "leagues"},
        {"across": 400, "unit": ""},
        {"across": 400, "unit": "u" * 33},
        {"across": 400, "unit": "leagues", "note": "no"},
        "leagues",
    ],
)
def test_an_unusable_scale_is_refused(payload):
    with pytest.raises(InvalidScale):
        validate_scale(payload)
