"""Drive the goal surfaces in a real browser and say whether they actually work.

The rest of the suite proves the *logic* (``tests/chronos/test_goal_placing_js``
and ``test_graph_js`` run the pure modules under node) and the *wiring*
(``test_ui_assets``). What neither can see is the thing a writer looks at:
whether a goal chip opens the panel instead of navigating, whether the mark
lands on the delivering scene's row, whether the strip names what is missing,
and whether switching calendars re-dates the lot. That needs a browser.

Unlike ``smoke_story_map.py`` this one brings its own server: it runs the app on
``mongomock`` in a thread, seeds a book, and drives it. Nothing to start first,
no Docker, no Mongo.

    python docker/smoke_goals_ui.py            # headless
    SHOTS=/tmp/shots python docker/smoke_goals_ui.py

Where a browser will not launch on the host -- a locked-down macOS refuses
Chromium its Mach bootstrap port -- serve on the host and drive from the
official Playwright image instead:

    PORT=5055 SERVE_ONLY=1 python docker/smoke_goals_ui.py &
    docker run --rm -v "$PWD/docker:/work" -w /work \\
      -e BASE=http://host.docker.internal:5055 \\
      --add-host=host.docker.internal:host-gateway \\
      mcr.microsoft.com/playwright/python:v1.62.0-noble \\
      bash -lc 'pip install -q playwright==1.62.0 && python smoke_goals_ui.py'

(The image carries the browsers but not the Python binding, hence the install.
`SERVE_ONLY` binds 0.0.0.0 so the container can reach it.)

Exit code is the verdict: 0 if every check passed, 1 otherwise.
"""

import os
import socket
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from wsgiref.simple_server import WSGIRequestHandler, make_server

USER, PASSWORD = "mara", "mara-pass"
BOOK = "ember-pact"
HOURS = {"base_unit": "hour", "cycles": [{"name": "day", "size": 24},
                                         {"name": "month", "size": 30}],
         "epoch_label": "AF"}
BELLS = {"base_unit": "bell", "cycles": [{"name": "moon", "size": 10}],
         "epoch_label": "SR"}

passed, failed = [], []


def check(name, ok, detail=""):
    (passed if ok else failed).append(name)
    print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f" — {detail}" if detail and not ok else ""))


class _Quiet(WSGIRequestHandler):
    def log_message(self, *args):
        pass


def build_app():
    # Imported here, not at the top: the Docker split above drives a server
    # someone else is running, and that container has playwright and nothing
    # else. Only the half that serves needs the app's dependencies.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    import mongomock
    from werkzeug.security import generate_password_hash

    from visualizer.auth import AuthStore
    from visualizer.chronos.app import create_app
    from visualizer.chronos.entity_gate import FakeEntityGate
    from visualizer.chronos.models import EntityRef
    from visualizer.chronos.store import CalendarStore, StoryStore

    client = mongomock.MongoClient()
    clock = lambda: datetime(2026, 1, 1, tzinfo=UTC)
    auth = AuthStore(client)
    auth.create_user(USER, generate_password_hash(PASSWORD), role="admin")
    gate = FakeEntityGate()
    for name, collection in (("aldric", "characters"), ("highkeep", "locations")):
        gate.add(EntityRef(database=BOOK, collection=collection, id=name))
    app = create_app(
        StoryStore(client, clock=clock), gate, auth,
        secret_key="smoke-secret", calendar_store=CalendarStore(client, clock=clock),
    )
    app.config.update(WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)
    return app


