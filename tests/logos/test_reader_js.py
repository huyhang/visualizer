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
_MODULES = (
    "dom.js", "prose.js", "preferences.js", "navigation.js", "outline.js",
    "position.js", "progress.js", "boundary.js", "readerdata.js",
    "editor.js", "comparison.js", "recovery.js", "coachpanel.js",
    "akashapanel.js", "contextmenu.js", "draftstate.js",
)

_PREAMBLE = """\
import { RenderError, renderDocument, safeHref } from "./prose.js";
import {
  DEFAULTS, DISPLAY_FIELDS, otherMode, parsePreferences, readPreferences,
  resetDisplay, showsChronos, writePreferences,
} from "./preferences.js";
import {
  findSection, neighbours, readingOrder, sectionAhead, sectionLabel, sectionName,
  sectionNeighbours,
} from "./navigation.js";
import {
  advance, blockAnchor, forgetPosition, parsePositions, prunePositions,
  readPosition, readPositions, scrollForAnchor, storePosition, writePosition,
} from "./position.js";
import { sectionProgress, scrollForProgress } from "./progress.js";
import { boundaryGesture } from "./boundary.js";
import { bookmarkAt, bookmarks, dataForSection, removeItem, replaceItem } from "./readerdata.js";
import { nodeFactory as createNodes } from "./dom.js";
import {
  defaultOpenVolume, filterOutline, pageForSection, SECTION_PAGE_SIZE,
  sectionCount, sectionPage,
} from "./outline.js";
import {
  documentFromEditor, mentionRef, unlinkMention, wordCount as editorWordCount,
} from "./editor.js";
import { compareDocuments, draftStats } from "./comparison.js";
import { createAutosave, recoveryKey } from "./recovery.js";
import { createCoachPanel } from "./coachpanel.js";
import { createAkashaPanel } from "./akashapanel.js";
import { menuPosition } from "./contextmenu.js";
import { createDraftState } from "./draftstate.js";

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


def test_a_fragment_ignores_optional_children(run_js):
    """Book contents has optional notices and resume cards; absent ones are
    not DOM nodes and must not be handed to appendChild."""
    assert run_js(
        "const appended = [];"
        "const owner = {createDocumentFragment: () => ({"
        " appendChild: (node) => {"
        "  if (node === null || node === undefined) throw new TypeError('not a Node');"
        "  appended.push(node);"
        " }"
        "})};"
        "createNodes(owner).fragment([{id: 1}, null, undefined, {id: 2}]);"
        "emit(appended);"
    ) == [{"id": 1}, {"id": 2}]


def test_draft_comparison_aligns_stable_blocks_and_reports_flow_stats(run_js):
    left = _doc(_para({"type": "text", "text": "The gate opened."}, node_id="a"))
    right = _doc(
        _para({"type": "text", "text": "The gate opened slowly."}, node_id="a"),
        _para({"type": "text", "text": "Lyra entered."}, node_id="b"),
    )

    result = run_js(
        "emit({comparison: compareDocuments(INPUT.left, INPUT.right), stats: draftStats(INPUT.right)});",
        {"left": left, "right": right},
    )

    assert [row["status"] for row in result["comparison"]["rows"]] == [
        "changed", "added"
    ]
    assert result["stats"] == {
        "words": 6, "paragraphs": 2, "sentences": 2,
        "averageSentenceWords": 3,
    }


def test_the_two_word_counts_agree_on_lists(run_js):
    """One document, one answer.

    The comparison view's statistics and the editor's live count are separate
    walkers over the same structure. They drifted on lists -- comparison joined
    list items with nothing, so a three-item list read as one word and the
    compare dialog contradicted the header beside it.
    """
    document = {
        "version": 1,
        "type": "doc",
        "content": [
            _para({"type": "text", "text": "The gate opened."}),
            {
                "type": "ordered_list", "id": "list", "content": [
                    {"type": "list_item", "content": [{"type": "text", "text": "alpha"}]},
                    {"type": "list_item", "content": [{"type": "text", "text": "beta"}]},
                    {"type": "list_item", "content": [{"type": "text", "text": "gamma"}]},
                ],
            },
        ],
    }

    result = run_js(
        "emit({editor: editorWordCount(INPUT), compare: draftStats(INPUT).words});",
        document,
    )

    assert result == {"editor": 6, "compare": 6}


_RECORDING_UI = (
    "const ui = {"
    "  el: (tag, attrs = {}, children = []) => ({tag, attrs,"
    "    children: children.flat().filter(Boolean), remove() {}}),"
    "  fill: (node, children) => { node.children = children.flat().filter(Boolean); return node; },"
    "};"
)


def test_renaming_a_draft_updates_the_open_copy_and_the_listing_row(run_js):
    """The bug this state object exists to make unrepeatable.

    The open draft and its row in the listing are separate reads; the selector
    renders from the rows, so a rename that touched only the open copy showed
    the old name until autosave came back.
    """
    result = run_js(
        "const state = createDraftState({"
        "  sectionRev: 4,"
        "  drafts: [{id: 'a', name: 'First', primary: true},"
        "           {id: 'b', name: 'Second', primary: false}],"
        "  current: {id: 'b', name: 'Second', primary: false, rev: 2}});"
        "state.renamed('Taut pass');"
        "emit({options: state.options(), open: state.current.name});"
    )

    assert result["open"] == "Taut pass"
    assert result["options"] == [
        {"value": "a", "text": "First (Primary)", "current": False},
        {"value": "b", "text": "Taut pass", "current": True},
    ]


def test_promoting_moves_the_primary_flag_off_every_other_draft(run_js):
    result = run_js(
        "const state = createDraftState({"
        "  sectionRev: 4,"
        "  drafts: [{id: 'a', name: 'First', primary: true},"
        "           {id: 'b', name: 'Second', primary: false}],"
        "  current: {id: 'b', name: 'Second', primary: false, rev: 2}});"
        "state.promoted(9);"
        "emit({options: state.options(), rev: state.sectionRev,"
        "  open: state.current.primary});"
    )

    assert result["rev"] == 9
    assert result["open"] is True
    assert [option["text"] for option in result["options"]] == [
        "First", "Second (Primary)",
    ]


def test_a_saved_draft_replaces_the_open_copy_and_refreshes_its_row(run_js):
    result = run_js(
        "const state = createDraftState({"
        "  sectionRev: 4,"
        "  drafts: [{id: 'b', name: 'Second', primary: false, word_count: 10}],"
        "  current: {id: 'b', name: 'Second', primary: false, rev: 2}});"
        "state.saved({id: 'b', name: 'Second', primary: false, rev: 3,"
        "  word_count: 66, section_rev: 7});"
        "state.sectionChanged(8);"
        "emit({rev: state.current.rev, rowWords: state.rows[0].word_count,"
        "  sectionRev: state.sectionRev, count: state.count});"
    )

    assert result == {"rev": 3, "rowWords": 66, "sectionRev": 8, "count": 1}


def test_the_akasha_panel_reports_an_empty_result_and_a_failure_apart(run_js):
    result = run_js(
        _RECORDING_UI
        + "const body = {children: []};"
        "const seen = [];"
        "const panel = createAkashaPanel({body, ui, focus: () => seen.push('focus'),"
        "  search: async () => ({entities: []})});"
        "await panel.showLookup({text: 'Aldric', block: 'p1'}, {});"
        "const empty = body.children.map((c) => [c.attrs.class, c.attrs.text]);"
        "const failing = createAkashaPanel({body, ui, focus: () => {},"
        "  search: async () => { throw new Error('Akasha is down'); }});"
        "await failing.showLookup({text: 'Aldric', block: 'p1'}, {});"
        "emit({seen, empty, failed: body.children.map((c) => [c.attrs.class, c.attrs.text])});"
    )

    assert result["seen"] == ["focus"]
    assert result["empty"] == [["muted", "No readable Akasha entity matched."]]
    assert result["failed"] == [["form-error", "Akasha is down"]]


def test_linking_is_offered_only_when_the_selection_sits_in_one_block(run_js):
    result = run_js(
        _RECORDING_UI
        + "const entity = {title: 'Sir Aldric', database_title: 'Ember',"
        "  collection_title: 'Characters', fields: [{name: 'Role', value: 'Knight'}]};"
        "const linked = [];"
        "async function render(selection) {"
        "  const body = {children: []};"
        "  const panel = createAkashaPanel({body, ui, focus: () => {},"
        "    search: async () => ({entities: [entity]})});"
        "  await panel.showLookup(selection, {onOpen: () => {},"
        "    onLink: (e) => linked.push(e.title)});"
        "  const actions = body.children[0].children.find((c) => c.attrs.class === 'entity-actions');"
        "  return actions.children[0];"
        "}"
        "const inBlock = await render({text: 'Sir Aldric', block: 'p1'});"
        "const across = await render({text: 'Sir Aldric', block: null});"
        "inBlock.attrs.onclick();"
        "emit({inBlock: inBlock.attrs.disabled, across: across.attrs.disabled,"
        "  acrossTitle: across.attrs.title, linked});"
    )

    assert result["inBlock"] is False
    assert result["across"] is True
    assert result["acrossTitle"] == "Select within one paragraph to link"
    assert result["linked"] == ["Sir Aldric"]


def test_the_context_menu_stays_inside_the_viewport(run_js):
    result = run_js(
        "const menu = {width: 200, height: 120};"
        "const viewport = {width: 1000, height: 700};"
        "emit({"
        "  middle: menuPosition({x: 400, y: 300}, menu, viewport),"
        "  bottomRight: menuPosition({x: 990, y: 690}, menu, viewport),"
        "  topLeft: menuPosition({x: 0, y: 0}, menu, viewport)});"
    )

    assert result["middle"] == {"left": 400, "top": 300}
    assert result["bottomRight"] == {"left": 792, "top": 572}
    assert result["topLeft"] == {"left": 8, "top": 8}


def test_the_coach_panel_applies_a_suggestion_and_can_undo_it(run_js):
    """The panel is a pure renderer over injected seams.

    Extracted from `mountWriter` so this path is reachable at all: applying a
    suggestion, then undoing it, without a browser or a network.
    """
    result = run_js(
        # A recording stand-in for the element builders and the prose surface.
        "const made = [];"
        "const ui = {"
        "  el: (tag, attrs = {}, children = []) => {"
        "    const node = {tag, attrs, children: children.flat().filter(Boolean),"
        "      remove() { node.removed = true; }};"
        "    made.push(node); return node;"
        "  },"
        "  fill: (node, children) => { node.children = children.flat().filter(Boolean); return node; },"
        "};"
        "const body = {children: []};"
        "const calls = [];"
        "const prose = {"
        "  snapshot: () => ({version: 1, marker: 'before'}),"
        "  restore: (doc) => calls.push(['restore', doc.marker]),"
        "  replaceIn: (block, from, to) => { calls.push(['replace', block, from, to]); return true; },"
        "  reveal: (block) => calls.push(['reveal', block]),"
        "};"
        "let dialect = 'en-GB'; const ignored = new Set();"
        "const preferences = {"
        "  dialect: () => dialect,"
        "  setDialect: (value) => { dialect = value; },"
        "  isIgnored: (title) => ignored.has(title),"
        "  ignore: (title) => ignored.add(title),"
        "};"
        "const issues = ["
        "  {block: 'p1', category: 'spelling', title: 'US spelling',"
        "   message: 'm', excerpt: 'color', replacement: 'colour'},"
        "  {block: 'p2', category: 'flow', title: 'Long sentence',"
        "   message: 'm', excerpt: 'x', replacement: null},"
        "];"
        "const seen = [];"
        "const panel = createCoachPanel({body, ui, prose, preferences,"
        "  requestReview: async (chosen) => { seen.push(chosen); return {issues}; }});"
        "await panel.review();"
        "const cards = body.children.filter((c) => c.attrs.class === 'coach-issue');"
        "const actions = cards[0].children.find((c) => c.attrs.class === 'coach-actions');"
        "const use = actions.children[0];"
        "use.attrs.onclick();"
        "const undo = cards[0].children.find((c) => c.attrs && c.attrs.text === 'Undo');"
        "undo.attrs.onclick();"
        "emit({dialectAsked: seen, cards: cards.length,"
        "  firstAction: use.attrs.text, calls});"
    )

    assert result["dialectAsked"] == ["en-GB", "en-GB"]
    assert result["cards"] == 2
    assert result["firstAction"] == "Use “colour”"
    assert result["calls"] == [
        ["replace", "p1", "color", "colour"],
        ["restore", "before"],
    ]


def test_the_coach_panel_hides_rules_the_writer_has_ignored(run_js):
    result = run_js(
        "const ui = {"
        "  el: (tag, attrs = {}, children = []) => ({tag, attrs,"
        "    children: children.flat().filter(Boolean), remove() {}}),"
        "  fill: (node, children) => { node.children = children.flat().filter(Boolean); return node; },"
        "};"
        "const body = {children: []};"
        "const ignored = new Set(['Long sentence']);"
        "const panel = createCoachPanel({body, ui,"
        "  prose: {snapshot: () => ({}), restore() {}, replaceIn: () => true, reveal() {}},"
        "  preferences: {dialect: () => 'en-US', setDialect() {},"
        "    isIgnored: (t) => ignored.has(t), ignore: (t) => ignored.add(t)},"
        "  requestReview: async () => ({issues: ["
        "    {block: 'p1', category: 'flow', title: 'Long sentence',"
        "     message: 'm', excerpt: 'x', replacement: null}]})});"
        "await panel.review();"
        "emit(body.children.map((c) => c.attrs.class));"
    )

    assert "coach-issue" not in result
    assert "coach-clear" in result


def test_a_linked_phrase_can_be_unlinked_without_touching_its_words(run_js):
    """Unlinking keeps the prose and drops only the Akasha reference."""
    result = run_js(
        "const text = (value) => ({nodeType: 3, nodeValue: value});"
        "const owner = {createTextNode: text};"
        "const span = {nodeType: 1, tagName: 'SPAN', ownerDocument: owner,"
        " textContent: 'Sir Aldric', dataset: {entityType: 'mention',"
        " database: 'ember', collection: 'characters', entityId: 'aldric'}};"
        "const parent = {childNodes: [span],"
        " replaceChild(fresh, old) { this.childNodes = [fresh]; }};"
        "span.parentNode = parent;"
        "const ref = mentionRef(span);"
        "const done = unlinkMention(span);"
        "emit({ref, done, left: parent.childNodes[0].nodeValue});"
    )

    assert result["done"] is True
    assert result["left"] == "Sir Aldric"
    assert result["ref"] == {
        "type": "mention", "database": "ember", "collection": "characters",
        "id": "aldric", "text": "Sir Aldric",
    }


def test_editor_word_count_includes_mentions_and_lists(run_js):
    payload = {
        "version": 1,
        "type": "doc",
        "content": [
            _para({
                "type": "mention",
                "text": "Lyra Venn",
                "ref": {"database": "ember", "collection": "people", "id": "lyra"},
            }),
            {
                "type": "bullet_list", "id": "list", "content": [
                    {"type": "list_item", "content": [{"type": "text", "text": "went home"}]}
                ],
            },
        ],
    }
    assert run_js("emit(editorWordCount(INPUT));", payload) == 4


def test_editor_serialization_preserves_marks_mentions_and_block_ids(run_js):
    result = run_js(
        "const text = (value) => ({nodeType: 3, nodeValue: value});"
        "const element = (tagName, children, dataset = {}, attributes = {}) => ({"
        " nodeType: 1, tagName, dataset, childNodes: children,"
        " children: children.filter((child) => child.nodeType === 1),"
        " matches: (selector) => selector === '[data-entity-id]' && Boolean(dataset.entityId),"
        " getAttribute: (name) => attributes[name] || null"
        "});"
        "const bold = element('STRONG', [text('bold')]);"
        "const mention = element('SPAN', [text('Lyra')], {"
        " entityId: 'lyra', entityType: 'mention', database: 'ember', collection: 'characters'"
        "});"
        "const paragraph = element('P', [bold, text(' met '), mention], {blockId: 'p1'});"
        "const root = {childNodes: [paragraph]};"
        "emit(documentFromEditor(root, () => 'unused'));"
    )

    assert result == {
        "version": 1,
        "type": "doc",
        "content": [{
            "type": "paragraph",
            "id": "p1",
            "content": [
                {"type": "text", "text": "bold", "marks": [{"type": "strong"}]},
                {"type": "text", "text": " met "},
                {
                    "type": "mention",
                    "ref": {
                        "database": "ember", "collection": "characters", "id": "lyra"
                    },
                    "text": "Lyra",
                },
            ],
        }],
    }


def test_recovery_keys_are_scoped_to_account_and_draft(run_js):
    result = run_js(
        "emit([recoveryKey(INPUT), recoveryKey({...INPUT, draft: 'other'})]);",
        {"user": "mara", "book": "ember pact", "volume": "one", "section": "gate", "draft": "first"},
    )
    assert result[0] != result[1]
    assert "ember%20pact" in result[0]


def test_autosave_keeps_the_latest_snapshot_while_a_save_is_running(run_js):
    result = run_js(
        "const saved = []; const states = []; let release;"
        "const gate = new Promise((resolve) => { release = resolve; });"
        "const autosave = createAutosave({delay: 1, saveLocal: () => {},"
        " saveRemote: async (value) => { saved.push(value); if (value === 1) await gate; },"
        " onState: (value) => states.push(value)});"
        "autosave.schedule(1); await new Promise((r) => setTimeout(r, 5));"
        "autosave.schedule(2); release(); await new Promise((r) => setTimeout(r, 10));"
        "emit({saved, pending: autosave.hasPending(), states});"
    )
    assert result["saved"] == [1, 2]
    assert result["pending"] is False
    assert result["states"][-1] == "saved"


def test_autosave_keeps_a_conflicting_snapshot_for_recovery(run_js):
    result = run_js(
        "const states = [];"
        "const autosave = createAutosave({delay: 1, saveLocal: () => {},"
        " saveRemote: async () => { throw {status: 409}; },"
        " onState: (value) => states.push(value)});"
        "autosave.schedule({text: 'mine'}); await autosave.flush();"
        "emit({pending: autosave.hasPending(), states});"
    )
    assert result["pending"] is True
    assert result["states"][-1] == "conflict"


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
    assert paragraph["attrs"] == {
        "data-block-id": "opening",
        "data-block-type": "paragraph",
    }
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

    assert tree == ["h2", "h3", "h4"]


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
        {"mode": "focused", "typeface": "serif", "leading": "normal",
         "measure": "medium", "align": "justify"},
        {"mode": "focused", "typeface": "serif", "leading": "normal",
         "measure": "medium", "align": "left"},
        {"mode": "focused", "typeface": "serif", "leading": "normal",
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
        {"mode": "full", "typeface": "sans", "leading": "normal",
         "measure": "medium", "align": "left"},
    ] * 2


def test_reset_restores_the_display_and_leaves_the_reading_mode_alone(run_js):
    """The header owns theme and text size, so reset here cannot reach them --
    and the mode is a place you are, not a display choice."""
    assert run_js(
        "emit(resetDisplay(INPUT));",
        {"mode": "full", "typeface": "sans", "leading": "relaxed",
         "measure": "wide", "align": "justify"},
    ) == {
        "mode": "full", "typeface": "serif",
        "leading": "normal", "measure": "medium", "align": "left",
    }


def test_a_storage_that_refuses_still_reads(run_js):
    """Private browsing throws on every touch. Show the prose anyway."""
    assert run_js(
        "emit([readPreferences(sealed), writePreferences(sealed, {mode: 'full'})]);"
    ) == [
        {"mode": "focused", "typeface": "serif", "leading": "normal",
         "measure": "medium", "align": "left"},
        {"mode": "full", "typeface": "serif", "leading": "normal",
         "measure": "medium", "align": "left"},
    ]


def test_corrupt_storage_reads_as_defaults(run_js):
    assert run_js(
        "emit(readPreferences(store({'logos-reader-preferences': 'not json'})));"
    ) == {"mode": "focused", "typeface": "serif", "leading": "normal",
          "measure": "medium", "align": "left"}


def test_the_display_fields_are_every_choice_but_the_mode(run_js):
    """The settings dialog is driven off this list, so its order is the order
    the rows appear in -- and `mode` must stay out of it: the mode is a button
    in the toolbar, not a row in a dialog."""
    assert run_js("emit(DISPLAY_FIELDS);") == [
        "typeface", "leading", "measure", "align",
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


def test_section_navigation_crosses_volume_boundaries(run_js):
    manuscript = {
        "volumes": [
            {"id": "one", "title": "One", "sections": [{"id": "same"}]},
            {"id": "two", "title": "Two", "sections": [
                {"id": "same"}, {"id": "last"},
            ]},
        ]
    }
    assert run_js(
        "emit([readingOrder(INPUT).map((e) => [e.volume.id, e.section.id]),"
        " findSection(INPUT, 'two', 'same').volume.title,"
        " sectionNeighbours(INPUT, 'two', 'same')]);",
        manuscript,
    ) == [
        [["one", "same"], ["two", "same"], ["two", "last"]],
        "Two",
        {
            "previous": {
                "section": {"id": "same"},
                "volume": {"id": "one", "title": "One", "sections": [{"id": "same"}]},
            },
            "next": {
                "section": {"id": "last"},
                "volume": {
                    "id": "two", "title": "Two",
                    "sections": [{"id": "same"}, {"id": "last"}],
                },
            },
        },
    ]


def test_outline_search_matches_section_metadata_and_volume_titles(run_js):
    manuscript = {
        "volumes": [
            {
                "id": "one", "number": 1, "title": "Beginnings",
                "sections": [
                    {"id": "before", "kind": "prologue", "number": None,
                     "title": None},
                    {"id": "gate", "kind": "chapter", "number": 1,
                     "title": "The Broken Gate"},
                ],
            },
            {
                "id": "two", "number": 2, "title": "The Long Road",
                "sections": [
                    {"id": "harbour", "kind": "chapter", "number": 2,
                     "title": "Harbour Exchange"},
                ],
            },
        ]
    }
    assert run_js(
        "const ids = (query) => filterOutline(INPUT, query)"
        " .map((v) => [v.id, v.sections.map((s) => s.id)]);"
        "emit([ids(''), ids('chapter 2'), ids('long road'), ids('PROLOGUE'),"
        " ids('missing'), sectionCount(filterOutline(INPUT, 'chapter'))]);",
        manuscript,
    ) == [
        [["one", ["before", "gate"]], ["two", ["harbour"]]],
        [["two", ["harbour"]]],
        [["two", ["harbour"]]],
        [["one", ["before"]]],
        [],
        2,
    ]


def test_default_volume_is_the_resume_volume_or_the_first(run_js):
    manuscript = {
        "volumes": [
            {"id": "one", "sections": [{"id": "opening"}]},
            {"id": "two", "sections": [{"id": "ending"}]},
        ]
    }
    assert run_js(
        "emit([defaultOpenVolume(INPUT, {volume: 'two', section: 'ending'}),"
        " defaultOpenVolume(INPUT, {volume: 'two', section: 'gone'}),"
        " defaultOpenVolume(INPUT, null), defaultOpenVolume({volumes: []}, null)]);",
        manuscript,
    ) == ["two", "one", "one", None]


def test_long_section_lists_are_split_at_the_configured_threshold(run_js):
    assert run_js(
        "const sections = Array.from({length: 58}, (_, n) => ({id: `s${n + 1}`}));"
        "const view = (requested) => { const p = sectionPage(sections, requested);"
        " return {page: p.page, pages: p.pages, start: p.start, end: p.end,"
        " first: p.sections[0].id, last: p.sections.at(-1).id}; };"
        "emit([SECTION_PAGE_SIZE, view(0), view(1), view(99), view(-4),"
        " pageForSection(sections, 's26'), pageForSection(sections, 's58'),"
        " pageForSection(sections, 'missing')]);"
    ) == [
        25,
        {"page": 0, "pages": 3, "start": 0, "end": 25,
         "first": "s1", "last": "s25"},
        {"page": 1, "pages": 3, "start": 25, "end": 50,
         "first": "s26", "last": "s50"},
        {"page": 2, "pages": 3, "start": 50, "end": 58,
         "first": "s51", "last": "s58"},
        {"page": 0, "pages": 3, "start": 0, "end": 25,
         "first": "s1", "last": "s25"},
        1,
        2,
        0,
    ]


# -- position persistence and progress ---------------------------------------


def test_positions_are_isolated_by_account_and_book(run_js):
    assert run_js(
        "const backing = {}; const s = store(backing);"
        "writePosition(s, 'mara', 'ember',"
        " {volume: 'one', section: 'opening', block: 'p4', offset: 12, progress: .42});"
        "writePosition(s, 'mara', 'other',"
        " {volume: 'two', section: 'end', block: null, offset: 0, progress: 2});"
        "emit([readPosition(s, 'mara', 'ember'), readPosition(s, 'mara', 'other'),"
        " readPosition(s, 'devi', 'ember'), Object.keys(backing).sort()]);"
    ) == [
        {
            "last": {"volume": "one", "section": "opening", "block": "p4",
                     "offset": 12, "progress": .42},
            "furthest": {"volume": "one", "section": "opening", "progress": .42},
        },
        {
            "last": {"volume": "two", "section": "end", "block": None,
                     "offset": 0, "progress": 1},
            "furthest": {"volume": "two", "section": "end", "progress": 1},
        },
        None,
        ["logos-reader-positions:mara"],
    ]


def test_a_server_position_can_replace_the_local_cache(run_js):
    assert run_js(
        "const backing = {}; const s = store(backing);"
        "const saved = storePosition(s, 'mara', 'ember', {"
        " last: {volume: 'v', section: 's', block: 'p', offset: 2, progress: .3},"
        " furthest: {volume: 'v', section: 's', progress: .8}});"
        "emit([saved, readPosition(s, 'mara', 'ember')]);"
    ) == [{
        "last": {"volume": "v", "section": "s", "block": "p", "offset": 2,
                 "progress": .3},
        "furthest": {"volume": "v", "section": "s", "progress": .8},
    }] * 2


def test_a_record_written_before_there_were_two_marks_still_reads(run_js):
    """The v1 shape was a bare spot. It is where the reader was *and* the best
    evidence of how far they got, so it seeds both marks rather than being
    dropped -- an upgrade must not lose somebody's place."""
    assert run_js(
        "emit(readPosition(store({'logos-reader-positions:mara': JSON.stringify("
        " {version: 1, books: {ember: {volume: 'one', section: 'ch4',"
        "  block: 'p9', offset: 30, progress: .6}}})}), 'mara', 'ember'));"
    ) == {
        "last": {"volume": "one", "section": "ch4", "block": "p9",
                 "offset": 30, "progress": .6},
        "furthest": {"volume": "one", "section": "ch4", "progress": .6},
    }


