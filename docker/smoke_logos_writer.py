"""Exercise the Logos writing workspace in a real headless browser.

Run from the repository root in the ``visualizer`` environment. The script uses
an in-memory app on a random local port and leaves no database or browser state.
It defaults to WebKit; set ``PLAYWRIGHT_BROWSER`` to another installed engine.
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
    box = page.locator(selector).bounding_box()
    assert box is not None
    viewport = page.viewport_size
    assert viewport is not None
    assert box["x"] >= -1, (selector, box)
    assert box["x"] + box["width"] <= viewport["width"] + 1, (selector, box)


def assert_compact_actions(page, selector: str, expected: int) -> None:
    actions = page.locator(selector)
    assert actions.count() == expected
    assert all(width == 36 for width in actions.evaluate_all(
        "buttons => buttons.map(button => Math.round(button.offsetWidth))"
    ))


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
            page.goto(
                base + "/?book=ember-pact&volume=one&section=gate&mode=write"
            )
            expect(page.locator(".draft-editor")).to_contain_text("Lyra waited")

            page.locator(".draft-editor").press("End")
            page.keyboard.insert_text(" She listened.")
            expect(page.locator(".writer-save-status")).to_have_text(
                "Saved", timeout=5_000
            )

            page.evaluate(
                """() => {
                  const root = document.querySelector('.draft-editor');
                  const text = root.querySelector('p').firstChild;
                  const range = document.createRange();
                  range.setStart(text, 0); range.setEnd(text, 4);
                  const selection = window.getSelection();
                  selection.removeAllRanges(); selection.addRange(range);
                  root.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                }"""
            )
            page.get_by_role("button", name="Look up in Akasha").click()
            expect(page.locator(".entity-result")).to_contain_text("Lyra")
            page.get_by_role("button", name="Link mention").click()
            expect(page.locator(".entity-mention")).to_have_text("Lyra")

            page.get_by_role("button", name="New draft").click()
            page.get_by_label("Draft name").fill("Alternate opening")
            page.get_by_role("button", name="Continue").click()
            expect(page.locator(".draft-select")).to_contain_text(
                "Alternate opening"
            )
            page.get_by_role("button", name="Compare").click()
            expect(page.get_by_role("heading", name="Compare drafts")).to_be_visible()

            # The narrowest layout the shared navigation supports, with the
            # largest shared text preference. These checks exercise each Logos
            # surface rather than only proving that the stylesheet has a media
            # query.
            page.get_by_role("button", name="Close comparison").click()
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

            page.goto(
                base + "/?book=ember-pact&volume=one&section=gate&mode=write"
            )
            expect(page.get_by_role("button", name="New draft")).to_be_visible()
            expect(page.get_by_role("button", name="Numbered")).to_be_visible()
            assert_no_horizontal_overflow(page, "writing workspace")
            assert_compact_actions(page, ".writer-draft-action", 3)
            assert_compact_actions(page, ".writer-format .compact-action", 7)

            page.get_by_role("button", name="Open outline").click()
            expect(page.get_by_role("navigation", name="Manuscript outline")).to_be_in_viewport()
            expect(page.locator(".writer-drawer-backdrop")).to_be_visible()
            page.locator(".writer-drawer-backdrop").click(position={"x": 310, "y": 350})
            expect(page.get_by_role("navigation", name="Manuscript outline")).not_to_be_in_viewport()

            page.get_by_role("button", name="Compare").click()
            expect(page.get_by_role("heading", name="Compare drafts")).to_be_visible()
            assert_inside_viewport(page, ".draft-comparison")
            page.get_by_role("button", name="Close comparison").click()

            # The band between the phone and a roomy desktop, which is where
            # the writer used to lose its right-hand panel off the edge: the
            # three tracks demanded 64rem and the service rail had already
            # taken its share. 1024 and 1152 sit either side of the rail's own
            # 1100px switch, and 1280 is the narrowest width that still gets
            # the three-column desktop layout.
            for width in (1024, 1152, 1280):
                page.set_viewport_size({"width": width, "height": 850})
                page.goto(
                    base + "/?book=ember-pact&volume=one&section=gate&mode=write"
                )
                assert_no_horizontal_overflow(page, f"writing workspace @{width}")
                assert_inside_viewport(page, ".writer-format")
                if width > 1100:
                    assert_inside_viewport(page, ".writer-context")
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
