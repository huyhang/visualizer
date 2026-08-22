"""The map browser, driven in a real browser against the running stack.

pytest covers the pure modules and the JSON routes; what it cannot see is
layout and pointer behaviour. Two things here are worth a real engine:

* **Zoom geometry.** Asserting that a zoom *label* changed proves nothing --
  the drawing can be in a box twenty times too tall and the label still reads
  100%. So this measures the stage and the drawing at every step and requires
  the round trip to close.
* **Draft semantics.** That dragging a pin issues no write until Save, and
  that Discard issues none at all, is only true of the assembled page.

Run it against a stack that is already up::

    docker compose -f docker/docker-compose.nas.yml up --build -d
    docker run --rm --network visualizer_default \\
      -v "$PWD/docker/smoke_prithvi_ui.py:/work/smoke_prithvi_ui.py:ro" -w /work \\
      mcr.microsoft.com/playwright/python:v1.62.0-noble \\
      bash -lc 'pip install -q playwright==1.62.0 && python smoke_prithvi_ui.py'

Mount the one script rather than all of ``docker/``: that directory holds
``.env``, and a browser-test container has no business reading the secret key.
Inside the compose network the app answers to ``app:5000``; override with BASE.
"""

import os
import socket
import sys
from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import sync_playwright


def _dialable(url: str) -> str:
    """Resolve a compose service name, which the browser cannot look up itself."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    try:
        socket.inet_aton(host)
        return url
    except OSError:
        pass
    port = f":{parts.port}" if parts.port else ""
    return urlunsplit((parts.scheme, f"{socket.gethostbyname(host)}{port}", parts.path, "", ""))


BASE = _dialable(os.environ.get("BASE", "http://app:5000"))
USER = os.environ.get("SEED_USER", "mara")
PASSWORD = os.environ.get("SEED_PASSWORD", "ember-pact-demo")

GEOMETRY = """
() => {
  const stage = document.querySelector('#map-stage');
  const svg = stage.querySelector('svg');
  const vb = svg.viewBox.baseVal;
  const m = svg.getScreenCTM();
  const at = (x, y) => { const p = svg.createSVGPoint(); p.x = x; p.y = y;
    const q = p.matrixTransform(m); return {x: q.x, y: q.y}; };
  const tl = at(vb.x, vb.y), br = at(vb.x + vb.width, vb.y + vb.height);
  const box = svg.getBoundingClientRect();
  return {
    label: document.querySelector('#zoom-reset').textContent,
    stageHeight: stage.clientHeight,
    boxHeight: Math.round(box.height),
    drawnHeight: Math.round(br.y - tl.y),
    drawnWidth: Math.round(br.x - tl.x),
  };
}
"""


class Checks:
    def __init__(self):
        self.failures = []
        self.total = 0

    def __call__(self, label, ok, detail=""):
        self.total += 1
        print(f"  [{'ok  ' if ok else 'FAIL'}] {label}{f'  -- {detail}' if detail else ''}")
        if not ok:
            self.failures.append(label)


def login(page):
    page.goto(f"{BASE}/login")
    page.fill("input[name=username]", USER)
    page.fill("input[name=password]", PASSWORD)
    page.click("button[type=submit]")


def open_first_map(page):
    page.goto(f"{BASE}/prithvi/#/")
    page.locator("#world-grid .card").first.click()
    page.locator("#map-grid .card").first.click()
    # Wait for the drawing *and* its pins: measuring before the overlay exists
    # is how a browser check becomes a coin flip.
    page.locator("#map-stage svg").wait_for()
    page.locator(".pin").first.wait_for()


def check_geometry(page, check):
    start = page.evaluate(GEOMETRY)
    check(
        "the drawing fills its box -- no letterboxing to magnify",
        abs(start["boxHeight"] - start["drawnHeight"]) <= 2,
        f"box {start['boxHeight']} vs drawing {start['drawnHeight']}",
    )

    seen = [start]
    for button in ["#zoom-in"] * 4 + ["#zoom-out"] * 4:
        page.click(button)
        page.wait_for_timeout(120)
        seen.append(page.evaluate(GEOMETRY))
    page.click("#zoom-reset")
    page.wait_for_timeout(150)
    end = page.evaluate(GEOMETRY)

    check(
        "the stage stays a fixed viewport at every zoom",
        len({m["stageHeight"] for m in seen}) == 1,
        f"heights {sorted({m['stageHeight'] for m in seen})}",
    )
    check(
        "no zoom step leaves dead space in the box",
        all(abs(m["boxHeight"] - m["drawnHeight"]) <= 2 for m in seen),
        f"worst {max(abs(m['boxHeight'] - m['drawnHeight']) for m in seen)}px",
    )
    check(
        "zooming in then out returns to the starting size",
        abs(end["drawnHeight"] - start["drawnHeight"]) <= 1,
        f"{start['drawnHeight']} -> {end['drawnHeight']}",
    )
    check("reset restores the label", end["label"] == "100%", end["label"])
    peak = max(m["drawnHeight"] for m in seen)
    check(
        "the drawing never exceeds the zoom ceiling",
        peak <= start["drawnHeight"] * 4 + 2,
        f"peak {peak} vs fit {start['drawnHeight']}",
    )


def check_draft(page, check):
    writes = []

    def intercept(route):
        if route.request.method in ("POST", "PUT", "DELETE"):
            writes.append(route.request.method)
            route.fulfill(status=200, content_type="application/json", body="{}")
        else:
            route.continue_()

    page.route("**/pins/**", intercept)

    marker = page.locator(".pin").first
    marker.wait_for()
    box = marker.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] / 2 + 30, box["y"] + box["height"] / 2 + 18, steps=6)
    page.mouse.up()
    page.wait_for_timeout(120)

    check("dragging a pin stages a change", page.locator("#save-changes").is_enabled())
    check("a staged drag writes nothing", not writes, str(writes))

    page.click("#discard-changes")
    page.wait_for_timeout(120)
    check("discard clears the draft", page.locator("#save-changes").is_disabled())
    check("discard writes nothing", not writes, str(writes))

    box = page.locator(".pin").first.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] / 2 + 24, box["y"] + box["height"] / 2 + 12, steps=6)
    page.mouse.up()
    page.wait_for_timeout(120)
    page.click("#save-changes")
    page.wait_for_function(
        "document.querySelector('#dirty-state').textContent === 'No unsaved changes'"
    )
    check("save issues exactly the staged write", writes == ["PUT"], str(writes))
    check(
        "pins are draggable again once saving is done",
        page.locator(".pin.dragging").count() == 0
        and page.locator(".pin").first.is_visible(),
    )
    page.unroute("**/pins/**")


def check_pin_card(page, check):
    page.locator(".pin").first.click()
    page.locator("#pin-preview").wait_for(state="visible")
    title = page.locator("#preview-title").inner_text().strip()
    check("clicking a pin opens its article beside the map", bool(title), title)
    check(
        "the card shows prose, not wikitext",
        "[[" not in page.locator("#preview-excerpt").inner_text(),
    )
    check("the card links into Articles", bool(page.locator("#preview-link").get_attribute("href")))
    check("a writer can remove the selected pin", page.locator("#remove-pin").is_visible())


def check_panning_does_not_place_a_pin(page, check):
    page.locator(".choice").first.wait_for()
    page.locator(".choice").first.click()
    page.locator("#placing").wait_for(state="visible")
    stage = page.locator("#map-stage").bounding_box()
    page.mouse.move(stage["x"] + stage["width"] / 2, stage["y"] + stage["height"] / 2)
    page.mouse.down()
    page.mouse.move(stage["x"] + stage["width"] / 2 - 60, stage["y"] + stage["height"] / 2 - 40, steps=8)
    page.mouse.up()
    page.wait_for_timeout(150)
    check(
        "dragging the map pans instead of placing a pin",
        page.locator("#save-changes").is_disabled(),
    )
    page.click("#cancel-placing")


def check_reader_sees_no_write_controls(page, check):
    """The negative case, without needing a second seeded account.

    The catalog is stubbed to report a world this session may only read, which
    is the one input every write affordance is supposed to hang off. If any of
    them is drawn unconditionally -- the failure mode where a reader is handed
    an editor that only the server refuses -- it shows up here.
    """
    page.route("**/ui/worlds", lambda route: route.fulfill(
        status=200,
        content_type="application/json",
        body=(
            '{"worlds":[{"id":"ember-pact","title":"Ember Pact","map_count":1,'
            '"can_write":false,"can_delete":false}]}'
        ),
    ))
    # A hash-only `goto` does not re-fetch the document, so the catalog would
    # never be requested again and the stub would never be seen. Reload, then
    # confirm the page really is running on the stubbed grants before asserting
    # anything about it -- a check that silently tested the writer again would
    # be worse than no check.
    page.goto(f"{BASE}/prithvi/#/")
    page.reload()
    page.locator("#world-grid .card").first.wait_for()
    stubbed = page.evaluate(
        "async () => (await (await fetch(window.__BASE__ + '/ui/worlds'))"
        ".json()).worlds[0].can_write"
    )
    check("the reader stub is in force", stubbed is False, f"can_write={stubbed}")
    page.locator("#world-grid .card").first.click()
    page.locator("#map-grid .card").first.click()
    page.locator("#map-stage svg").wait_for()
    page.locator(".pin").first.wait_for()

    check("a reader is offered no article picker", page.locator("#picker").is_hidden())
    check("a reader is offered no save bar", page.locator("#edit-bar").is_hidden())
    check("a reader is offered no delete-map button", page.locator("#delete-map").is_hidden())

    page.locator(".pin").first.click()
    page.locator("#pin-preview").wait_for(state="visible")
    check("a reader can still read a pin's article", bool(
        page.locator("#preview-title").inner_text().strip()
    ))
    check("a reader is offered no remove-pin button", page.locator("#remove-pin").is_hidden())

    box = page.locator(".pin").first.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] / 2 + 30, box["y"] + box["height"] / 2 + 20, steps=6)
    page.mouse.up()
    page.wait_for_timeout(120)
    after = page.locator(".pin").first.bounding_box()
    check(
        "a reader cannot drag a pin",
        abs(after["x"] - box["x"]) < 2 and abs(after["y"] - box["y"]) < 2,
    )
    page.unroute("**/ui/worlds")


def main() -> int:
    check = Checks()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 960})
        login(page)
        open_first_map(page)

        print("\ngeometry")
        check_geometry(page, check)
        print("\nthe pin card")
        check_pin_card(page, check)
        print("\nplacing")
        check_panning_does_not_place_a_pin(page, check)
        print("\nthe draft")
        check_draft(page, check)
        print("\nas a reader")
        check_reader_sees_no_write_controls(page, check)

        browser.close()

    print(f"\n{check.total - len(check.failures)}/{check.total} checks passed")
    if check.failures:
        print("failed: " + ", ".join(check.failures))
    return 1 if check.failures else 0


if __name__ == "__main__":
    sys.exit(main())