def test_a_book_id_that_is_an_object_property_is_not_a_phantom_position(run_js):
    assert run_js(
        "emit([readPosition(store({}), 'mara', 'toString'),"
        " readPosition(store({}), 'mara', 'constructor')]);"
    ) == [None, None]


def test_bad_or_unavailable_position_storage_fails_open(run_js):
    assert run_js(
        "emit([parsePositions(null), parsePositions({version: 9, books: {x: {}}}),"
        " readPositions(store({'logos-reader-positions:mara': 'bad'}), 'mara'),"
        " readPositions(sealed, 'mara'),"
        " writePosition(sealed, 'mara', 'b',"
        "  {volume: 'v', section: 's', block: null, offset: 0, progress: .1})]);"
    ) == [
        {"version": 1, "books": {}},
        {"version": 1, "books": {}},
        {"version": 1, "books": {}},
        {"version": 1, "books": {}},
        {
            "last": {"volume": "v", "section": "s", "block": None,
                     "offset": 0, "progress": .1},
            "furthest": {"volume": "v", "section": "s", "progress": .1},
        },
    ]


def test_stale_positions_can_be_pruned_or_forgotten(run_js):
    assert run_js(
        "const backing = {}; const s = store(backing);"
        "for (const book of ['keep', 'lost']) writePosition(s, 'mara', book,"
        " {volume: 'v', section: 's', block: null, offset: 0, progress: .2});"
        "prunePositions(s, 'mara', ['keep']);"
        "const pruned = readPositions(s, 'mara');"
        "forgetPosition(s, 'mara', 'keep');"
        "emit([pruned, readPositions(s, 'mara')]);"
    ) == [
        {"version": 1, "books": {
            "keep": {
                "last": {"volume": "v", "section": "s", "block": None,
                         "offset": 0, "progress": .2},
                "furthest": {"volume": "v", "section": "s", "progress": .2},
            },
        }},
        {"version": 1, "books": {}},
    ]


