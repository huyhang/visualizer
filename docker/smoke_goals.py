"""Drive the goals view in a real browser and say whether it actually works.

The same gap `smoke_story_map.py` fills, one screen over. The layout arithmetic
is proved under node (tests/chronos/test_goal_layout_js.py) and the wiring
statically (tests/chronos/test_ui_assets.py); what neither can see is whether the
diagram draws, whether selecting a goal lights the edges that reach it, and
whether the chips on a card go where they say they go.

It runs in the official Playwright image against the already-running stack, so
nothing is installed on the host and the app image is untouched:

    docker run --rm --network visualizer_default \\
      -v "$PWD/docker:/work" -v /tmp/shots:/shots -w /work \\
      mcr.microsoft.com/playwright/python:v1.62.0-noble \\
      bash -lc 'pip install -q playwright==1.62.0 && python smoke_goals.py'

Seed the book first with `seed_demo.py`. Screenshots land in /shots. Exit code
is the verdict: 0 if every check passed, 1 otherwise.
"""

import os
import socket
import sys
from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import sync_playwright


def _dialable(url: str) -> str:
    """Swap a compose service name for its address (see smoke_story_map.py)."""
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
BOOK = os.environ.get("BOOK", "ember-pact")
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


def open_goals(page, goal=""):
    suffix = f"/{goal}" if goal else ""
    page.goto(f"{BASE}/timeline/#/{BOOK}/~goals{suffix}", wait_until="domcontentloaded")
    page.wait_for_selector(".goal-card", timeout=15000)
    page.wait_for_timeout(300)


def node_positions(page):
    """Each goal box's y, keyed by the goal it draws -- what the layout claims."""
    return page.eval_on_selector_all(".goal-node", """
      (nodes) => Object.fromEntries(nodes.map((n) => [n.dataset.goal, parseFloat(n.style.top)]))
    """)


