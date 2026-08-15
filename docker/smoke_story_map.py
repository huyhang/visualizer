"""Drive the story map in a real browser and say whether it actually works.

The rest of the suite proves the *logic* (tests/chronos/test_graph_js.py runs the
pure modules under node) and the *wiring* (tests/chronos/test_ui_assets.py). What
neither can see is the thing a writer actually looks at: whether the diagram
lays out, whether a scene enlarges in place and pushes the rows below it down,
whether a folded stretch unfolds. That needs a browser.

It runs in the official Playwright image against the already-running stack, so
nothing is installed on the host and the app image is untouched:

    docker run --rm --network visualizer_default \\
      -v "$PWD/docker:/work" -v /tmp/shots:/shots -w /work \\
      mcr.microsoft.com/playwright/python:v1.62.0-noble \\
      bash -lc 'pip install -q playwright==1.62.0 && python smoke_story_map.py'

(The image carries the browsers but not the Python binding, hence the install.)
Inside that network the app answers to `app:5000`; override with BASE. Seed the
book first with `seed_story_map.py`. Screenshots land in /shots.

Exit code is the verdict: 0 if every check passed, 1 otherwise.
"""

import os
import socket
import sys
from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import expect, sync_playwright


def _dialable(url: str) -> str:
    """Swap a compose service name for its address.

    Chromium resolves DNS itself rather than through the C library, and its
    resolver does not consult Docker's embedded server -- so `app:5000` times out
    inside the very network where `curl app:5000` answers. Python's resolver does
    see it, so the name is turned into an address here, once, before the browser
    is ever handed a URL.
    """
    parts = urlsplit(url)
    host = parts.hostname or ""
    try:
        socket.inet_aton(host)
        return url  # already an address
    except OSError:
        pass
    address = socket.gethostbyname(host)
    port = f":{parts.port}" if parts.port else ""
    return urlunsplit((parts.scheme, f"{address}{port}", parts.path, "", ""))


BASE = _dialable(os.environ.get("BASE", "http://app:5000"))
BOOK = os.environ.get("BOOK", "salt-road")
SHOTS = os.environ.get("SHOTS", "/shots")
USER = os.environ.get("SEED_USER", "mara")
PASSWORD = os.environ.get("SEED_PASSWORD", "ember-pact-demo")

results = []


def check(label, condition, detail=""):
    results.append((label, bool(condition), detail))
    print(f"  [{'ok ' if condition else 'FAIL'}] {label}{' -- ' + detail if detail else ''}")
    return bool(condition)


def step(label):
    print(f"\n=== {label} ===")


def log_in(page):
    step("log in")
    page.goto(f"{BASE}/login", wait_until="domcontentloaded")
    page.fill("input[name=username]", USER)
    page.fill("input[name=password]", PASSWORD)
    page.click("button[type=submit], input[type=submit]")
    page.wait_for_load_state("networkidle")
    check("session established", "/login" not in page.url, page.url)


def open_map(page, selection=""):
    suffix = f"/{selection}" if selection else ""
    page.goto(f"{BASE}/timeline/#/{BOOK}/~map{suffix}", wait_until="domcontentloaded")
    page.wait_for_selector(".sg-row", timeout=15000)
    page.wait_for_timeout(400)  # let the measure/reflow pass settle