def test_a_stable_block_anchor_round_trips_its_scroll_position(run_js):
    assert run_js(
        "const anchor = blockAnchor(["
        " {id: 'p1', top: 100}, {id: 'p2', top: 350}, {id: 'p3', top: 700}], 410);"
        "emit([anchor, scrollForAnchor(350, anchor.offset, 96),"
        " blockAnchor([], 410)]);"
    ) == [
        {"block": "p2", "offset": 60},
        314,
        {"block": None, "offset": 0},
    ]


def test_section_progress_tracks_the_current_viewport(run_js):
    assert run_js(
        "const at = (scrollY) => sectionProgress("
        " {top: 200, height: 1400, viewportHeight: 600, scrollY});"
        "emit([at(0), at(200), at(600), at(1000), at(1400),"
        " sectionProgress({top: 200, height: 500, viewportHeight: 600, scrollY: 0}),"
        " scrollForProgress({top: 200, height: 1400, viewportHeight: 600}, .5)]);"
    ) == [0, 0, .5, 1, 1, 1, 600]


# -- how far you got, as against where you are --------------------------------


BOOK_ORDER = {
    "volumes": [
        {"id": "one", "sections": [{"id": "a"}, {"id": "b"}]},
        {"id": "two", "sections": [{"id": "c"}]},
    ]
}