def overflowing(page):
    """Boxes whose text is wider or taller than the box holding it.

    The failure this screen actually had: SVG text does not clip, so a long goal
    name ran over the box beside it. Measured rather than eyeballed, and
    measured on the *rendered* page, because how much fits depends on the font
    the reader has and the scale they chose.
    """
    return page.eval_on_selector_all(".goal-node", """
      (nodes) => nodes.filter((n) =>
        n.scrollWidth > n.clientWidth + 1 || n.scrollHeight > n.clientHeight + 1
      ).map((n) => n.dataset.goal)
    """)


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 1200})
        page.on("pageerror", lambda e: check("no uncaught JS error", False, str(e)))

        log_in(page)

        step("the diagram draws")
        open_goals(page)
        nodes = page.locator(".goal-node").count()
        cards = page.locator(".goal-card").count()
        check("a box per goal", nodes > 0 and nodes == cards, f"{nodes} boxes, {cards} cards")
        check("dependency edges are drawn", page.locator("path.goal-edge").count() >= 3,
              f"{page.locator('path.goal-edge').count()} edges")
        page.screenshot(path=f"{SHOTS}/01-goals.png", full_page=True)

        step("a goal is drawn below what it rests on")
        at = node_positions(page)
        charter = at.get("charter-sealed")
        seal = at.get("seal-delivered")
        traitor = at.get("traitor-exposed")
        check("the ending's goal sits under both its prerequisites",
              None not in (charter, seal, traitor) and charter > seal and charter > traitor,
              f"charter={charter} seal={seal} traitor={traitor}")

        step("a graph wider than the page is reachable, not lost")
        pane = page.eval_on_selector(".goal-diagram", """
          (p) => ({ scroll: p.scrollWidth, visible: p.clientWidth })
        """)
        check("the pane scrolls when the graph is wider than it",
              pane["scroll"] <= pane["visible"] or page.eval_on_selector(
                  ".goal-diagram", "(p) => getComputedStyle(p).overflowX") == "auto",
              f"{pane['scroll']}px of graph in {pane['visible']}px of pane")

        step("no box overflows its own edges")
        spilling = overflowing(page)
        check("every label is clipped by the box that holds it", not spilling, str(spilling))
        page.locator("#font-toggle").click()   # the reader's larger font scale
        page.wait_for_timeout(400)
        bigger = overflowing(page)
        check("still true at the larger font scale", not bigger, str(bigger))
        page.screenshot(path=f"{SHOTS}/03-goals-large-font.png", full_page=True)
        page.locator("#font-toggle").click()
        page.wait_for_timeout(300)

        step("selecting a goal")
        # Named rather than "the first box": whichever box that happens to be
        # may rest on nothing and have nothing resting on it, and then there are
        # no edges to light and the check passes or fails by luck.
        page.locator(".goal-node", has_text="See the Seal pressed to the charter").click()
        page.wait_for_timeout(400)
        check("the selection rides in the URL", "~goals/" in page.url, page.url)
        check("a box is marked selected", page.locator(".goal-node.is-selected").count() == 1)
        check("the edges touching it are lit", page.locator("path.goal-edge.is-lit").count() > 0)
        check("its card is marked", page.locator(".goal-card.is-selected").count() == 1)
        page.screenshot(path=f"{SHOTS}/02-goal-selected.png", full_page=True)

        step("cards are closed until one is asked for")
        open_goals(page)
        check("every card is one row", page.locator(".goal-card.is-expanded").count() == 0)
        check("a closed card still says where the goal lands",
              "The Coronation" in page.locator("#goal-charter-sealed").inner_text())
        page.locator("#goal-crown-reached .goal-head").click()
        page.wait_for_timeout(400)
        check("clicking one opens it", page.locator("#goal-crown-reached.is-expanded").count() == 1)
        check("and only it", page.locator(".goal-card.is-expanded").count() == 1)
        check("the open card is the one in the URL", page.url.endswith("~goals/crown-reached"),
              page.url)
        page.locator("#goal-crown-reached .goal-head").click()
        page.wait_for_timeout(400)
        check("clicking it again closes it", page.locator(".goal-card.is-expanded").count() == 0)
        check("and the URL stops claiming a selection", page.url.endswith("~goals"), page.url)

        step("what an open card says")
        open_goals(page, "charter-sealed")
        card = page.locator("#goal-charter-sealed")
        check("the linked-to goal arrives open",
              "is-expanded" in (card.get_attribute("class") or ""))
        text = card.inner_text()
        check("it names what it rests on", "Deliver the Ember Seal" in text)
        check("it names the thread pursuing it", "The Road to the Crown" in text)
        check("it names the scene that delivers it", "The Coronation" in text)
        check("it is marked achieved", "achieved" in text.lower())

        step("the graph opens the card too")
        open_goals(page)
        page.locator(".goal-node", has_text="Expose the traitor").click()
        page.wait_for_timeout(400)
        check("picking a box opens that goal's card",
              page.locator("#goal-traitor-exposed.is-expanded").count() == 1)

        step("the filter narrows the list, not the graph")
        page.fill(".filter-bar .filter-box", "traitor")
        page.wait_for_timeout(400)
        check("one card left", page.locator(".goal-card").count() == 1,
              f"{page.locator('.goal-card').count()} cards")
        check("the whole graph is still drawn", page.locator(".goal-node").count() == nodes)

        step("the goal form builds its fields")
        # Every editor in the app builds its rows with dom.js's `field()`, which
        # each of them used to define its own copy of. Worth one real render to
        # prove the shared one is wired up.
        open_goals(page)
        page.locator(".book-head button", has_text="New goal").click()
        page.wait_for_selector(".modal-panel", timeout=10000)
        # Compared lowercased: the stylesheet upper-cases these, and what is
        # being checked is that the rows exist and are in order, not the CSS.
        labels = [t.lower() for t in
                  page.locator(".modal-panel .field .field-label").all_inner_texts()]
        check("the form has its labelled rows",
              labels == ["name", "id", "what it is", "rests on", "achieved at"], str(labels))
        check("and the hints under them", page.locator(".modal-panel .field-hint").count() >= 3)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        check("Escape closes it", page.locator(".modal-panel").count() == 0)

        step("the book report names the goal a finding is about")
        # The failure this catches: the row read "No scene achieves this goal
        # yet" with nothing on it saying which goal, because the payload carried
        # the anchor and the renderer dropped it.
        page.goto(f"{BASE}/timeline/#/{BOOK}/~issues", wait_until="domcontentloaded")
        page.wait_for_selector(".issue", timeout=15000)
        page.wait_for_timeout(400)
        row = page.locator(".issue", has_text="No scene achieves this goal yet").first
        check("the finding is on the page", row.count() > 0)
        check("and it names the goal", "Establish who was where" in row.inner_text(),
              row.inner_text().replace("\n", " ")[:90])
        page.screenshot(path=f"{SHOTS}/04-report-goals.png", full_page=True)
        row.locator(".issue-goal").click()
        page.wait_for_timeout(500)
        check("clicking it opens that goal", page.url.endswith("~goals/who-was-where"), page.url)

        step("a goal chip on a thread leads to it")
        page.goto(f"{BASE}/timeline/#/{BOOK}", wait_until="domcontentloaded")
        page.wait_for_selector(".pl-row", timeout=15000)
        chip = page.locator(".pl-table .chip.link").first
        check("the table draws goal chips", chip.count() > 0)
        chip.click()
        page.wait_for_timeout(500)
        check("it opens the goals view", "~goals/" in page.url, page.url)

        browser.close()

    failed = [label for label, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        print("failed: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
