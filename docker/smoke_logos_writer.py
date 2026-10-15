"""Exercise the Logos writing page in a real headless browser.

Run from the repository root in the ``visualizer`` environment, after building
the frontend (``npm --prefix frontend ci && npm --prefix frontend run build``).
The script uses an in-memory app on a random local port and leaves no database
or browser state. It defaults to WebKit; set ``PLAYWRIGHT_BROWSER`` to another
installed engine.

What it walks: typing and autosave, an Akasha lookup linked as a mention, a new
draft and the comparison, then the narrowest phone layout at the largest text
size -- no surface overflows, the formatting bar and dialogs stay on screen,
the drawers open and close -- and the band around the service rail's 1100px
switch, where a three-column workspace once lost its right-hand panel.
"""

from __future__ import annotations

import os
import threading
from contextlib import closing

import mongomock
from playwright.sync_api import expect, sync_playwright
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server

from visualizer.auth import ALL_PERMS, AuthStore
from visualizer.logos.app import BOOK_RESOURCE, create_app
from visualizer.logos.gateways import FakeArticleGateway, FakeChronosGateway
from visualizer.logos.store import LogosStore

WRITE = "/?book=ember-pact&volume=one&section=gate&mode=write"


def document(text: str) -> dict:
    return {
        "version": 1,
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "id": "opening",
                "content": [{"type": "text", "text": text}],
            }
        ],
    }


def application():
    client = mongomock.MongoClient()
    auth = AuthStore(client)
    auth.create_user("mara", generate_password_hash("mara-pass"), role="user")
    auth.grant_owner(
        "mara", "ember-pact", None, None, list(ALL_PERMS),
        resource_type=BOOK_RESOURCE,
    )
    chronos = FakeChronosGateway()
    chronos.add_book("ember-pact", "The Ember Pact", world="ember")
    app = create_app(
        LogosStore(client),
        chronos,
        FakeArticleGateway([("ember", "characters", "lyra")]),
        auth,
        secret_key="writer-smoke",
        akasha_url="/",
        chronos_url="/timeline",
        prithvi_url="/prithvi",
        logos_url="/",
    )
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)
    seeded = app.test_client()
    seeded.post("/login", json={"username": "mara", "password": "mara-pass"})
    seeded.post(
        "/books/ember-pact/volumes/one",
        json={"title": "Volume One", "overview": ""},
    )
    seeded.post(
        "/books/ember-pact/volumes/one/sections/gate",
        json={
            "kind": "chapter",
            "title": "The Gate",
            "overview": "",
            "event_ids": [],
            "document": document("Lyra waited at the gate."),
        },
    )
    return app


def assert_no_horizontal_overflow(page, label: str) -> None:
    width = page.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert width <= 1, f"{label} overflows the viewport by {width}px"


def assert_inside_viewport(page, selector: str) -> None:
    box = page.locator(selector).first.bounding_box()
    assert box is not None, selector
    viewport = page.viewport_size
    assert viewport is not None
    assert box["x"] >= -1, (selector, box)
    assert box["x"] + box["width"] <= viewport["width"] + 1, (selector, box)


def assert_compact_actions(page, selector: str, expected: int) -> None:
    actions = page.locator(selector)
    assert actions.count() == expected, (selector, actions.count())
    assert all(width == 36 for width in actions.evaluate_all(
        "buttons => buttons.map(button => Math.round(button.offsetWidth))"
    )), selector


def select_words(page, words: str) -> None:
    """Select ``words`` in the prose, as a drag would."""
    page.evaluate(
        """(words) => {
          const walker = document.createTreeWalker(
            document.querySelector('.lw-editor'), NodeFilter.SHOW_TEXT);
          while (walker.nextNode()) {
            const node = walker.currentNode, at = node.nodeValue.indexOf(words);
            if (at < 0) continue;
            const range = document.createRange();
            range.setStart(node, at); range.setEnd(node, at + words.length);
            const selection = window.getSelection();
            selection.removeAllRanges(); selection.addRange(range);
            return;
          }
          throw new Error('no such words: ' + words);
        }""",
        words,
    )