def test_book_order_decides_what_counts_as_further_on(run_js):
    """Across volumes as well as within one, and never for an id the
    manuscript no longer has -- a deleted section must not be able to claim
    it is ahead of everything."""
    assert run_js(
        "const ahead = (f, s) => sectionAhead(INPUT, f, s);"
        "const at = (volume, section) => ({volume, section});"
        "emit([ahead(at('one', 'b'), at('one', 'a')),"
        " ahead(at('one', 'a'), at('one', 'b')),"
        " ahead(at('one', 'a'), at('one', 'a')),"
        " ahead(at('two', 'c'), at('one', 'b')),"
        " ahead(at('one', 'b'), at('two', 'c')),"
        " ahead(at('gone', 'a'), at('one', 'a')),"
        " ahead(at('one', 'gone'), at('one', 'a')),"
        " ahead(null, at('one', 'a')), ahead(at('one', 'b'), null)]);",
        BOOK_ORDER,
    ) == [True, False, False, True, False, False, False, False, False]


def test_looking_back_cannot_lose_the_way_forward(run_js):
    """Skipping ahead moves the mark; going back to re-read leaves it where it
    was, so "Continue reading" still offers the furthest point. Within one
    section the deeper read wins, so reopening it at the top cannot regress."""
    assert run_js(
        "const mark = (section, progress) =>"
        " ({volume: 'one', section, progress});"
        "emit([advance(null, mark('a', .3), false),"
        " advance(mark('a', .3), mark('b', .1), true),"
        " advance(mark('b', .1), mark('a', .9), false),"
        " advance(mark('a', .2), mark('a', .7), false),"
        " advance(mark('a', .7), mark('a', .2), false),"
        " advance(mark('a', .4), {volume: '', section: ''}, true)]);"
    ) == [
        {"volume": "one", "section": "a", "progress": .3},
        {"volume": "one", "section": "b", "progress": .1},
        {"volume": "one", "section": "b", "progress": .1},
        {"volume": "one", "section": "a", "progress": .7},
        {"volume": "one", "section": "a", "progress": .7},
        {"volume": "one", "section": "a", "progress": .4},
    ]


