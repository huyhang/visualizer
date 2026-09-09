"""The presentation manifest: what can be said about showing a diorama."""

import pytest

from visualizer.akasha.diorama import (
    DEFAULTS,
    MAX_DESCRIPTION,
    MAX_LIGHTS,
    MAX_TITLE,
    SCHEMA_VERSION,
    validate_manifest,
)
from visualizer.akasha.errors import InvalidDiorama


def test_a_title_is_the_only_thing_required():
    manifest = validate_manifest({"title": "The Tea Garden"})
    assert manifest == {
        "schema_version": SCHEMA_VERSION,
        "title": "The Tea Garden",
        "description": "",
        "lights": [],
        **DEFAULTS,
    }


@pytest.mark.parametrize("payload", [{}, {"title": "  "}, {"title": None}])
def test_a_diorama_without_a_title_is_refused(payload):
    with pytest.raises(InvalidDiorama, match="needs a title"):
        validate_manifest(payload)


def test_a_title_is_collapsed_and_a_description_is_only_trimmed():
    manifest = validate_manifest(
        {"title": "  The   Tea  Garden ", "description": "  Two lines\n\nof prose.  "}
    )
    assert manifest["title"] == "The Tea Garden"
    assert manifest["description"] == "Two lines\n\nof prose."


@pytest.mark.parametrize(
    "field,limit", [("title", MAX_TITLE), ("description", MAX_DESCRIPTION)]
)
def test_prose_is_bounded(field, limit):
    payload = {"title": "t", field: "x" * (limit + 1)}
    with pytest.raises(InvalidDiorama, match=f"at most {limit}"):
        validate_manifest(payload)


def test_a_manifest_from_a_future_version_is_refused_rather_than_guessed_at():
    with pytest.raises(InvalidDiorama, match="version 1 manifest"):
        validate_manifest({"title": "t", "schema_version": 2})


def test_a_field_this_version_does_not_understand_is_refused():
    """Accepting it would store a setting nothing reads and nobody is told about."""
    with pytest.raises(InvalidDiorama, match="does not understand"):
        validate_manifest({"title": "t", "camera_roll": 12})


# -- the camera --------------------------------------------------------------


@pytest.mark.parametrize(
    "given,expected", [(0, 0), (35, 35), (359, 359), (360, 0), (370, 10), (-10, 350)]
)
def test_azimuth_wraps_because_370_and_10_name_the_same_camera(given, expected):
    assert validate_manifest({"title": "t", "camera_azimuth": given})[
        "camera_azimuth"
    ] == expected


@pytest.mark.parametrize("elevation", [-89, 0, 25, 89])
def test_elevation_is_accepted_within_the_poles(elevation):
    assert validate_manifest({"title": "t", "camera_elevation": elevation})[
        "camera_elevation"
    ] == elevation


@pytest.mark.parametrize("elevation", [-90, 90, 900])
def test_elevation_at_or_past_a_pole_is_refused(elevation):
    """Straight down loses the camera's up-vector and the view spins."""
    with pytest.raises(InvalidDiorama, match="camera_elevation"):
        validate_manifest({"title": "t", "camera_elevation": elevation})


@pytest.mark.parametrize("speed", [0, 0.5, 6, 30])
def test_rotation_speed_is_accepted_within_range(speed):
    assert validate_manifest({"title": "t", "rotation_speed": speed})[
        "rotation_speed"
    ] == speed


@pytest.mark.parametrize("speed", [-1, 31, 1000])
def test_an_out_of_range_value_is_refused_not_quietly_clamped(speed):
    """Clamping tells the writer their input was accepted when it was replaced."""
    with pytest.raises(InvalidDiorama, match="between 0 and 30"):
        validate_manifest({"title": "t", "rotation_speed": speed})


@pytest.mark.parametrize(
    "field", ["camera_azimuth", "camera_elevation", "rotation_speed"]
)
@pytest.mark.parametrize("value", ["35", "", [], {}, True])
def test_a_camera_field_that_is_not_a_number_is_refused(field, value):
    with pytest.raises(InvalidDiorama, match="must be a number"):
        validate_manifest({"title": "t", field: value})


@pytest.mark.parametrize("value", ["yes", 1, 0, "true"])
def test_auto_rotate_must_be_a_boolean(value):
    with pytest.raises(InvalidDiorama, match="true or false"):
        validate_manifest({"title": "t", "auto_rotate": value})


# -- local lights ------------------------------------------------------------


def test_a_light_is_filled_out_from_its_defaults():
    manifest = validate_manifest({"title": "t", "lights": [{"type": "point"}]})
    assert manifest["lights"] == [
        {"type": "point", "x": 0.0, "y": 0.0, "z": 0.0,
         "color": "#ffffff", "intensity": 1.0}
    ]


def test_a_full_light_round_trips():
    light = {"type": "spot", "x": 2, "y": 5.5, "z": -3,
             "color": "FFCC88", "intensity": 4}
    got = validate_manifest({"title": "t", "lights": [light]})["lights"][0]
    assert got == {"type": "spot", "x": 2.0, "y": 5.5, "z": -3.0,
                   "color": "#ffcc88", "intensity": 4.0}


@pytest.mark.parametrize("kind", ["directional", "ambient", "hemisphere", "", None])
def test_only_the_two_light_types_the_viewer_builds_are_accepted(kind):
    """A directional light is a second sun; it fights the first and flattens
    the shadows the scene is lit for."""
    with pytest.raises(InvalidDiorama, match="must be one of"):
        validate_manifest({"title": "t", "lights": [{"type": kind}]})


def test_the_number_of_lights_is_capped():
    lights = [{"type": "point"}] * (MAX_LIGHTS + 1)
    with pytest.raises(InvalidDiorama, match=f"at most {MAX_LIGHTS}"):
        validate_manifest({"title": "t", "lights": lights})


@pytest.mark.parametrize("colour", ["#gggggg", "#fff", "red", "#ffcc8", 123])
def test_a_light_needs_a_real_colour(colour):
    with pytest.raises(InvalidDiorama):
        validate_manifest({"title": "t", "lights": [{"type": "point", "color": colour}]})


@pytest.mark.parametrize("intensity", [-0.1, 21])
def test_light_intensity_is_bounded(intensity):
    with pytest.raises(InvalidDiorama, match="intensity"):
        validate_manifest(
            {"title": "t", "lights": [{"type": "point", "intensity": intensity}]}
        )


def test_a_light_placed_absurdly_far_away_is_refused():
    with pytest.raises(InvalidDiorama):
        validate_manifest({"title": "t", "lights": [{"type": "point", "y": 1e9}]})


def test_a_light_with_an_unknown_field_is_refused():
    with pytest.raises(InvalidDiorama, match="unknown fields"):
        validate_manifest(
            {"title": "t", "lights": [{"type": "point", "castShadow": True}]}
        )


@pytest.mark.parametrize("value", ["not a list", 5, {"type": "point"}])
def test_lights_must_be_a_list(value):
    with pytest.raises(InvalidDiorama, match="'lights' must be a list"):
        validate_manifest({"title": "t", "lights": value})


@pytest.mark.parametrize("payload", ["a string", 5, [], True])
def test_a_manifest_that_is_not_an_object_is_refused(payload):
    with pytest.raises(InvalidDiorama, match="must be an object"):
        validate_manifest(payload)
