"""The guards both route modules share.

``?purge=`` (drop a collection's history) and ``?force=`` (delete media that
articles still use) are the two destructive flags in this service. They were
briefly read by two different helpers -- one an allowlist, one a denylist --
which disagreed on six spellings including ``off``. One reading, tested here.
"""

import pytest
from flask import Flask

from visualizer.akasha.errors import ReservedName
from visualizer.akasha.routing import flag_arg, reject_reserved


@pytest.fixture
def app():
    return Flask(__name__)


@pytest.mark.parametrize("spelling", ["1", "true", "TRUE", "yes", "on", " true "])
def test_an_explicit_yes_sets_the_flag(app, spelling):
    with app.test_request_context(f"/?go={spelling}"):
        assert flag_arg("go") is True


@pytest.mark.parametrize(
    "spelling", ["", "0", "false", "no", "off", "n", "y", "2", "enabled", "maybe"]
)
def test_anything_else_leaves_a_destructive_flag_unset(app, spelling):
    """An unrecognised value is not consent -- `off` and `maybe` must not purge."""
    with app.test_request_context(f"/?go={spelling}"):
        assert flag_arg("go") is False


def test_an_absent_flag_is_unset(app):
    with app.test_request_context("/"):
        assert flag_arg("go") is False


@pytest.mark.parametrize("database", ["_auth", "_chronos", "_akasha_media"])
def test_reserved_namespaces_are_refused(database):
    with pytest.raises(ReservedName):
        reject_reserved(database)


@pytest.mark.parametrize("database", ["earth", "ember-pact", "a_b"])
def test_ordinary_worlds_pass(database):
    assert reject_reserved(database) is None