def row_tops(page):
    """Every row's y, keyed by identity -- what a reflow has to move.

    Keyed by the row's id and not by the text on it: several rows legitimately
    read the same ("2 at once", "4 scenes on The Boy"), so a text key silently
    collapses them and the comparison stops meaning anything.
    """
    return page.eval_on_selector_all(".sg-row", """
      (rows) => Object.fromEntries(rows.map((r) => [
        r.dataset.event || r.dataset.slot, parseFloat(r.style.top),
      ]))
    """)


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        page.on("pageerror", lambda e: check("no uncaught JS error", False, str(e)))

        log_in(page)

        step("the map draws")
        open_map(page)
        rows = page.locator(".sg-row").count()
        chips = page.locator(".sg-pick").count()
        check("every thread has a picker chip", chips == 10, f"{chips} chips")
        check("rows are drawn", rows > 20, f"{rows} rows")
        check("all chips start selected",
              page.locator(".sg-pick.is-on").count() == chips)
        check("edges are drawn", page.locator("path.sg-edge").count() > 20)
        check("the calendar rail is drawn", page.locator(".sg-head").count() > 0)
        page.screenshot(path=f"{SHOTS}/01-map-all-threads.png", full_page=False)

        step("solitary stretches are folded")
        bands = page.locator(".sg-row.is-band")
        folded = bands.count()
        check("bands are present", folded > 0, f"{folded} folded stretches")
        check("a band says how much story it holds",
              "scenes on" in bands.first.inner_text(), bands.first.inner_text().strip())
        before = row_tops(page)
        bands.first.locator(".sg-row-head").click()
        page.wait_for_timeout(400)
        check("unfolding a band adds rows",
              page.locator(".sg-row").count() > rows,
              f"{rows} -> {page.locator('.sg-row').count()}")
        page.screenshot(path=f"{SHOTS}/02-band-unfolded.png")

        step("a scene enlarges in place and the diagram reflows")
        open_map(page, "the-assayer,the-widow,the-boy")
        check("the URL selection narrows the map",
              page.locator(".sg-pick.is-on").count() == 3,
              f"{page.locator('.sg-pick.is-on').count()} of 10 selected")
        before = row_tops(page)
        # a scene standing on its own -- not a folded stretch, and not one of the
        # several sharing a moment, whose rows behave differently on purpose
        scene = page.locator(".sg-row[data-event]:not(.is-band):not(.is-group)").nth(1)
        scene_id = scene.get_attribute("data-event")
        title = scene.locator(".sg-row-title").inner_text()
        scene.locator(".sg-row-head").click()
        page.wait_for_selector(".sg-row.expanded .peek-card", timeout=10000)
        page.wait_for_timeout(700)  # the card fetches its detail, then re-measures
        after = row_tops(page)

        card = page.locator(".sg-row.expanded .peek-card").first
        expect(card).to_be_visible()
        box = card.bounding_box()
        check("the card opened inside its own row", box and box["height"] > 80,
              f"card {round(box['height']) if box else 0}px tall")
        check("the expanded row is the one clicked",
              page.locator(".sg-row.expanded .sg-row-title").inner_text() == title, title)

        moved = [t for t in before if t in after and after[t] > before[t] + 20]
        unmoved_above = [
            t for t in before
            if t in after and before[t] < before[scene_id] and abs(after[t] - before[t]) < 1
        ]
        check("rows below moved down", len(moved) > 0, f"{len(moved)} rows pushed down")
        check("rows above stayed put", len(unmoved_above) > 0,
              f"{len(unmoved_above)} rows unchanged")
        check("the diagram grew with it",
              page.eval_on_selector(".storygraph", "(el) => parseFloat(el.style.height)")
              > max(before.values()))
        page.screenshot(path=f"{SHOTS}/03-scene-expanded.png")

        step("the connected-plots preset still works")
        page.goto(f"{BASE}/timeline/#/{BOOK}/the-cipher/connected",
                  wait_until="domcontentloaded")
        page.wait_for_selector(".sg-row", timeout=15000)
        page.wait_for_timeout(600)
        selected = page.locator(".sg-pick.is-on").count()
        check("it lands on the map with a preset selection", 0 < selected < 10,
              f"{selected} of 10 threads")
        check("and rewrites the URL to that selection", "~map/" in page.url,
              page.url.split("#")[-1])
        page.screenshot(path=f"{SHOTS}/04-connected-preset.png")

        step("dark mode")
        page.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
        page.wait_for_timeout(200)
        page.screenshot(path=f"{SHOTS}/05-dark.png")

        browser.close()

    failed = [label for label, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        print("failed: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
