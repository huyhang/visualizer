"""prefs.js: the theme button steps through light, paper and dark.

Run under node against a small fake of the few browser objects it touches, so
the cycle, what the button says and what a stale saved value does are pinned
without a browser.
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[2] / "src" / "visualizer"
_PREFS = _SRC / "static" / "js" / "prefs.js"

# Just enough of a browser for prefs.js: storage, a <html> with attributes, two
# buttons that remember their click handler, and matchMedia.
_FAKE = """
const stored = JSON.parse(process.argv[2]);
const dark = process.argv[3] === "dark";
const attrs = {};
const buttons = {};
const button = (id) => (buttons[id] = {
  title: "", attrs: {}, click: null,
  setAttribute(k, v) { this.attrs[k] = v; },
  addEventListener(type, fn) { if (type === "click") this.click = fn; },
});
button("theme-toggle"); button("font-toggle");
globalThis.localStorage = {
  getItem: (k) => (k in stored ? stored[k] : null),
  setItem: (k, v) => { stored[k] = String(v); },
};
globalThis.window = { matchMedia: () => ({ matches: dark }) };
globalThis.CustomEvent = class { constructor(type, init) { this.type = type; this.detail = init && init.detail; } };
globalThis.document = {
  readyState: "complete",
  documentElement: {
    style: {},
    setAttribute: (k, v) => { attrs[k] = v; },
    getAttribute: (k) => (k in attrs ? attrs[k] : null),
  },
  getElementById: (id) => buttons[id] || null,
  addEventListener: () => {},
  dispatchEvent: () => {},
};
"""

_REPORT = """
const seen = [{ theme: attrs["data-theme"], title: buttons["theme-toggle"].title }];
for (let i = 0; i < 3; i++) {
  buttons["theme-toggle"].click();
  seen.push({ theme: attrs["data-theme"], title: buttons["theme-toggle"].title });
}
console.log(JSON.stringify({ seen, saved: stored["visualizer-theme"] }));
"""


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


@pytest.fixture(scope="module")
def press(tmp_path_factory):
    """Load prefs.js with ``stored`` in localStorage, press the theme button
    three times, and report each theme in turn and what was saved."""
    node = _node_binary()
    if node is None:
        pytest.skip("no node available -- `pip install -e \".[dev]\"` provides one")
    driver = tmp_path_factory.mktemp("prefs-js") / "driver.cjs"
    driver.write_text(_FAKE + _PREFS.read_text() + _REPORT)

    def run(stored: dict, system: str = "light") -> dict:
        done = subprocess.run(
            [node, str(driver), json.dumps(stored), system],
            capture_output=True, text=True, timeout=60, check=False,
        )
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)

    return run


def test_the_button_steps_light_paper_dark_and_back(press):
    got = press({"visualizer-theme": "light"})
    assert [s["theme"] for s in got["seen"]] == ["light", "paper", "dark", "light"]
    assert got["saved"] == "light"


def test_the_button_says_which_theme_is_on(press):
    got = press({"visualizer-theme": "paper"})
    assert [s["title"] for s in got["seen"]] == [
        "Theme: Paper", "Theme: Dark", "Theme: Light", "Theme: Paper",
    ]


def test_paper_is_remembered(press):
    got = press({"visualizer-theme": "paper"})
    assert got["seen"][0]["theme"] == "paper"


@pytest.mark.parametrize(("system", "expected"), [("light", "light"), ("dark", "dark")])
def test_an_unknown_saved_theme_counts_as_none_chosen(press, system, expected):
    """A name no page knows would paint nothing at all; the system's wins."""
    got = press({"visualizer-theme": "sepia"}, system)
    assert got["seen"][0]["theme"] == expected


def test_the_sign_in_page_knows_the_same_themes():
    """The sign-in shell decides its theme inline, before prefs.js could; if it
    knew fewer themes than the button offers, paper would turn white there."""
    shell = (_SRC / "auth" / "templates" / "base.html").read_text()
    inline = re.search(r'\[("[a-z]+"(?:, "[a-z]+")*)\]\.indexOf\(saved\)', shell)
    assert inline, "the sign-in page no longer lists the themes it accepts"
    offered = re.findall(r'\{ id: "([a-z]+)"', _PREFS.read_text())
    assert sorted(json.loads(f"[{inline.group(1)}]")) == sorted(offered)
