"""``dateUnits`` — the browser's half of the date vocabulary, run under node.

The scene form generates one input per calendar unit, and it has to agree with
the server about what those units are and how far each counts. That agreement is
the only thing in the browser that could silently disagree with ``unit_table``
in calendar.py, so it is worth a test that actually runs the JavaScript.

Everything *arithmetic* stays on the server (see ``api.resolveDates``), which is
why this is the whole of the browser's calendar knowledge: naming and ranges,
no odometer.

Node comes from the ``nodejs-wheel-binaries`` dev dependency, or the PATH; see
test_graph_js.py, whose harness this mirrors.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from visualizer.chronos.calendar import unit_table

_JS_DIR = Path(__file__).resolve().parents[2] / "src" / "visualizer" / "chronos" / "static" / "js"

HOURS = {
    "base_unit": "hour",
    "cycles": [
        {"name": "day", "size": 24},
        {"name": "month", "size": 30},
        {"name": "year", "size": 12},
    ],
    "epoch_label": "AF",
}


def _node_binary():
    found = shutil.which("node")
    if found:
        return found
    try:
        import nodejs_wheel  # optional: only the JS tests need it
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
    workspace = tmp_path_factory.mktemp("dates-js")
    (workspace / "package.json").write_text('{"type": "module"}')
    # calendars.js is pure -- no DOM, no api -- so it needs no shim.
    shutil.copy(_JS_DIR / "calendars.js", workspace / "calendars.js")

    def run(body: str, payload=None):
        script = workspace / "driver.js"
        script.write_text(
            'import { calendarHint, calendarProblems, dateUnits, descriptorFrom, '
            'draftFrom, tickName } from "./calendars.js";\n'
            f"const INPUT = {json.dumps(payload if payload is not None else {})};\n"
            "const emit = (value) => console.log(JSON.stringify(value));\n"
            + body
        )
        done = subprocess.run(
            [node, str(script)], capture_output=True, text=True, timeout=60, check=False,
        )
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)

    return run


# -- what the form offers ------------------------------------------------------


def test_units_are_offered_largest_first(run_js):
    """The order a date is said in, which is the reverse of how cycles nest."""
    got = run_js("emit(dateUnits(INPUT).map((u) => u.name));", HOURS)
    assert got == ["year", "month", "day", "hour"]


def test_the_browser_agrees_with_the_server_about_every_unit(run_js):
    """The one thing here that could drift. If ``unit_table`` ever changes shape,
    a form built from the old one would offer boxes the API refuses."""
    got = run_js("emit(dateUnits(INPUT));", HOURS)
    expected = [
        {"name": unit.name, "min": unit.origin,
         "max": None if unit.limit is None else unit.origin + unit.limit - 1}
        for unit in unit_table(["day", "month", "year"], [24, 30, 12], "hour")
    ]
    assert got == expected
    # Said plainly, so a silent reversal cannot pass the check above:
    assert got[0] == {"name": "year", "min": 1, "max": None}
    assert got[-1] == {"name": "hour", "min": 0, "max": 23}


def test_the_top_cycle_is_open_ended(run_js):
    """A story is free to run past Year 12 -- and back before Year 1."""
    assert run_js("emit(dateUnits(INPUT)[0].max);", HOURS) is None


def test_a_shallow_calendar_still_yields_a_date(run_js):
    got = run_js("emit(dateUnits(INPUT));",
                 {"base_unit": "day", "cycles": [{"name": "year", "size": 365}]})
    assert got == [{"name": "year", "min": 1, "max": None},
                   {"name": "day", "min": 0, "max": 364}]


# -- when there is no date to offer --------------------------------------------


@pytest.mark.parametrize("descriptor", [None, {"kind": "identity"},
                                        {"base_unit": "tick", "cycles": []}])
def test_a_book_without_a_calendar_offers_no_date_fields(run_js, descriptor):
    """An empty list is the form's signal to stay on ticks -- which are already
    the plainest thing to type when there is nothing to translate them into."""
    assert run_js("emit(dateUnits(INPUT));", descriptor) == []


def test_a_calendar_naming_two_units_alike_offers_no_date_fields(run_js):
    """Matching the server, which refuses such a date because it could not say
    which unit was meant. A browser that offered the boxes anyway would collect
    a date the save then rejected."""
    muddled = {"base_unit": "cycle",
               "cycles": [{"name": "cycle", "size": 10}, {"name": "age", "size": 10}]}
    assert run_js("emit(dateUnits(INPUT));", muddled) == []


def test_the_plain_language_hint_is_unchanged(run_js):
    """The existing reading of a descriptor still stands beside the new fields."""
    assert run_js("emit(calendarHint(INPUT));", HOURS) == (
        "Ticks are hours: 24 hours to a day, 30 days to a month, 12 months to a year."
    )


# -- Earth ---------------------------------------------------------------------


@pytest.mark.parametrize("tick_unit,names", [
    ("day", ["year", "month", "day"]),
    ("hour", ["year", "month", "day", "hour"]),
    ("minute", ["year", "month", "day", "hour", "minute"]),
    ("week", []),
])
def test_earths_date_boxes_follow_the_precision_it_was_created_at(run_js, tick_unit, names):
    got = run_js("emit(dateUnits(INPUT).map((u) => u.name));",
                 {"kind": "gregorian", "tick_unit": tick_unit})
    assert got == names


def test_earths_year_box_carries_an_era_and_no_ceiling(run_js):
    """A year that counts backwards needs somewhere to say so. Without the flag
    the only spelling left is a minus sign, and `-43` is not how anyone writes
    44 BCE."""
    year = run_js("emit(dateUnits(INPUT)[0]);", {"kind": "gregorian", "tick_unit": "day"})
    assert year == {"name": "year", "min": 1, "max": None, "era": True}


def test_no_other_calendar_offers_an_era(run_js):
    units = run_js("emit(dateUnits(INPUT));", HOURS)
    assert all("era" not in unit for unit in units)


def test_the_hint_for_earth_never_claims_a_month_length(run_js):
    hint = run_js("emit(calendarHint(INPUT));", {"kind": "gregorian", "tick_unit": "day"})
    assert "28, 29, 30 or 31" in hint
    assert "Ticks are days" in hint


def test_earth_survives_a_trip_through_the_library_editors_draft(run_js):
    """`draftFrom` falls back to a fantasy preset for anything with no cycles.
    Earth has none, so without its own branch, opening an Earth calendar in the
    editor and pressing Save would rewrite it as thirty-day months -- silently,
    with nothing on screen to say the book's dates had just changed."""
    descriptor = {"kind": "gregorian", "tick_unit": "minute"}
    assert run_js("emit(descriptorFrom(draftFrom(INPUT)));", descriptor) == descriptor


