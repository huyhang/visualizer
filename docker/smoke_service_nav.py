"""The shared service navigation, measured in a real browser.

pytest can prove the nav renders, that no header still carries a service link,
and which item claims to be current. It cannot prove any of the things this
change is actually about: that the header fits one row on a phone, that the
rail narrows before Prithvi's map runs out of room, that the tab bar does not
sit on top of the content it is supposed to sit under. A layout bug is
invisible to a test client -- which is exactly how the wrapping header this
replaces survived a green suite.

It also covers the two other rows that compete for a phone's width: Chronos's
"Your books" heading, whose actions shrink to their glyphs rather than pushing
the title onto a second line, and an Akasha article's trail and actions, which
take a line each so that the length of the path stops deciding the layout.
Same concern, same widths, same login.

So this measures. Three widths, one per state the CSS defines:

    1280x800   left rail, glyph + label      176px
     980x800   left rail, glyph only          64px
     320x700   bottom tab bar                 56px of height

Run it against a stack that is already up::

    docker compose -f docker/docker-compose.nas.yml up --build -d
    docker run --rm --network visualizer_default \\
      -v "$PWD/docker/smoke_service_nav.py:/work/smoke_service_nav.py:ro" -w /work \\
      mcr.microsoft.com/playwright/python:v1.62.0-noble \\
      bash -lc 'pip install -q playwright==1.62.0 && python smoke_service_nav.py'

Mount the one script rather than all of ``docker/``: that directory holds
``.env``, and a browser-test container has no business reading the secret key.
Inside the compose network the app answers to ``app:5000``; override with BASE.
"""

import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE", "http://app:5000").rstrip("/")
USER = os.environ.get("SEED_USER", "admin")
PASSWORD = os.environ.get("SEED_PASSWORD", "admin-pass")

# Every authenticated shell, so "always available" is measured rather than
# asserted. The last three are the utility pages that used to highlight
# Articles while you stood on them.
PAGES = (
    ("Articles", "/", "Articles"),
    ("Timeline", "/timeline/", "Timeline"),
    ("Maps", "/prithvi/", "Maps"),
    ("Access", "/account", None),
    ("Admin", "/admin", None),
    ("Change password", "/change-password", None),
)

WIDTHS = (
    # width, height, expected rail width, labels visible, orientation
    (1280, 800, 176, True, "left"),
    (980, 800, 64, False, "left"),
    (320, 700, None, True, "bottom"),
)


class Checks:
    def __init__(self):
        self.failures = []
        self.total = 0

    def __call__(self, label, ok, detail=""):
        self.total += 1
        mark = "ok  " if ok else "FAIL"
        print(f"  [{mark}] {label}" + (f" -- {detail}" if detail else ""))
        if not ok:
            self.failures.append(label)


