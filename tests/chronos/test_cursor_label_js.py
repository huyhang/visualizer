"""What the timeline's lens says while it is moving.

The reading under the cursor comes from the book's calendar, which only the
server holds, so it costs a round trip -- and the cursor moves every animation
frame. The policy that reconciles those two facts lives in ``cursorlabel.js``:
keep what is known, ask for what is not, and never let the label change notation
mid-gesture. It used to flip to ``Tick 4821`` on every frame of a scroll and back
to a date a moment after it stopped.

None of that is visible to the rest of the suite. The Python tests never run the
browser code, and the one thing a screenshot would show -- a label flickering
between two notations while the hand moves -- is exactly what a still frame
cannot capture.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_JS_DIR = (
    Path(__file__).resolve().parents[2]
    / "src" / "visualizer" / "chronos" / "static" / "js"
)


def _node_binary():
    found = shutil.which("node")
    if found:
        return found
    try:
        import nodejs_wheel
    except ImportError:
        return None
    executable = "node.exe" if sys.platform == "win32" else "node"
    candidate = Path(nodejs_wheel.__file__).parent / "bin" / executable
    return str(candidate) if candidate.exists() else None


# A `formatTick` the test drives: it records every tick it is asked for, answers
# on a delay the test chooses, and can be told to fail. `minGap: 0` takes the
# rate floor out of the way -- it is asserted on its own, separately.
_HARNESS = """
import { tickLabels } from "./cursorlabel.js";
const emit = (value) => console.log(JSON.stringify(value));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function harness({ seeded = [], answer = (t) => `Day ${t}`, delay = 0, minGap = 0 } = {}) {
  const asked = [];
  const written = [];
  let inFlight = 0;
  let peakInFlight = 0;
  const reading = tickLabels({
    seeded, minGap,
    onLabel: (text) => written.push(text),
    formatTick: async (tick) => {
      asked.push(tick);
      inFlight += 1;
      peakInFlight = Math.max(peakInFlight, inFlight);
      try {
        if (delay) await sleep(delay);
        return answer(tick);
      } finally {
        inFlight -= 1;
      }
    },
  });
  return { reading, asked, written, peak: () => peakInFlight };
}
"""


@pytest.fixture(scope="module")
def run_js(tmp_path_factory):
    node = _node_binary()
    if node is None:
        pytest.skip("no node available -- `pip install -e \".[dev]\"` provides one")
    workspace = tmp_path_factory.mktemp("cursor-label-js")
    (workspace / "package.json").write_text('{"type": "module"}')
    shutil.copy(_JS_DIR / "cursorlabel.js", workspace / "cursorlabel.js")

    def run(body, payload=None):
        script = workspace / "driver.js"
        script.write_text(
            _HARNESS + f"const INPUT = {json.dumps(payload or {})};\n" + body
        )
        done = subprocess.run(
            [node, str(script)], capture_output=True, text=True, timeout=60, check=False,
        )
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)

    return run


def test_a_seeded_tick_is_dated_without_asking_anyone(run_js):
    """The timeline payload dates every scene's start and end, so the lens opens
    on a date and crosses a scene's own ticks without a request."""
    got = run_js("""
      const h = harness({ seeded: [[10, "Day 1"], [20, "Day 2"]] });
      h.reading.cursorAt(10);
      h.reading.cursorAt(20);
      await sleep(20);
      emit({ written: h.written, asked: h.asked });
    """)
    assert got == {"written": ["Day 1", "Day 2"], "asked": []}


def test_the_label_never_falls_back_to_a_tick_once_a_date_is_known(run_js):
    """The bug, stated as a test. Moving onto an undated tick must leave the last
    date standing until the real one arrives -- not flash the raw number."""
    got = run_js("""
      const h = harness({ seeded: [[10, "Day 1"]], delay: 30 });
      h.reading.cursorAt(10);
      h.reading.cursorAt(11);   // not seeded: a request goes out
      const midScroll = [...h.written];
      await sleep(80);
      emit({ midScroll, settled: h.written });
    """)
    assert got["midScroll"] == ["Day 1"], (
        f"the lens changed notation mid-scroll: {got['midScroll']}"
    )
    assert got["settled"] == ["Day 1", "Day 11"]
    assert not any(text.startswith("Tick ") for text in got["settled"])


def test_a_lens_that_has_never_had_a_date_shows_the_tick(run_js):
    """The one honest use of the bare number: a book whose scenes carry no
    labels has nothing better to say, and saying nothing would be worse."""
    got = run_js("""
      const h = harness({ delay: 30 });
      h.reading.cursorAt(7);
      const before = [...h.written];
      await sleep(80);
      emit({ before, after: h.written });
    """)
    assert got["before"] == ["Tick 7"]
    assert got["after"] == ["Tick 7", "Day 7"]