def test_an_invented_calendar_still_survives_the_same_trip(run_js):
    assert run_js("emit(descriptorFrom(draftFrom(INPUT)));", HOURS) == {
        "base_unit": "hour", "epoch_label": "AF",
        "cycles": [{"name": "day", "size": 24}, {"name": "month", "size": 30},
                   {"name": "year", "size": 12}],
    }


@pytest.mark.parametrize("tick_unit,problems", [
    ("day", []),
    ("week", ["Choose whether one tick is a day, an hour or a minute."]),
])
def test_an_earth_draft_has_only_its_precision_to_get_wrong(run_js, tick_unit, problems):
    got = run_js("emit(calendarProblems(INPUT));",
                 {"kind": "gregorian", "tickUnit": tick_unit})
    assert got == problems


@pytest.mark.parametrize("calendar,unit", [
    ({"kind": "gregorian", "tick_unit": "hour"}, "hour"),
    (HOURS, "hour"),
    ({"kind": "identity"}, "tick"),
    (None, "tick"),
])
def test_a_span_is_counted_in_whatever_one_tick_is_called(run_js, calendar, unit):
    assert run_js("emit(tickName(INPUT));", calendar) == unit


# -- the timing section, driven for real -------------------------------------
#
# `sceneTiming` holds one timeframe in two spellings, and only one is on screen
# at a time. Nothing else in the suite can see whether they agree: the Python
# tests never run JavaScript, and the checks above are over pure functions that
# never build a form. So the harness below stands up the real module against a
# fake DOM and a stand-in server, and drives the toggle the way a writer does.
#
# The stand-in implements exactly the two endpoints the form calls, with the
# same span/components rules as calendar.py -- a lenient stub would let a
# desynced form pass.

