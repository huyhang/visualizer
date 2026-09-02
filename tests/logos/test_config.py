"""Revision retention is read from the environment, and refuses nonsense."""

import pytest

from visualizer.logos.config import (
    DEFAULT_SECTION_REVISIONS_KEEP,
    get_section_revisions_keep,
)

VARIABLE = "LOGOS_SECTION_REVISIONS_KEEP"


def test_retention_defaults_and_can_be_raised(monkeypatch):
    monkeypatch.delenv(VARIABLE, raising=False)
    assert get_section_revisions_keep() == DEFAULT_SECTION_REVISIONS_KEEP

    monkeypatch.setenv(VARIABLE, "35")
    assert get_section_revisions_keep() == 35

    monkeypatch.setenv(VARIABLE, "  ")
    assert get_section_revisions_keep() == DEFAULT_SECTION_REVISIONS_KEEP


@pytest.mark.parametrize("value", ["0", "-1", "many", "1.5"])
def test_a_retention_that_cannot_be_honoured_stops_startup(monkeypatch, value):
    """Silently keeping one revision when a hundred were asked for is a failure
    nobody notices until they need the history back."""
    monkeypatch.setenv(VARIABLE, value)
    with pytest.raises(RuntimeError, match=VARIABLE):
        get_section_revisions_keep()