def run() -> None:
    server = make_server("127.0.0.1", 0, application(), threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with (
            sync_playwright() as playwright,
            closing(
                getattr(
                    playwright, os.environ.get("PLAYWRIGHT_BROWSER", "webkit")
                ).launch(headless=True)
            ) as browser,
        ):
            page = browser.new_page(viewport={"width": 1280, "height": 850})
            thread.start()
            login = page.request.post(
                base + "/login",
                data={"username": "mara", "password": "mara-pass"},
            )
            assert login.ok
            page.goto(base + WRITE)
            expect(page.locator(".lw-unbuilt")).to_have_count(0)
            editor = page.locator(".lw-editor")
            expect(editor).to_contain_text("Lyra waited")

            editor.click()
            page.keyboard.press("ControlOrMeta+End")
            page.keyboard.insert_text(" She listened.")
            expect(page.locator(".lw-save")).to_have_text("Saved", timeout=5_000)

            select_words(page, "Lyra")
            page.keyboard.press("ControlOrMeta+k")
            expect(page.locator(".lw-entity")).to_contain_text("Lyra")
            page.get_by_role("button", name="Link mention").click()
            expect(page.locator(".lw-editor .entity-mention")).to_have_text("Lyra")
            expect(page.locator(".lw-save")).to_have_text("Saved", timeout=5_000)

            page.get_by_role("button", name="New draft").click()
            page.get_by_label("Draft name").fill("Alternate opening")
            page.get_by_role("button", name="Continue").click()
            expect(page.locator(".lw-draft-select")).to_contain_text(
                "Alternate opening"
            )
            page.get_by_role("button", name="Compare").click()
            expect(page.get_by_role("heading", name="Compare drafts")).to_be_visible()
            page.get_by_role("button", name="Compare", exact=True).last.click()
            expect(page.locator(".lw-compare-grid")).to_contain_text("Lyra waited")

            # The narrowest layout the shared navigation supports, with the
            # largest shared text preference. These checks exercise each Logos
            # surface rather than only proving that the stylesheet has a media
            # query.
            page.keyboard.press("Escape")
            page.set_viewport_size({"width": 320, "height": 700})
            page.evaluate("localStorage.setItem('visualizer-fontscale', '22')")

            page.goto(base + "/?book=ember-pact")
            assert_no_horizontal_overflow(page, "book contents")
            expect(page.get_by_role("button", name="Search")).to_be_visible()
            assert_compact_actions(page, ".book-actions .compact-action", 7)

            page.goto(base + "/?book=ember-pact&volume=one&section=gate")
            assert_no_horizontal_overflow(page, "section reader")
            page.get_by_role("button", name="Reading settings").click()
            assert_compact_actions(page, ".reader-toolbar .compact-action", 7)
            expect(page.get_by_role("heading", name="Reading settings")).to_be_visible()
            assert_inside_viewport(page, "#reading-settings")
            page.get_by_role("button", name="Close reading settings").click()

            page.goto(base + WRITE)
            expect(page.get_by_role("button", name="New draft")).to_be_visible()
            expect(page.get_by_role("button", name="Numbered")).to_be_visible()
            assert_no_horizontal_overflow(page, "writing page")
            assert_compact_actions(page, ".lw-draft-actions .lw-action", 3)
            assert_inside_viewport(page, ".lw-format")
            expect(page.locator(".app-header")).to_be_hidden()

            page.get_by_role("button", name="Open outline").click()
            outline = page.get_by_role("navigation", name="Manuscript outline")
            expect(outline).to_be_in_viewport()
            expect(page.locator(".lw-backdrop")).to_be_visible()
            page.locator(".lw-backdrop").click(position={"x": 310, "y": 350})
            expect(outline).not_to_be_in_viewport()

            page.get_by_role("button", name="Open writing tools").click()
            tools = page.get_by_role("complementary", name="Writing tools")
            expect(tools).to_be_in_viewport()
            page.keyboard.press("Escape")
            expect(tools).not_to_be_in_viewport()

            page.get_by_role("button", name="Compare").click()
            expect(page.get_by_role("heading", name="Compare drafts")).to_be_visible()
            assert_inside_viewport(page, ".lw-compare")
            page.keyboard.press("Escape")

            # The band between the phone and a roomy desktop, which is where
            # the old writer lost its right-hand panel off the edge. 1024 and
            # 1152 sit either side of the rail's own 1100px switch, and 1280
            # is a narrow laptop that still gets three columns.
            for width in (1024, 1152, 1280):
                page.set_viewport_size({"width": width, "height": 850})
                page.goto(base + WRITE)
                expect(page.locator(".lw-editor")).to_be_visible()
                assert_no_horizontal_overflow(page, f"writing page @{width}")
                assert_inside_viewport(page, ".lw-format")
                # Three columns when there is room for them, in rem; drawers
                # otherwise -- but never a panel pushed off the edge.
                if page.locator(".lw-tools-button").is_visible():
                    tools = page.get_by_role("complementary", name="Writing tools")
                    expect(tools).not_to_be_in_viewport()
                else:
                    assert_inside_viewport(page, ".lw-tools")
                page.goto(base + "/?book=ember-pact")
                assert_no_horizontal_overflow(page, f"book contents @{width}")
    finally:
        if thread.is_alive():
            server.shutdown()
            thread.join(timeout=5)
        else:
            server.server_close()


if __name__ == "__main__":
    run()
    print("Logos writer smoke test passed.")