def seed(app):
    """A book with two reckonings, four scenes on two threads, and three goals.

    Chosen so every case the UI has to tell apart is present: a goal delivered
    on the thread you are reading, one delivered on the *other* thread, and one
    with no scene at all.
    """
    c = app.test_client()
    c.post("/login", data={"username": USER, "password": PASSWORD})
    c.post(f"/calendars/{USER}/imperial", json={"name": "Imperial", "descriptor": HOURS})
    c.post(f"/calendars/{USER}/elvish", json={"name": "Elvish", "descriptor": BELLS})
    c.post(f"/books/{BOOK}", json={
        "title": "The Ember Pact",
        "calendars": [
            {"id": "imperial", "label": "Imperial Reckoning",
             "source": {"owner": USER, "calendar": "imperial"}},
            {"id": "elvish", "label": "Elvish Count",
             "source": {"owner": USER, "calendar": "elvish"}},
        ],
    })
    where = {"database": BOOK, "collection": "locations", "id": "highkeep"}
    who = [{"database": BOOK, "collection": "characters", "id": "aldric"}]
    for eid, title, start, end in (
        ("the-claim", "The Claim", 0, 10),
        ("the-road", "The Long Road", 20, 30),
        ("the-seal", "The Seal Pressed", 40, 50),
        ("the-coronation", "The Coronation", 60, 70),
    ):
        c.post(f"/books/{BOOK}/events/{eid}", json={
            "location": where, "characters": who, "title": title,
            "start_tick": start, "end_tick": end,
        })
    c.post(f"/books/{BOOK}/goals/claim", json={
        "title": "The claim is proved", "achieved_at": "the-claim"})
    c.post(f"/books/{BOOK}/goals/seal", json={
        "title": "The Seal pressed to the charter", "depends_on": ["claim"],
        "achieved_at": "the-seal"})
    c.post(f"/books/{BOOK}/goals/peace", json={
        "title": "The Pact holds", "depends_on": ["seal"]})  # no scene yet
    # aldric pursues all three but delivers only two of them: `seal` lands on
    # mirena's thread, which is the case the strip exists for.
    c.post(f"/books/{BOOK}/plotlines/aldric", json={
        "title": "Aldric's Road", "events": ["the-claim", "the-road", "the-coronation"],
        "goals": ["claim", "seal", "peace"]})
    c.post(f"/books/{BOOK}/plotlines/mirena", json={
        "title": "Mirena's Errand", "events": ["the-seal", "the-coronation"],
        "goals": ["seal"]})
    c.post(f"/books/{BOOK}/terminus/the-coronation")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run(page, base, shots):
    def shoot(name):
        if shots:
            page.screenshot(path=str(Path(shots) / f"goals-{name}.png"), full_page=True)

    errors, refused = [], []
    page.on("pageerror", lambda e: errors.append(str(e)))
    # The Akasha article proxy is excluded, and only that. This harness stands
    # chronos up alone against a fake entity gate, so it holds no Akasha grants
    # and `/ui/entity/...` refuses every article — correctly. The event cards
    # fall back to the reference's id, which is what they are designed to do.
    page.on("response", lambda r: refused.append(f"{r.status} {r.url}")
            if r.status >= 400 and "/ui/entity/" not in r.url else None)

    # The panel fills in after a fetch, so "the card exists" is not "the card is
    # ready" -- waiting on the facts list is what tells the two apart.
    def open_panel():
        page.wait_for_selector("#peek .goal-peek .goal-facts")

    page.goto(f"{base}/login")
    page.fill("input[name=username]", USER)
    page.fill("input[name=password]", PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")

    # -- a thread: marks on the rail, the strip above it, the panel beside it --
    page.goto(f"{base}/#/{BOOK}/aldric")
    page.wait_for_selector(".plotline-view .tl-row")

    marks = page.locator(".tl-goals .chip.goal")
    check("a thread marks the goals its scenes deliver",
          marks.count() == 1, f"{marks.count()} marks")
    check("the mark names the goal it stands for",
          "claim is proved" in (marks.first.inner_text() if marks.count() else ""))
    ticked = page.locator(".tl-row", has=page.locator(".tl-goals .chip.goal"))
    check("the delivering scene is ticked, on the row rather than round its dot",
          ticked.count() == 1 and "The Claim" in ticked.first.inner_text())
    check("...and the tick is a tick",
          marks.first.inner_text().startswith("\u2713") if marks.count() else False,
          marks.first.inner_text() if marks.count() else "no mark")

    strip = page.locator(".goal-strip-list li")
    notes = [strip.nth(i).inner_text() for i in range(strip.count())]
    check("the strip names the goals that did not land here", strip.count() == 2,
          f"{strip.count()}: {notes}")
    check("...and says a goal another thread delivers landed there",
          any("delivered at The Seal Pressed" in n for n in notes), str(notes))
    check("...and says which goal has no scene at all",
          any("no scene yet" in n for n in notes), str(notes))
    shoot("thread")

    # -- the chip opens the panel rather than navigating ----------------------
    before = page.url
    page.locator(".pl-header .chip-row.goals .chip.goal.link").first.click()
    open_panel()
    check("a goal chip opens the peek panel", page.locator("#peek .goal-peek").count() == 1)
    check("...without leaving the thread", page.url == before, page.url)
    panel = page.locator("#peek .goal-peek")
    check("the panel dates the goal through the book's calendar",
          "Day 1" in panel.inner_text(), panel.inner_text()[:200])
    check("the panel offers the one way out", page.locator("#peek .link-btn").count() == 1)
    shoot("peek")

    # -- following a prerequisite stays in the panel --------------------------
    page.goto(f"{base}/#/{BOOK}/aldric")
    page.wait_for_selector(".plotline-view .tl-row")
    page.locator(".goal-strip-list .chip.goal.link").first.click()
    open_panel()
    dep = page.locator("#peek .goal-facts .chip.goal.link").first
    if dep.count():
        dep.click()
        page.wait_for_timeout(400)
        check("a chip inside the panel opens in the panel, not the page",
              page.url == before and page.locator("#peek .goal-peek").count() == 1, page.url)
    else:
        check("a chip inside the panel opens in the panel, not the page", False, "no chip")

    # -- the story map --------------------------------------------------------
    page.goto(f"{base}/#/{BOOK}/~map")
    page.wait_for_selector(".storygraph .sg-row")
    map_marks = page.locator(".sg-goal")
    check("the map marks the scenes that deliver goals", map_marks.count() == 2,
          f"{map_marks.count()}")
    check("the map adds no ring to the nodes it marks",
          page.locator(".sg-goal-ring").count() == 0,
          str(page.locator(".sg-goal-ring").count()))
    check("the map names the goal that lands nowhere",
          page.locator(".goal-strip-list li").count() == 1,
          str(page.locator(".goal-strip-list li").count()))
    map_url = page.url
    map_marks.first.click()
    open_panel()
    check("a mark on the map opens the panel without leaving the map",
          page.url == map_url, page.url)
    shoot("map")

    # -- the goals page: dates on the diagram, and a switcher -----------------
    page.goto(f"{base}/#/{BOOK}/~goals")
    page.wait_for_selector(".goal-canvas .goal-node")
    whens = page.locator(".goal-node .goal-when")
    dated = [whens.nth(i).inner_text() for i in range(whens.count())]
    check("every goal box has a place for its date", whens.count() == 3, str(dated))
    check("the two delivered goals are dated",
          len([d for d in dated if d.strip()]) == 2, str(dated))
    check("the goals page offers the calendar switcher",
          page.locator(".goals-view .calendar-switch").count() == 1)

    imperial = sorted(d for d in dated if d.strip())
    page.select_option(".goals-view .calendar-switch", "elvish")
    page.wait_for_timeout(600)
    whens = page.locator(".goal-node .goal-when")
    elvish = sorted(d for d in (whens.nth(i).inner_text() for i in range(whens.count()))
                    if d.strip())
    check("switching the reckoning re-dates the diagram", imperial != elvish,
          f"{imperial} vs {elvish}")
    check("...and moves nothing else", len(elvish) == 2, str(elvish))
    shoot("goals")

    # -- the table ------------------------------------------------------------
    page.goto(f"{base}/#/{BOOK}")
    page.wait_for_selector(".pl-table .pl-row")
    table_url = page.url
    page.locator(".pl-table .chip.link").first.click()
    open_panel()
    check("a goal chip in the table opens the panel, not the goals page",
          page.url == table_url, page.url)

    check("no page threw a script error", not errors, "; ".join(errors[:3]))
    check("nothing the page asked for was refused", not refused,
          "; ".join(sorted(set(refused))[:4]))


def serve():
    """Start the seeded app and return (server, base url)."""
    app = build_app()
    seed(app)
    port = int(os.environ.get("PORT") or free_port())
    server = make_server("0.0.0.0", port, app, handler_class=_Quiet)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{port}"


def main():
    shots = os.environ.get("SHOTS")
    if shots:
        Path(shots).mkdir(parents=True, exist_ok=True)

    # Driving something already served (the Docker split above): no app here.
    given = os.environ.get("BASE")
    server, base = (None, given) if given else serve()
    print(f"driving {base}\n")

    if os.environ.get("SERVE_ONLY"):
        print("serving; ctrl-c to stop")
        threading.Event().wait()
        return 0

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        try:
            run(page, base, shots)
        finally:
            browser.close()
            if server:
                server.shutdown()

    print(f"\n{len(passed)} passed, {len(failed)} failed")
    for name in failed:
        print(f"  FAILED: {name}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