def login(page):
    page.goto(f"{BASE}/login")
    # The largest text setting, because that is when a row runs out of width.
    page.evaluate("localStorage.setItem('visualizer-fontscale', '22')")
    page.fill("input[name=username]", USER)
    page.fill("input[name=password]", PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")


def measure(page):
    return page.evaluate(
        """() => {
          const nav = document.querySelector('.service-nav');
          const header = document.querySelector('header');
          const navBox = nav.getBoundingClientRect();
          const headerBox = header ? header.getBoundingClientRect() : null;
          const current = [...nav.querySelectorAll('[aria-current="page"]')]
            .map(a => a.querySelector('.service-nav-label').textContent.trim());
          return {
            viewport: window.innerWidth,
            documentWidth: document.documentElement.scrollWidth,
            navLeft: Math.round(navBox.left),
            navTop: Math.round(navBox.top),
            navRight: Math.round(navBox.right),
            navBottom: Math.round(navBox.bottom),
            navWidth: Math.round(navBox.width),
            navHeight: Math.round(navBox.height),
            viewportWidth: window.innerWidth,
            viewportHeight: window.innerHeight,
            labelsVisible: [...nav.querySelectorAll('.service-nav-label')]
              .every(l => l.getBoundingClientRect().width > 1),
            linkCount: nav.querySelectorAll('.service-nav-link').length,
            smallestTarget: Math.min(...[...nav.querySelectorAll('.service-nav-link')]
              .map(a => Math.min(a.getBoundingClientRect().width,
                                 a.getBoundingClientRect().height))),
            current,
            accessActive: !!document.querySelector('.access-link.active'),
            headerHeight: headerBox ? Math.round(headerBox.height) : null,
            headerLines: headerBox
              ? Math.round(headerBox.height / parseFloat(getComputedStyle(header).lineHeight || 24))
              : null,
            headerWrap: header ? getComputedStyle(header).flexWrap : null,
            // Only the chrome this change owns. An element that is wider than
            // the window *inside its own scroll container* is fine -- an admin
            // table is meant to scroll in its box rather than drag the page.
            chromeOverflow: [...document.querySelectorAll(
                '.service-nav *, header *')]
              .filter(e => e.getBoundingClientRect().right > window.innerWidth + 1)
              .slice(0, 6)
              .map(e => ({ tag: e.tagName, cls: String(e.className).slice(0, 40) })),
            // Reported, not asserted: wide content that stays contained.
            containedWide: [...document.querySelectorAll('main *')]
              .filter(e => e.getBoundingClientRect().right > window.innerWidth + 1)
              .slice(0, 3)
              .map(e => e.tagName + '.' + String(e.className).slice(0, 24)),
          };
        }"""
    )


def check_page(page, check, name, path, expect_current, rail_w, labels, side):
    response = page.goto(f"{BASE}{path}")
    page.wait_for_selector(".service-nav")
    page.wait_for_load_state("networkidle")
    m = measure(page)
    tag = f"{name}"

    check(f"{tag}: loads", response.ok, str(response.status))
    check(f"{tag}: all three services are present", m["linkCount"] == 3, str(m))
    # The user-visible criterion, and the strict one: the page itself must
    # never slide sideways. This is what the wrapping header used to cause.
    check(f"{tag}: the page does not scroll sideways",
          m["documentWidth"] <= m["viewport"],
          f"document {m['documentWidth']}px in {m['viewport']}px")
    check(f"{tag}: no header or nav element overflows",
          not m["chromeOverflow"], str(m["chromeOverflow"]))
    if m["containedWide"]:
        print(f"       note: wider than the window but contained -- "
              f"{', '.join(m['containedWide'])}")
    check(f"{tag}: touch targets clear 44px", m["smallestTarget"] >= 44, str(m))
    check(f"{tag}: labels {'visible' if labels else 'hidden'}",
          m["labelsVisible"] is labels, str(m))

    # The point of the whole change: one row, never two.
    if m["headerHeight"] is not None:
        check(f"{tag}: header does not wrap", m["headerWrap"] == "nowrap", str(m))
        check(f"{tag}: header is a single row", m["headerHeight"] <= 96, str(m))

    if side == "left":
        check(f"{tag}: rail is at the left edge", m["navLeft"] == 0, str(m))
        check(f"{tag}: rail is {rail_w}px wide", m["navWidth"] == rail_w, str(m))
        check(f"{tag}: rail fills the window",
              m["navHeight"] == m["viewportHeight"], str(m))
    else:
        check(f"{tag}: tab bar is pinned to the bottom",
              m["navBottom"] == m["viewportHeight"], str(m))
        check(f"{tag}: tab bar spans the width",
              m["navLeft"] == 0 and m["navRight"] == m["viewportWidth"], str(m))
        check(f"{tag}: tab bar leaves the content full width",
              m["navWidth"] == m["viewportWidth"], str(m))

    # The bug this change also fixes: Articles claiming to be the current page
    # while you stand on Access.
    expected = [expect_current] if expect_current else []
    check(f"{tag}: current item is {expected or 'nothing'}",
          m["current"] == expected, str(m["current"]))
    check(f"{tag}: Access is {'lit' if expect_current is None else 'not lit'}",
          m["accessActive"] is (expect_current is None), str(m))


def check_content_clears_the_tab_bar(page, check):
    """A fixed bar that covers the end of the page is not 'always available'."""
    page.goto(f"{BASE}/timeline/")
    page.wait_for_selector(".service-nav")
    clear = page.evaluate(
        """() => {
          const nav = document.querySelector('.service-nav').getBoundingClientRect();
          const main = document.querySelector('.app-shell-main').getBoundingClientRect();
          const pad = parseFloat(getComputedStyle(
            document.querySelector('.app-shell-main')).paddingBottom);
          return { navTop: Math.round(nav.top), mainBottom: Math.round(main.bottom),
                   paddingBottom: Math.round(pad), navHeight: Math.round(nav.height) };
        }"""
    )
    check("Timeline: content reserves room for the tab bar",
          clear["paddingBottom"] >= clear["navHeight"], str(clear))


def check_books_head(page, check, compact):
    """The heading row keeps its title and its actions on one line.

    Both Chronos views that use this row are measured, because they share a
    class: a rule written for one silently reaches the other, and a button
    squashed to a square without a glyph to fall back on is unreadable.
    """
    page.goto(f"{BASE}/timeline/")
    page.wait_for_selector(".books-head")

    def geometry():
        return page.evaluate(
            """() => {
              const head = document.querySelector('.books-head');
              const title = head.querySelector('.view-title');
              const buttons = [...head.querySelectorAll('button')];
              const t = title.getBoundingClientRect();
              const line = parseFloat(getComputedStyle(title).lineHeight);
              return {
                title: title.textContent.trim(),
                lines: Math.round(t.height / line),
                clipped: title.scrollWidth > title.clientWidth + 1,
                headLines: Math.round(head.getBoundingClientRect().height / t.height),
                count: buttons.length,
                // Every button in this row must be one the helper built, or the
                // compact rule squashes a label with nothing to replace it.
                allAreActions: buttons.every(b => b.classList.contains('head-action')),
                named: buttons.every(b => (b.textContent.trim() || b.title).length > 0),
                widths: buttons.map(b => Math.round(b.offsetWidth)),
                sameHeight: new Set(buttons.map(b => b.offsetHeight)).size === 1,
                labelsShown: buttons.every(b =>
                  b.querySelector('.head-action-label').getBoundingClientRect().width > 1),
                glyphsShown: buttons.every(b =>
                  b.querySelector('.head-action-glyph').getBoundingClientRect().width > 1),
                primaryLast: buttons.length
                  ? !buttons[buttons.length - 1].classList.contains('secondary') : true,
              };
            }"""
        )

    for view in ("books", "calendars"):
        if view == "calendars":
            page.click(".books-head .head-action[title^='Reckonings']")
            page.wait_for_timeout(400)
            page.wait_for_selector(".books-head")
        g = geometry()
        tag = f"Timeline {g['title']!r}"
        check(f"{tag}: title stays on one line", g["lines"] == 1, str(g))
        check(f"{tag}: title is not clipped", not g["clipped"], str(g))
        check(f"{tag}: the row is a single line", g["headLines"] == 1, str(g))
        check(f"{tag}: every action can shrink to a glyph", g["allAreActions"], str(g))
        check(f"{tag}: every action keeps a name", g["named"], str(g))
        check(f"{tag}: actions share one height", g["sameHeight"], str(g))
        check(f"{tag}: the new-thing action is primary", g["primaryLast"], str(g))
        if compact:
            check(f"{tag}: actions are 36px glyphs",
                  all(w == 36 for w in g["widths"]) and g["glyphsShown"]
                  and not g["labelsShown"], str(g))
        else:
            check(f"{tag}: actions show their words",
                  g["labelsShown"] and not g["glyphsShown"], str(g))


def check_article_toolbar(page, check, stacked):
    """An article's trail and its four actions, at a deep path.

    The reported case: how many of Edit/History/Share/Delete were stranded on a
    second row depended on how long the breadcrumb was and how large the reader
    had set the text. Below the breakpoint the two take a row each, so the path
    stops deciding the shape.
    """
    page.goto(f"{BASE}/#/ember-pact/characters/lyra-vane")
    page.wait_for_selector(".pane-actions .btn")
    page.wait_for_timeout(250)
    m = page.evaluate(
        r"""() => {
          const bar = document.querySelector('.pane-toolbar');
          const crumbs = bar.querySelector('.crumbs');
          const actions = bar.querySelector('.pane-actions');
          const buttons = [...actions.querySelectorAll('.btn')];
          const tops = new Set(buttons.map(b =>
            Math.round(b.getBoundingClientRect().top)));
          const c = crumbs.getBoundingClientRect();
          const a = actions.getBoundingClientRect();
          return {
            crumbText: crumbs.textContent.replace(/\s+/g, ' ').trim().slice(0, 60),
            buttonCount: buttons.length,
            actionRows: tops.size,
            actionsBelowCrumbs: Math.round(a.top) >= Math.round(c.bottom),
            sameRow: Math.round(a.top) < Math.round(c.bottom),
            actionsRight: Math.round(a.right) <= window.innerWidth + 1,
            labels: buttons.map(b => b.textContent.trim()),
          };
        }"""
    )
    check("Article: all four actions are present", m["buttonCount"] == 4, str(m))
    # The point of the change: four buttons, one row, whatever the path says.
    check("Article: the actions are on a single row", m["actionRows"] == 1, str(m))
    check("Article: the actions stay inside the window", m["actionsRight"], str(m))
    if stacked:
        check("Article: the actions have a row of their own",
              m["actionsBelowCrumbs"], str(m))
    # Above the breakpoint they take a row of their own only when the width
    # left over calls for it, which is ordinary wrapping and not asserted. The
    # invariant at every width is the one above: the four never split.


def check_akasha_browser(page, check, side):
    """Akasha's article browser has to sit beside the nav, not underneath it.

    It is the tightest case in the product: the only screen with a second
    left-hand thing. Above 820px it is a permanent column and ``#menu-toggle``
    is hidden; below, it is a drawer that has to be opened first.
    """
    page.goto(f"{BASE}/")
    page.wait_for_load_state("networkidle")
    if side == "bottom":
        page.click("#menu-toggle")
        page.wait_for_timeout(350)
    boxes = page.evaluate(
        """() => {
          const nav = document.querySelector('.service-nav').getBoundingClientRect();
          const bar = document.querySelector('#sidebar').getBoundingClientRect();
          return { navTop: Math.round(nav.top), navLeft: Math.round(nav.left),
                   navRight: Math.round(nav.right), navBottom: Math.round(nav.bottom),
                   barLeft: Math.round(bar.left), barBottom: Math.round(bar.bottom),
                   innerH: window.innerHeight };
        }"""
    )
    # On a phone the nav is along the bottom, so "beside" means "above it".
    beside = boxes["barLeft"] >= boxes["navRight"] or boxes["barBottom"] <= boxes["navTop"]
    check("Articles: the browser opens clear of the service nav", beside, str(boxes))


def run(browser, width, height, rail_w, labels, side, check):
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    login(page)

    print(f"\n{width}x{height}  ({side}, {'labels' if labels else 'glyphs only'})")
    for name, path, expect_current in PAGES:
        check_page(page, check, name, path, expect_current, rail_w, labels, side)
    if side == "bottom":
        check_content_clears_the_tab_bar(page, check)
    check_books_head(page, check, compact=width <= 560)
    check_article_toolbar(page, check, stacked=width <= 820)
    check_akasha_browser(page, check, side)
    check(f"{width}px: no page raised a script error", not errors, "; ".join(errors[:3]))
    context.close()


def main():
    check = Checks()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for width, height, rail_w, labels, side in WIDTHS:
            run(browser, width, height, rail_w, labels, side, check)
        browser.close()

    passed = check.total - len(check.failures)
    print(f"\n{passed}/{check.total} checks passed")
    if check.failures:
        print("failed: " + "; ".join(check.failures))
    return 1 if check.failures else 0


if __name__ == "__main__":
    sys.exit(main())