def test_where_you_are_still_moves_when_how_far_you_got_does_not(run_js):
    """The whole point of two marks: re-reading chapter one keeps the anchor
    that reopens chapter one, without dragging the Continue target back."""
    assert run_js(
        "const backing = {}; const s = store(backing);"
        "writePosition(s, 'mara', 'ember',"
        " {volume: 'two', section: 'c', block: 'p2', offset: 5, progress: .8}, true);"
        "const back = writePosition(s, 'mara', 'ember',"
        " {volume: 'one', section: 'a', block: 'p1', offset: 9, progress: .1}, false);"
        "emit([back.last, back.furthest]);"
    ) == [
        {"volume": "one", "section": "a", "block": "p1", "offset": 9, "progress": .1},
        {"volume": "two", "section": "c", "progress": .8},
    ]


# -- private reader data and boundary navigation ----------------------------


def test_private_items_are_selected_by_section_and_kind(run_js):
    items = [
        {"id": "n", "kind": "note", "volume": "v", "section": "s", "block": "p"},
        {"id": "b", "kind": "bookmark", "volume": "v", "section": "s", "block": "p"},
        {"id": "cs", "kind": "checklist", "scope": "section", "volume": "v", "section": "s"},
        {"id": "cb", "kind": "checklist", "scope": "book"},
        {"id": "other", "kind": "note", "volume": "v", "section": "else", "block": "p"},
    ]
    assert run_js(
        "const found = dataForSection(INPUT, 'v', 's');"
        "emit([Object.fromEntries(Object.entries(found).map(([k,v]) => [k, v.map(i => i.id)])),"
        " bookmarkAt(INPUT, 'v', 's', 'p').id, bookmarks(INPUT).map(i => i.id),"
        " replaceItem(INPUT, {id: 'n', kind: 'note', text: 'new'}).find(i => i.id === 'n').text,"
        " removeItem(INPUT, 'n').some(i => i.id === 'n')]);",
        items,
    ) == [
        {"notes": ["n"], "bookmarks": ["b"], "sectionChecklist": ["cs"],
         "bookChecklist": ["cb"]},
        "b", ["b"], "new", False,
    ]


def test_boundary_navigation_needs_sustained_input_at_the_matching_edge(run_js):
    assert run_js(
        "const g = boundaryGesture({threshold: 100, windowMs: 500});"
        "emit(["
        " g.push({delta: 40, atStart: false, atEnd: true, now: 0}),"
        " g.push({delta: 61, atStart: false, atEnd: true, now: 100}),"
        " g.reset(),"
        " g.push({delta: -80, atStart: true, atEnd: false, now: 200}),"
        " g.reset(),"
        " g.push({delta: -100, atStart: true, atEnd: false, now: 300})]);"
    ) == [
        {"direction": "next", "progress": .4, "trigger": None},
        {"direction": "next", "progress": 1, "trigger": "next"},
        {"direction": None, "progress": 0, "trigger": None},
        {"direction": "previous", "progress": .8, "trigger": None},
        {"direction": None, "progress": 0, "trigger": None},
        {"direction": "previous", "progress": 1, "trigger": "previous"},
    ]
