"""Exercise the Logos writing workspace in a real headless browser.

Run from the repository root in the ``visualizer`` environment. The script uses
an in-memory app on a random local port and leaves no database or browser state.
"""

from __future__ import annotations

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


def run() -> None:
    server = make_server("127.0.0.1", 0, application(), threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with (
            sync_playwright() as playwright,
            closing(playwright.webkit.launch(headless=True)) as browser,
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
    finally:
        if thread.is_alive():
            server.shutdown()
            thread.join(timeout=5)
        else:
            server.server_close()


if __name__ == "__main__":
    run()
    print("Logos writer smoke test passed.")
