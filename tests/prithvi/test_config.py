"""The three environment numbers, and the noise they refuse to accept."""

import pytest

from visualizer.prithvi.config import (
    DEFAULT_MAP_REVISIONS_KEEP,
    DEFAULT_MAX_SVG_BYTES,
    DEFAULT_PIN_REVISIONS_KEEP,
    get_map_revisions_keep,
    get_max_svg_bytes,
    get_pin_revisions_keep,
)

NAMES = (
    "PRITHVI_MAX_SVG_BYTES",
    "PRITHVI_MAP_REVISIONS_KEEP",
    "PRITHVI_PIN_REVISIONS_KEEP",
)


def test_an_unconfigured_deployment_gets_the_documented_defaults(monkeypatch):
    for name in NAMES:
        monkeypatch.delenv(name, raising=False)

    assert get_max_svg_bytes() == DEFAULT_MAX_SVG_BYTES
    assert get_map_revisions_keep() == DEFAULT_MAP_REVISIONS_KEEP
    assert get_pin_revisions_keep() == DEFAULT_PIN_REVISIONS_KEEP


def test_each_number_is_read_from_its_own_variable(monkeypatch):
    monkeypatch.setenv("PRITHVI_MAX_SVG_BYTES", "1234")
    monkeypatch.setenv("PRITHVI_MAP_REVISIONS_KEEP", "7")
    monkeypatch.setenv("PRITHVI_PIN_REVISIONS_KEEP", "30")

    assert get_max_svg_bytes() == 1234
    assert get_map_revisions_keep() == 7
    assert get_pin_revisions_keep() == 30


@pytest.mark.parametrize("value", ["0", "-1", "5MB", "lots"])
def test_a_meaningless_value_stops_the_deployment_rather_than_the_first_request(
    monkeypatch, value
):
    monkeypatch.setenv("PRITHVI_MAX_SVG_BYTES", value)
    with pytest.raises(RuntimeError):
        get_max_svg_bytes()


def test_an_empty_variable_means_unset(monkeypatch):
    """Compose writes an empty string for a variable nobody filled in."""
    monkeypatch.setenv("PRITHVI_MAX_SVG_BYTES", "")
    assert get_max_svg_bytes() == DEFAULT_MAX_SVG_BYTES