_FAKE_DOM = r"""
const mk = (tag) => ({
  tag, attrs: {}, children: [], listeners: {}, className: "", dataset: {},
  textContent: "", value: "", checked: false, hidden: false,
  appendChild(c) { this.children.push(c); return c; },
  removeChild(c) { this.children.splice(this.children.indexOf(c), 1); return c; },
  get firstChild() { return this.children[0] || null; },
  // A browser seeds a text input's `.value` from its `value` attribute, which
  // is how every `textInput` in these modules gets its starting text. Without
  // this the harness reads them all as empty and quietly disagrees with the
  // page. (Not true of select/textarea -- and `el(…, {value})` on those is
  // banned outright; see test_ui_assets.)
  setAttribute(k, v) {
    this.attrs[k] = String(v);
    if (k === "value") this.value = String(v);
  },
  addEventListener(k, fn) { (this.listeners[k] ||= []).push(fn); },
  // Class selectors only -- the one descendant selector in these modules runs
  // solely when a cycle row is focused, which nothing here does.
  querySelectorAll(sel) {
    return walk(this, (n) => n.className === sel.replace(/^\./, ""));
  },
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; },
});
globalThis.document = {
  createElement: mk,
  createElementNS: (ns, t) => mk(t),
  createTextNode: (v) => ({ tag: "#text", textContent: v, children: [] }),
};

export const HOURS = { base_unit: "hour",
  cycles: [{name:"day",size:24},{name:"month",size:30},{name:"year",size:12}] };
export const CALENDARS = [{ id: "imperial", label: "Imperial", descriptor: HOURS }];

// The server, as far as the form is concerned. Same arithmetic as calendar.py.
const PLACE = { hour: 1, day: 24, month: 720, year: 8640 };
const components = (t) => {
  let v = t;
  const h = ((v % 24) + 24) % 24; v = Math.floor(v / 24);
  const d = ((v % 30) + 30) % 30; v = Math.floor(v / 30);
  const m = ((v % 12) + 12) % 12; const y = Math.floor(v / 12);
  return { year: y + 1, month: m + 1, day: d + 1, hour: h };
};
const span = (o) => {
  const t = (o.year - 1) * PLACE.year + ((o.month || 1) - 1) * PLACE.month
          + ((o.day || 1) - 1) * PLACE.day + (o.hour || 0);
  const finest = o.hour !== undefined ? "hour" : o.day !== undefined ? "day"
               : o.month !== undefined ? "month" : "year";
  return [t, t + PLACE[finest]];
};
const row = (t) => ({ tick: t, label: `L${t}`, parts: [`L${t}`],
                      components: components(t), readings: [] });
export const calls = [];
globalThis.fetch = async (url, opts) => {
  calls.push(url);
  if (url.includes("/ui/ticks")) {
    const ticks = [...new URL("http://x" + url).searchParams.getAll("tick")].map(Number);
    return { ok: true, status: 200, json: async () => ({ ticks: ticks.map(row) }) };
  }
  const b = JSON.parse(opts.body);
  const s = span(b.start_date)[0], e = span(b.end_date)[1];
  return { ok: true, status: 200,
           json: async () => ({ start_tick: s, end_tick: e, ticks: [row(s), row(e)] }) };
};

// -- driving the form --------------------------------------------------------
export const settle = () => new Promise((r) => setTimeout(r, 80));
const walk = (n, pred, out = []) => {
  if (pred(n)) out.push(n);
  (n.children || []).forEach((c) => walk(c, pred, out));
  return out;
};
export const inputs = (node, cls) =>
  walk(node, (n) => n.tag === "input" && (cls ? n.className === cls : true));
export const dateBoxes = (node) => inputs(node, "date-part");
export const tickBoxes = (node) => inputs(node).filter((n) => n.className !== "date-part"
                                                           && n.attrs.type !== "radio");
// Click a toggle segment the way a writer would: check it, uncheck its sibling,
// then fire the change listener the module registered.
export const chooseMode = async (node, value) => {
  const radios = inputs(node).filter((n) => n.attrs.type === "radio");
  for (const r of radios) r.checked = r.attrs.value === value;
  const picked = radios.find((r) => r.attrs.value === value);
  for (const fn of picked.listeners.change || []) await fn();
  await settle();
};
// Set a control the way a writer does: the value, then the listener the module
// registered for it. Setting `.value` alone changes nothing a module can see.
export const fire = async (node, kind = "input") => {
  for (const fn of node.listeners[kind] || []) await fn();
  await settle();
};
export const eraBoxes = (node) =>
  walk(node, (n) => n.tag === "select" && n.className === "date-era");
export const type = (boxes, values) => {
  boxes.forEach((b, i) => { b.value = values[i] === undefined ? "" : String(values[i]); });
};
"""

_FORM_PREAMBLE = (
    'import { HOURS, CALENDARS, settle, dateBoxes, tickBoxes, chooseMode, type as fill,'
    ' eraBoxes, fire, inputs } from "./harness.js";\n'
    'import { sceneTiming } from "./scenetiming.js";\n'
    'import { calendarField, inlineCalendarEditor } from "./calendarfield.js";\n'
    'import { dateFields } from "./datefields.js";\n'
    "const emit = (value) => console.log(JSON.stringify(value));\n"
)

