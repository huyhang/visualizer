"""Exercise the book-wide Scenes timeline in a real browser.

The pure placement rules are covered by ``test_scene_timeline_js.py``. This
smoke check covers the browser boundary: mounting, scrolling, the view switch,
the fixed cursor, simultaneous lanes, and the undated shelf.
"""

import os
import socket
import sys
import threading
from pathlib import Path
from wsgiref.simple_server import WSGIRequestHandler, make_server

from playwright.sync_api import sync_playwright

# Reuse the self-contained Chronos fixture rather than maintaining a second app
# factory and login setup in this scripts-only directory.
from smoke_goals_ui import BOOK, PASSWORD, USER, build_app, seed


class _Quiet(WSGIRequestHandler):
    def log_message(self, *args):
        pass


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _add_edge_cases(app):
    client = app.test_client()
    client.post("/login", data={"username": USER, "password": PASSWORD})
    location = {"database": BOOK, "collection": "locations", "id": "highkeep"}
    client.post(f"/books/{BOOK}/events/same-time", json={
        "location": location,
        "title": "A Second Beginning",
        "start_tick": 0,
        "end_tick": 5,
    })
    client.post(f"/books/{BOOK}/events/someday", json={
        "location": location,
        "title": "Someday",
    })
    client.post(f"/books/{BOOK}/events/distant-coda", json={
        "location": location,
        "title": "A Distant Coda",
        "start_tick": 1000,
        "end_tick": 1010,
    })


def _fixture_server(port):
    app = build_app()
    seed(app)
    _add_edge_cases(app)
    server = make_server("127.0.0.1", port, app, handler_class=_Quiet)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main():
    if os.environ.get("SERVE_ONLY"):
        port = int(os.environ.get("PORT", "5056"))
        app = build_app()
        seed(app)
        _add_edge_cases(app)
        print(f"Serving the Scenes timeline fixture on :{port}", flush=True)
        make_server("0.0.0.0", port, app, handler_class=_Quiet).serve_forever()
        return 0

    external = os.environ.get("BASE")
    server = None
    if external:
        base = external.rstrip("/")
    else:
        port = _free_port()
        server = _fixture_server(port)
        base = f"http://127.0.0.1:{port}"
    failures = []
    shots = os.environ.get("SHOTS")

    def check(label, condition):
        print(f"  {'ok  ' if condition else 'FAIL'} {label}")
        if not condition:
            failures.append(label)

    try:
        with sync_playwright() as playwright:
            browser_type = getattr(
                playwright, os.environ.get("PLAYWRIGHT_BROWSER", "chromium")
            )
            browser = browser_type.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.on("pageerror", lambda error: failures.append(f"JavaScript: {error}"))
            page.goto(f"{base}/login")
            page.fill("input[name=username]", USER)
            page.fill("input[name=password]", PASSWORD)
            page.click("button[type=submit]")

            page.goto(f"{base}/#/{BOOK}/~scenes")
            page.wait_for_selector(".scene-timeline-stage")
            page.wait_for_timeout(450)
            check("the timeline is the default view",
                  page.locator(".scene-view-option.active").inner_text() == "Timeline")
            check("the time cursor is visible",
                  page.locator(".scene-cursor-label").is_visible())

            simultaneous = page.locator(
                '.scene-timeline-item[data-event="the-claim"], '
                '.scene-timeline-item[data-event="same-time"]'
            )
            sides = simultaneous.evaluate_all("xs => xs.map(x => x.className).sort()")
            check("simultaneous scenes occupy parallel lanes",
                  len(sides) == 2 and sides[0] != sides[1])
            if shots:
                Path(shots).mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(Path(shots) / "scenes-timeline.png"))

            check("the rail is banded by the book's own calendar",
                  page.locator(".timeline-period-label").count() > 0)
            # The one thing the JS tests cannot see: a card is only invisible
            # off-stage, so a layout that packs past the bottom looks identical
            # to one that does not until you measure against a real stage.
            spilled = page.locator(".scene-timeline-layer").evaluate(
                """layer => {
                     const h = layer.clientHeight;
                     return [...layer.children].filter(card => {
                       const top = card.getBoundingClientRect().top
                         - layer.getBoundingClientRect().top;
                       return top >= h || top + card.offsetHeight <= 0;
                     }).length;
                   }"""
            )
            check("no card is mounted where the stage cannot show it", spilled == 0)

            before = page.locator(".scene-timeline-item").evaluate_all(
                "xs => xs.map(x => x.dataset.event).sort()"
            )
            page.locator(".scene-timeline-scroll").evaluate(
                "el => { el.scrollTop = el.scrollHeight * 0.4; }"
            )
            page.wait_for_timeout(350)
            check("a large empty interval is drawn as an explicit break",
                  "ticks later" in page.locator(".timeline-break-label").inner_text())
            page.locator(".scene-timeline-scroll").evaluate(
                "el => { el.scrollTop = el.scrollHeight; }"
            )
            page.wait_for_timeout(450)
            after = page.locator(".scene-timeline-item").evaluate_all(
                "xs => xs.map(x => x.dataset.event).sort()"
            )
            check("scrolling changes the virtual scene neighborhood", before != after)

            page.get_by_role("button", name="List", exact=True).click()
            page.wait_for_selector(".scene-table")
            check("the complete list remains available",
                  page.locator(".scene-table tbody tr").count() == 7)
            page.get_by_role("button", name="Timeline", exact=True).click()
            page.wait_for_selector(".timeline-unscheduled")
            check("undated scenes have their own shelf",
                  "1 unscheduled scene" in page.locator(".timeline-unscheduled").inner_text())

            page.set_viewport_size({"width": 390, "height": 844})
            page.reload()
            page.wait_for_selector(".scene-timeline-item")
            page.wait_for_timeout(300)
            mobile_sides = page.locator(".scene-timeline-item").evaluate_all(
                "xs => xs.map(x => x.classList.contains('side-1'))"
            )
            check("the narrow layout uses one readable card lane", all(mobile_sides))
            check("simultaneous mobile scenes collapse into one moment",
                  page.locator(".timeline-moment-card").count() == 1)
            if shots:
                page.screenshot(path=str(Path(shots) / "scenes-timeline-mobile.png"))
            browser.close()
    finally:
        if server is not None:
            server.shutdown()

    if failures:
        print("failed: " + ", ".join(failures))
        return 1
    print("Scenes timeline smoke test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
