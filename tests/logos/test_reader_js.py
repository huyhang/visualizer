"""The reader's pure modules, exercised from pytest.

``prose.js`` turns a validated manuscript document into nodes, ``preferences``
turns whatever is in localStorage into a set of choices this page can honour,
and ``navigation`` answers where you are in an ordered list. The first two take
their world by injection -- a node factory, a storage object -- which is what
lets ``node`` run every branch with plain dictionaries, no DOM.

The renderer is the part of this service that handles text somebody else wrote,
so most of what follows is about what it *refuses*: a mark it does not know, a
node type it does not know, and above all a URL scheme it does not know.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_JS_DIR = (
    Path(__file__).resolve().parents[2]
    / "src" / "visualizer" / "logos" / "static" / "js"
)
_MODULES = ("prose.js", "preferences.js", "navigation.js")

_PREAMBLE = """\
import { RenderError, renderDocument, safeHref } from "./prose.js";
import {
  DEFAULTS, DISPLAY_FIELDS, otherMode, parsePreferences, readPreferences,
  resetDisplay, showsChronos, writePreferences,
} from "./preferences.js";
import { neighbours, sectionLabel, sectionName } from "./navigation.js";

const INPUT = %s;

// A node factory that records the tree instead of building one, and a
// localStorage with the same string semantics (missing keys read as null).
const nodes = {
  text: (value) => ({ tag: "#text", value }),
  element: (tag, attrs = {}, children = []) => ({ tag, attrs, children }),
  fragment: (children = []) => ({ tag: "#fragment", children }),
};
const store = (backing) => ({
  getItem: (key) => (key in backing ? backing[key] : null),
  setItem: (key, value) => { backing[key] = String(value); },
});
const sealed = {
  getItem() { throw new Error("denied"); },
  setItem() { throw new Error("denied"); },
};
// The name *and* the type: `app.js` branches on `instanceof RenderError`, so a
// refusal that is merely some Error would be re-thrown to the page instead of
// degrading one section.
const caught = (fn) => {
  try {
    fn();
    return "rendered";
  } catch (e) {
    return [e.name, e instanceof RenderError];
  }
};
const emit = (value) => console.log(JSON.stringify(value));
"""


def _node_binary():
    """node from the PATH, else the one the dev dependency ships, else None."""
    found = shutil.which("node")
    if found:
        return found
    try:
        import nodejs_wheel  # optional: only this module needs it
    except ImportError:
        return None
    exe = "node.exe" if sys.platform == "win32" else "node"
    candidate = Path(nodejs_wheel.__file__).parent / "bin" / exe
    return str(candidate) if candidate.exists() else None


@pytest.fixture(scope="module")
def run_js(tmp_path_factory):
    node = _node_binary()
    if node is None:
        pytest.skip("no node available -- `pip install -e \".[dev]\"` provides one")
    workspace = tmp_path_factory.mktemp("logos-reader-js")
    (workspace / "package.json").write_text('{"type": "module"}')
    for name in _MODULES:
        shutil.copy(_JS_DIR / name, workspace / name)

    def run(body: str, payload=None):
        script = workspace / "driver.js"
        script.write_text(_PREAMBLE % json.dumps(payload) + body)
        done = subprocess.run(
            [node, str(script)], capture_output=True, text=True, timeout=60, check=False,
        )
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)

    return run


def _doc(*blocks):
    return {"version": 1, "type": "doc", "content": list(blocks)}


def _para(*content, node_id="p1"):
    return {"type": "paragraph", "id": node_id, "content": list(content)}


# -- what the renderer refuses ------------------------------------------------


def test_prose_becomes_text_not_markup(run_js):
    """A chapter containing "<script>" is a chapter that reads "<script>"."""
    tree = run_js(
        "emit(renderDocument(INPUT, nodes));",
        _doc(_para({"type": "text", "text": "<script>alert(1)</script>"})),
    )

    (paragraph,) = tree["children"]
    assert paragraph["tag"] == "p"
    assert paragraph["children"] == [
        {"tag": "#text", "value": "<script>alert(1)</script>"}
    ]


@pytest.mark.parametrize(
    "href,expected",
    [
        ("https://example.test/a", "https://example.test/a"),
        ("http://example.test/a", "http://example.test/a"),
        ("/inside/the/site", "/inside/the/site"),
        ("javascript:alert(1)", None),
        ("JavaScript:alert(1)", None),
        ("data:text/html;base64,PHN2Zz4=", None),
        ("vbscript:msgbox", None),
        # Passes the server's leading-slash rule while meaning somewhere else.
        ("//evil.test/steal", None),
        ("", None),
        (None, None),
    ],
)
def test_only_http_https_and_site_relative_urls_survive(run_js, href, expected):
    assert run_js("emit(safeHref(INPUT));", href) == expected


def test_a_link_the_reader_will_not_follow_degrades_to_its_own_words(run_js):
    tree = run_js(
        "emit(renderDocument(INPUT, nodes));",
        _doc(_para({"type": "link", "href": "javascript:alert(1)", "text": "click me"})),
    )

    # Not a dead <a>, and not dropped: the sentence still reads.
    assert tree["children"][0]["children"] == [{"tag": "#text", "value": "click me"}]


def test_an_offsite_link_opens_away_and_cannot_reach_back(run_js):
    tree = run_js(
        "emit(renderDocument(INPUT, nodes));",
        _doc(_para({"type": "link", "href": "https://example.test", "text": "source"})),
    )

    link = tree["children"][0]["children"][0]
    assert link["tag"] == "a"
    assert link["attrs"] == {
        "href": "https://example.test",
        "target": "_blank",
        "rel": "noopener noreferrer",
    }


def test_a_site_relative_link_stays_in_the_tab(run_js):
    tree = run_js(
        "emit(renderDocument(INPUT, nodes));",
        _doc(_para({"type": "link", "href": "/timeline/books/x", "text": "the book"})),
    )

    assert tree["children"][0]["children"][0]["attrs"] == {"href": "/timeline/books/x"}


@pytest.mark.parametrize(
    "document",
    [
        _doc({"type": "raw_html", "id": "x", "content": []}),
        _doc({"type": "heading", "id": "h", "level": 9, "content": []}),
        _doc(_para({"type": "text", "text": "x", "marks": [{"type": "blink"}]})),
        _doc(_para({"type": "iframe", "src": "x"})),
        _doc({"type": "bullet_list", "id": "l", "content": [{"type": "paragraph"}]}),
        _doc(_para({"type": "text", "text": 7})),
        {"version": 2, "type": "doc", "content": []},
        {"version": 1, "type": "not-a-doc", "content": []},
    ],
)
def test_anything_the_reader_does_not_know_fails_closed(run_js, document):
    """A newer writer must not be guessed at -- the page says so instead."""
    assert run_js("emit(caught(() => renderDocument(INPUT, nodes)));", document) == [
        "RenderError", True,
    ]


# -- what it renders ----------------------------------------------------------


def test_marks_nest_and_block_ids_travel_with_the_node(run_js):
    tree = run_js(
        "emit(renderDocument(INPUT, nodes));",
        _doc(_para(
            {"type": "text", "text": "loud", "marks": [{"type": "strong"}, {"type": "em"}]},
            node_id="opening",
        )),
    )

    (paragraph,) = tree["children"]
    assert paragraph["attrs"] == {"data-block-id": "opening"}
    outer = paragraph["children"][0]
    assert outer["tag"] == "em"
    assert outer["children"][0]["tag"] == "strong"
    assert outer["children"][0]["children"] == [{"tag": "#text", "value": "loud"}]


def test_headings_start_below_the_page_and_section_titles(run_js):
    tree = run_js(
        "emit(renderDocument(INPUT, nodes).children.map((n) => n.tag));",
        _doc(*[
            {"type": "heading", "id": f"h{n}", "level": n,
             "content": [{"type": "text", "text": "T"}]}
            for n in (1, 2, 3)
        ]),
    )

    assert tree == ["h3", "h4", "h5"]


def test_lists_and_breaks_render(run_js):
    tree = run_js(
        "emit(renderDocument(INPUT, nodes));",
        _doc({
            "type": "ordered_list",
            "id": "l",
            "content": [{
                "type": "list_item",
                "content": [
                    {"type": "text", "text": "one"},
                    {"type": "hard_break"},
                ],
            }],
        }),
    )

    (ordered,) = tree["children"]
    assert ordered["tag"] == "ol"
    (item,) = ordered["children"]
    assert item["tag"] == "li"
    assert [child["tag"] for child in item["children"]] == ["#text", "br"]


def test_akasha_references_stay_prose_in_every_mode(run_js):
    """Full View's one exception is Chronos scenes. A character chip here
    would quietly make that promise false, so a mention is its own words."""
    tree = run_js(
        "emit(renderDocument(INPUT, nodes));",
        _doc(_para(
            {"type": "mention", "text": "Lyra",
             "ref": {"database": "ember", "collection": "characters", "id": "lyra"}},
            {"type": "article_link", "text": "Highkeep",
             "ref": {"database": "ember", "collection": "locations", "id": "highkeep"}},
        )),
    )

    assert tree["children"][0]["children"] == [
        {"tag": "#text", "value": "Lyra"},
        {"tag": "#text", "value": "Highkeep"},
    ]


# -- preferences --------------------------------------------------------------


def test_unknown_choices_fall_back_and_focused_is_the_default(run_js):
    assert run_js(
        "emit([parsePreferences(INPUT), parsePreferences(undefined), DEFAULTS]);",
        {"mode": "peek", "typeface": "comic", "align": "justify", "future": True},
    ) == [
        {"mode": "focused", "flow": "continuous", "typeface": "serif", "leading": "normal",
         "measure": "medium", "align": "justify"},
        {"mode": "focused", "flow": "continuous", "typeface": "serif", "leading": "normal",
         "measure": "medium", "align": "left"},
        {"mode": "focused", "flow": "continuous", "typeface": "serif", "leading": "normal",
         "measure": "medium", "align": "left"},
    ]


def test_full_view_is_never_reached_by_accident(run_js):
    """Every route to the mode has to be *asked* for; nothing defaults to it."""
    assert run_js(
        "emit([showsChronos({}), showsChronos({mode: 'peek'}), showsChronos(null),"
        " showsChronos({mode: 'full'}), otherMode('focused'), otherMode('full')]);"
    ) == [False, False, False, True, "full", "focused"]


def test_a_patch_merges_over_what_is_stored(run_js):
    assert run_js(
        "const backing = {};"
        "const s = store(backing);"
        "writePreferences(s, {typeface: 'sans'});"
        "const merged = writePreferences(s, {mode: 'full'});"
        "emit([merged, JSON.parse(backing['logos-reader-preferences'])]);"
    ) == [
        {"mode": "full", "flow": "continuous", "typeface": "sans", "leading": "normal",
         "measure": "medium", "align": "left"},
    ] * 2


def test_reset_restores_the_display_and_leaves_the_reading_mode_alone(run_js):
    """The header owns theme and text size, so reset here cannot reach them --
    and the mode is a place you are, not a display choice."""
    assert run_js(
        "emit(resetDisplay(INPUT));",
        {"mode": "full", "flow": "continuous", "typeface": "sans", "leading": "relaxed",
         "measure": "wide", "align": "justify"},
    ) == {
        "mode": "full", "flow": "continuous", "typeface": "serif",
        "leading": "normal", "measure": "medium", "align": "left",
    }


def test_a_storage_that_refuses_still_reads(run_js):
    """Private browsing throws on every touch. Show the prose anyway."""
    assert run_js(
        "emit([readPreferences(sealed), writePreferences(sealed, {mode: 'full'})]);"
    ) == [
        {"mode": "focused", "flow": "continuous", "typeface": "serif", "leading": "normal",
         "measure": "medium", "align": "left"},
        {"mode": "full", "flow": "continuous", "typeface": "serif", "leading": "normal",
         "measure": "medium", "align": "left"},
    ]


def test_corrupt_storage_reads_as_defaults(run_js):
    assert run_js(
        "emit(readPreferences(store({'logos-reader-preferences': 'not json'})));"
    ) == {"mode": "focused", "flow": "continuous", "typeface": "serif", "leading": "normal",
          "measure": "medium", "align": "left"}


def test_the_display_fields_are_every_choice_but_the_mode(run_js):
    """The settings dialog is driven off this list, so its order is the order
    the rows appear in -- and `mode` must stay out of it: the mode is a button
    in the toolbar, not a row in a dialog."""
    assert run_js("emit(DISPLAY_FIELDS);") == [
        "flow", "typeface", "leading", "measure", "align",
    ]


# -- moving between sections and volumes --------------------------------------


def test_the_pager_stops_at_both_ends(run_js):
    """Both pagers share this. A "next" on the last section that reloads the
    same section is the bug, and it is invisible until you reach the end."""
    assert run_js(
        "const rows = [{id: 'a'}, {id: 'b'}, {id: 'c'}];"
        "emit([neighbours(rows, 'a'), neighbours(rows, 'b'), neighbours(rows, 'c'),"
        " neighbours(rows, 'ghost'), neighbours([], 'a'), neighbours(undefined, 'a')]);"
    ) == [
        {"previous": None, "next": {"id": "b"}},
        {"previous": {"id": "a"}, "next": {"id": "c"}},
        {"previous": {"id": "b"}, "next": None},
        {"previous": None, "next": None},
        {"previous": None, "next": None},
        {"previous": None, "next": None},
    ]


def test_a_lone_section_has_no_neighbours_either_way(run_js):
    assert run_js("emit(neighbours([{id: 'only'}], 'only'));") == {
        "previous": None, "next": None,
    }


def test_sections_are_named_for_the_contents_and_the_heading(run_js):
    """An untitled prologue must not read as a blank line in the contents."""
    assert run_js(
        "emit(["
        "sectionName({kind: 'chapter', number: 4, title: 'The Harbour Exchange'}),"
        "sectionName({kind: 'chapter', number: 4, title: null}),"
        "sectionName({kind: 'prologue'}),"
        "sectionName({kind: 'glossary', title: ''}),"
        "sectionLabel({kind: 'chapter', number: 12}),"
        "sectionLabel({kind: 'epilogue'})]);"
    ) == [
        "The Harbour Exchange", "Chapter 4", "Prologue", "Glossary",
        "Chapter 12", "Epilogue",
    ]