_FORM_MODULES = (
    "scenetiming.js", "calendarfield.js", "datefields.js", "calendars.js",
    "dom.js", "api.js",
)


@pytest.fixture(scope="module")
def run_form(tmp_path_factory):
    node = _node_binary()
    if node is None:
        pytest.skip("no node available -- `pip install -e \".[dev]\"` provides one")
    workspace = tmp_path_factory.mktemp("sceneform-js")
    (workspace / "package.json").write_text('{"type": "module"}')
    (workspace / "harness.js").write_text(_FAKE_DOM)
    for name in _FORM_MODULES:
        shutil.copy(_JS_DIR / name, workspace / name)

    def run(body: str):
        script = workspace / "driver.js"
        script.write_text(_FORM_PREAMBLE + body)
        done = subprocess.run(
            [node, str(script)], capture_output=True, text=True, timeout=60, check=False,
        )
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)

    return run


def test_a_date_typed_then_switched_to_ticks_is_not_lost(run_form):
    """The defect this test exists for. The two spellings are one timeframe, and
    only one is on screen -- so a writer who types a date, flips to Tick and
    saves must get *that* date's ticks, not whatever the tick boxes held when
    the form opened."""
    got = run_form("""
      const t = sceneTiming("b", { calendars: CALENDARS, calendarId: "imperial",
                                   event: { start_tick: 0, end_tick: 24 } });
      await settle();
      fill(dateBoxes(t.node), [3, 4, 12, 0, 3, 4, 12, 0]);   // Year 3, Month 4, Day 12
      await chooseMode(t.node, "tick");
      emit({ ticks: tickBoxes(t.node).map((b) => b.value), saved: t.timeframe() });
    """)
    assert got["ticks"] == ["19704", "19705"], "the tick boxes kept their opening values"
    assert got["saved"]["body"] == {"start_tick": 19704, "end_tick": 19705}


def test_ticks_typed_then_switched_to_dates_are_not_lost(run_form):
    """And the same going the other way."""
    got = run_form("""
      const t = sceneTiming("b", { calendars: CALENDARS, calendarId: "imperial",
                                   event: { start_tick: 0, end_tick: 24 } });
      await settle();
      await chooseMode(t.node, "tick");     // the writer switches, then types
      fill(tickBoxes(t.node), [19704, 19728]);
      await chooseMode(t.node, "date");
      emit({ dates: dateBoxes(t.node).map((b) => b.value), saved: t.timeframe() });
    """)
    # The end box shows the last tick *inside* the scene, so it round-trips.
    assert got["dates"] == ["3", "4", "12", "0", "3", "4", "12", "23"]
    assert got["saved"]["body"] == {
        "start_date": {"year": 3, "month": 4, "day": 12, "hour": 0},
        "end_date": {"year": 3, "month": 4, "day": 12, "hour": 23},
    }


def test_clearing_the_dates_then_switching_unschedules_rather_than_reverting(run_form):
    """Emptying the date boxes means "I do not know when this happens". Flipping
    to Tick must not resurrect the ticks the scene had when it opened."""
    got = run_form("""
      const t = sceneTiming("b", { calendars: CALENDARS, calendarId: "imperial",
                                   event: { start_tick: 240, end_tick: 264 } });
      await settle();
      fill(dateBoxes(t.node), []);          // every box emptied
      await chooseMode(t.node, "tick");
      emit({ ticks: tickBoxes(t.node).map((b) => b.value), saved: t.timeframe() });
    """)
    assert got["ticks"] == ["", ""]
    assert got["saved"]["body"] == {"start_tick": None, "end_tick": None}


# -- the two forms Earth touches ----------------------------------------------

_EARTH = '{kind: "gregorian", tick_unit: "day"}'
_EARTH_HOURS = '{kind: "gregorian", tick_unit: "hour"}'
_LIBRARY = (
    'const entry = (descriptor) => [{owner: "mara", id: "earth", rev: 2,'
    ' qualified_id: "mara/earth", name: "Earth", descriptor}];\n'
    'const source = {owner: "mara", calendar: "earth", rev: 2};\n'
)


def test_the_library_editor_hands_back_the_earth_calendar_it_was_given(run_form):
    """The live half of the draft round trip: not the pure function, but the
    editor a writer actually opens an existing calendar in."""
    got = run_form(f"""
      const editor = inlineCalendarEditor({{initial: {_EARTH_HOURS}}});
      emit({{value: editor.value(), problems: editor.problems()}});
    """)
    assert got == {"value": {"kind": "gregorian", "tick_unit": "hour"}, "problems": []}


