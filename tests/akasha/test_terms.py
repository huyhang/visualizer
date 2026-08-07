"""The UI vocabulary is defined twice — once for Jinja, once for the SPA.

``terms.py`` serves the server-rendered pages and ``static/js/terms.js`` serves
the browse views, because there is no build step to share one file between them.
Two copies of the same table is a drift waiting to happen: someone renames
"category" in the dialogs and the account page keeps saying "collection". These
tests make that a failing build rather than a bug report.
"""

import re
from pathlib import Path

import pytest

from visualizer.akasha.terms import TERMS

_TERMS_JS = (
    Path(__file__).resolve().parents[2]
    / "src" / "visualizer" / "akasha" / "static" / "js" / "terms.js"
)

# `database: { one: "world", many: "worlds", One: "World", Many: "Worlds" },`
_ENTRY = re.compile(r"(?P<level>\w+):\s*\{(?P<body>[^}]*)\}")
_PAIR = re.compile(r"(?P<key>\w+):\s*\"(?P<value>[^\"]*)\"")


def _js_terms() -> dict:
    source = _TERMS_JS.read_text()
    table = source.split("export const T = {", 1)[1].split("\n};", 1)[0]
    return {
        m.group("level"): dict(_PAIR.findall(m.group("body")))
        for m in _ENTRY.finditer(table)
    }


def test_the_two_vocabularies_agree():
    assert _js_terms() == TERMS


@pytest.mark.parametrize("level", ["database", "collection", "document"])
def test_every_level_is_named_four_ways(level):
    """Views need lower and title case, singular and plural — `count()` picks
    the plural from the table rather than adding an "s" (which is where
    "categorys" would have come from)."""
    assert set(TERMS[level]) == {"one", "many", "One", "Many"}
    assert all(TERMS[level].values())


def test_the_pages_speak_the_chosen_vocabulary(client):
    """A spot check through the real templates: the context processor is wired
    up, and the account page is not still saying "collection"."""
    client.post("/databases/earth/collections/lotr")  # so there is something owned
    page = client.get("/account").get_data(as_text=True)
    assert f"{TERMS['collection']['Many']} (1)" in page
    assert "Collections (" not in page


def test_the_api_keeps_the_mongo_names(client):
    """The relabel is presentation only. Renaming these would break every
    wikilink, grant and chronos reference that addresses them."""
    client.post("/databases/earth/collections/lotr")
    body = client.get("/databases/earth/collections").get_json()
    assert set(body) == {"database", "title", "collections", "empty"}
    assert body["database"] == "earth"  # the address, beside its rendering
    entry = client.get("/databases").get_json()["databases"][0]
    assert entry.keys() == {"name", "title", "collections", "articles"}
    # `title` is a rendering of `name`, never a replacement for it.
    assert entry["name"] == "earth"