def test_only_one_request_is_ever_in_flight(run_js):
    """A scroll is hundreds of cursor positions. Without the single-flight bound
    each one starts a request and they land out of order behind the slow ones."""
    got = run_js("""
      const h = harness({ delay: 20 });
      for (let tick = 0; tick < 40; tick += 1) h.reading.cursorAt(tick);
      await sleep(200);
      emit({ peak: h.peak(), asked: h.asked.length });
    """)
    assert got["peak"] == 1, f"{got['peak']} requests were in flight at once"
    assert got["asked"] < 40, (
        f"every cursor position cost a request ({got['asked']}); the scroll was "
        "not collapsed at all"
    )


def test_the_request_chases_the_cursor_rather_than_the_backlog(run_js):
    """When an answer lands the cursor has moved on, and the *new* position is
    what the next request is worth spending on. Asking for the queue in order
    would spend the whole scroll dating ticks nobody is looking at any more."""
    got = run_js("""
      const h = harness({ delay: 20 });
      h.reading.cursorAt(1);
      h.reading.cursorAt(2);
      h.reading.cursorAt(3);
      h.reading.cursorAt(4);
      await sleep(200);
      emit({ asked: h.asked, written: h.written });
    """)
    assert got["asked"] == [1, 4], f"asked for {got['asked']}, not just where it is"
    # Ticks 2 and 3 are passed through and never asked about. This lens has no
    # date yet, so it tracks the raw tick meanwhile (the previous test); what
    # matters here is that 1's answer is kept but never shown -- the cursor had
    # left by the time it landed -- and that 4's is what ends up on screen.
    assert got["written"][-1] == "Day 4"
    assert "Day 1" not in got["written"], (
        f"an answer for a tick the cursor had left was displayed: {got['written']}"
    )


def test_an_answer_for_a_tick_the_cursor_has_left_is_not_displayed(run_js):
    got = run_js("""
      const h = harness({ seeded: [[9, "Day 9"]], delay: 40 });
      h.reading.cursorAt(1);     // asks for 1
      await sleep(10);
      h.reading.cursorAt(9);     // seeded, so it paints at once
      await sleep(120);
      emit(h.written);
    """)
    assert got[-1] == "Day 9", f"a late answer overwrote the current reading: {got}"


def test_ground_already_covered_is_never_asked_for_twice(run_js):
    got = run_js("""
      const h = harness({ delay: 10 });
      h.reading.cursorAt(5);
      await sleep(60);
      h.reading.cursorAt(6);
      await sleep(60);
      h.reading.cursorAt(5);     // scrolled back
      await sleep(60);
      emit({ asked: h.asked, written: h.written });
    """)
    assert got["asked"] == [5, 6], f"re-asked for a tick it had: {got['asked']}"
    assert got["written"][-1] == "Day 5"


def test_lookups_are_spaced_by_the_rate_floor(run_js):
    """Single-flight alone is not enough: against a fast server an answer returns
    in a millisecond and is immediately re-asked, so one flick of the wheel costs
    hundreds of requests. The floor is what makes the cost of a scroll bounded.
    """
    got = run_js("""
      const h = harness({ minGap: 40, delay: 0 });
      const started = Date.now();
      // A scroll: a new cursor position every few milliseconds for a fifth of
      // a second, which is on the short side for a real one.
      for (let step = 0; step < 40; step += 1) {
        h.reading.cursorAt(100 + step);
        await sleep(5);
      }
      await sleep(80);
      emit({ asked: h.asked.length, elapsed: Date.now() - started });
    """)
    # ~280ms of scrolling at one lookup per 40ms is a handful, not forty.
    assert got["asked"] <= 1 + got["elapsed"] // 40, (
        f"{got['asked']} lookups in {got['elapsed']}ms breaks the 40ms floor"
    )
    assert got["asked"] >= 2, (
        f"only {got['asked']} lookups: the date never moved during the scroll"
    )


def test_a_failed_lookup_leaves_the_reading_alone(run_js):
    """The calendar is a nicety; losing it must not blank the lens or wedge it."""
    got = run_js("""
      const h = harness({
        seeded: [[10, "Day 1"]],
        answer: (tick) => { if (tick === 11) throw new Error("no"); return `Day ${tick}`; },
      });
      h.reading.cursorAt(10);
      h.reading.cursorAt(11);
      await sleep(40);
      h.reading.cursorAt(12);
      await sleep(40);
      emit(h.written);
    """)
    assert got == ["Day 1", "Day 12"], (
        f"a failed lookup should leave the last date up and keep going: {got}"
    )


def test_nothing_in_flight_writes_to_a_stopped_lens(run_js):
    """The view is torn down on navigation while a lookup is still out."""
    got = run_js("""
      const h = harness({ seeded: [[10, "Day 1"]], delay: 30 });
      h.reading.cursorAt(10);
      h.reading.cursorAt(11);
      h.reading.stop();
      await sleep(80);
      emit(h.written);
    """)
    assert got == ["Day 1"], f"a stopped lens was still written to: {got}"