def test_the_library_editor_still_hands_back_an_invented_calendar(run_form):
    got = run_form("""
      const editor = inlineCalendarEditor({initial: HOURS});
      emit(editor.value());
    """)
    assert got == {
        "base_unit": "hour", "epoch_label": "",
        "cycles": [{"name": "day", "size": 24}, {"name": "month", "size": 30},
                   {"name": "year", "size": 12}],
    }


def test_the_book_form_asks_where_this_story_meets_earth(run_form):
    """An Earth calendar with nowhere to stand cannot date anything, so the
    form says so before the save does."""
    got = run_form(f"""
      {_LIBRARY}
      const field = calendarField({{
        initial: {_EARTH}, source, library: entry({_EARTH}),
      }});
      emit({{origin: field.origin(), problems: field.problems()}});
    """)
    assert got == {
        "origin": None,
        "problems": ["Say which Earth date this book's tick 0 fell on."],
    }


def test_the_book_form_gives_back_the_origin_it_was_opened_with(run_form):
    got = run_form(f"""
      {_LIBRARY}
      const field = calendarField({{
        initial: {_EARTH_HOURS}, source, library: entry({_EARTH_HOURS}),
        origin: "2024-02-27T06:00-08:00",
      }});
      emit({{origin: field.origin(), problems: field.problems()}});
    """)
    assert got == {"origin": "2024-02-27T06:00-08:00", "problems": []}


def test_an_invented_calendar_is_never_asked_for_an_origin(run_form):
    got = run_form("""
      const library = [{owner: "mara", id: "imperial", rev: 1, name: "Imperial",
                        qualified_id: "mara/imperial", descriptor: HOURS}];
      const field = calendarField({
        initial: HOURS, source: {owner: "mara", calendar: "imperial", rev: 1}, library,
      });
      emit({origin: field.origin(), problems: field.problems()});
    """)
    assert got == {"origin": None, "problems": []}


def test_a_year_before_1_is_typed_as_an_era_rather_than_a_minus_sign(run_form):
    """The whole reason the era control exists. What crosses the wire is still
    the plain integer every other calendar sends -- 44 BCE is the year `-43`."""
    got = run_form(f"""
      {_LIBRARY}
      const field = calendarField({{
        initial: {_EARTH}, source, library: entry({_EARTH}),
      }});
      const boxes = dateBoxes(field.node);
      fill(boxes, [44, 3, 15]);
      eraBoxes(field.node)[0].value = "BCE";
      await fire(boxes[0]);
      emit({{origin: field.origin(), problems: field.problems()}});
    """)
    assert got == {"origin": "-0043-03-15", "problems": []}


def test_an_origin_read_back_shows_the_era_rather_than_the_negative_year(run_form):
    got = run_form(f"""
      {_LIBRARY}
      const field = calendarField({{
        initial: {_EARTH}, source, library: entry({_EARTH}), origin: "-0043-03-15",
      }});
      emit({{
        boxes: dateBoxes(field.node).map((b) => b.value),
        era: eraBoxes(field.node)[0].value,
        origin: field.origin(),
      }});
    """)
    assert got == {"boxes": ["44", "3", "15"], "era": "BCE", "origin": "-0043-03-15"}


def test_a_half_typed_origin_is_reported_rather_than_quietly_completed(run_form):
    """An origin is the one date that may not name a period: defaulting the
    blank boxes to the first of January would anchor the book somewhere the
    writer never said."""
    got = run_form(f"""
      {_LIBRARY}
      const field = calendarField({{
        initial: {_EARTH}, source, library: entry({_EARTH}), origin: "2024-02-27",
      }});
      const boxes = dateBoxes(field.node);
      fill(boxes, [2024, "", ""]);
      await fire(boxes[0]);
      emit({{origin: field.origin(), problems: field.problems()}});
    """)
    assert got["origin"] is None
    assert got["problems"] == ["Say which Earth date this book's tick 0 fell on."]


def test_an_offset_that_is_not_fixed_is_refused_before_the_save(run_form):
    got = run_form(f"""
      {_LIBRARY}
      const field = calendarField({{
        initial: {_EARTH_HOURS}, source, library: entry({_EARTH_HOURS}),
        origin: "2024-02-27T06:00Z",
      }});
      const offset = inputs(field.node).find((n) => n.className !== "date-part");
      offset.value = "Europe/London";
      await fire(offset);
      emit(field.problems());
    """)
    assert got == ["Use Z for UTC, or a fixed offset like -08:00."]
