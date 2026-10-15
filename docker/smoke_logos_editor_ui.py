"""The writing page's Editor -- LLM review -- driven in a real browser against a
running stack.

pytest covers the review routes and vitest the components one at a time; what
neither sees is the assembled page: a review polled to its issues, underlines
on the very words they quote, a popover anchored to them, a fix accepted into
the prose and undone, a discussion that revises the fix, and the same flow on
a phone, where notes rise as sheets. This walks a writer's loop:

    ask -> watch it run -> issues listed and underlined -> accept a fix,
    undo it, accept it again -> talk an issue over until the editor revises
    -> dismiss one -> see what the editor reads -> a fresh review remembers
    the dismissal -> the phone: drawer, issue, sheet

It needs a stack with a GPU box behind LLM review. Without one, use the dev
server's fake, which walks the real stages a second or so apiece::

    npm --prefix frontend ci && npm --prefix frontend run build
    python -m visualizer.devserver --fake-gpubox --seed --port 5099 &
    BASE=http://127.0.0.1:5099 python docker/smoke_logos_editor_ui.py

The fake's issues say "[Fake]", and accepting one writes "[Fake fix]" into
the demo chapter. ``SHOTS=<dir>`` keeps a screenshot of each step; set
``PLAYWRIGHT_BROWSER`` to use an engine other than Chromium.
"""

import os
import re

from playwright.sync_api import Page, expect, sync_playwright

BASE = os.environ.get("BASE", "http://127.0.0.1:5099").rstrip("/")
USER = os.environ.get("USER_NAME", "mara")
PASSWORD = os.environ.get("USER_PASSWORD", "ember-pact-demo")
BOOK = os.environ.get("BOOK", "ember-pact")
VOLUME = os.environ.get("VOLUME", "the-ember-seal")
SECTION = os.environ.get("SECTION", "the-road-from-highkeep")
SHOTS = os.environ.get("SHOTS")
WRITE = (f"{BASE}/logos/?book={BOOK}&volume={VOLUME}&section={SECTION}"
         "&mode=write")


def shot(page: Page, name: str) -> None:
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        page.screenshot(path=os.path.join(SHOTS, f"{name}.png"))


def prose(page: Page) -> str:
    return page.locator(".lw-editor").inner_text()


def assert_no_horizontal_overflow(page: Page, label: str) -> None:
    width = page.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert width <= 1, f"{label} overflows the viewport by {width}px"


def open_writer(page: Page) -> None:
    page.goto(WRITE)
    expect(page.locator(".lw-unbuilt")).to_have_count(0)
    expect(page.locator(".lw-editor")).to_be_visible()


def ask(page: Page) -> None:
    """Ask for a review and wait for its issues."""
    tools = page.get_by_role("complementary", name="Writing tools")
    tools.get_by_role("tab", name=re.compile("^Editor")).click()
    expect(tools.locator(".lw-ask-state")).to_have_text(
        re.compile("Ready|Warming up|Busy"), timeout=10_000)
    asking = re.compile("Ask (the editor|for a fresh review)")
    tools.get_by_role("button", name=asking).click()
    expect(tools.locator(".lw-progress")).to_be_visible()
    shot(page, "1-running")
    expect(tools.get_by_role("list", name="Issues")).to_be_visible(timeout=30_000)


def desktop(page: Page) -> None:
    open_writer(page)
    ask(page)
    tools = page.get_by_role("complementary", name="Writing tools")
    rows = tools.get_by_role("list", name="Issues").get_by_role("button")
    open_rows = rows.count()
    assert open_rows >= 2, "the fake box raises an issue per check"
    # One underline per issue -- drawn in pieces where it crosses a linked name.
    underlined = page.locator(".logos-ann-editor").evaluate_all(
        "spans => new Set(spans.map(s => s.dataset.annotation)).size")
    assert underlined == open_rows, (underlined, open_rows)
    shot(page, "2-issues")

    # A prose issue offers exact words: accept, undo, accept.
    before = prose(page)
    page.locator(".logos-ann-k-prose").first.click()
    popover = page.locator(".lw-note-bubble")
    expect(popover).to_be_visible()
    expect(popover.locator("ins")).to_contain_text("[Fake fix]")
    shot(page, "3-popover")
    popover.get_by_role("button", name="Accept").click()
    expect(page.locator(".lw-editor")).to_contain_text("[Fake fix]")
    toast = page.locator(".st-toast").filter(has_text="Fix applied")
    toast.get_by_role("button", name="Undo").click()
    expect(page.locator(".lw-editor")).not_to_contain_text("[Fake fix]")
    assert prose(page) == before
    page.locator(".logos-ann-k-prose").first.click()
    page.locator(".lw-note-bubble").get_by_role("button", name="Accept").click()
    expect(page.locator(".lw-editor")).to_contain_text("[Fake fix]")
    expect(page.locator(".lw-save")).to_have_text("Saved", timeout=10_000)
    shot(page, "4-accepted")

    # Talk the continuity issue over until the editor revises its fix.
    rows.filter(has_text="Continuity").first.click()
    tools.get_by_role("button", name="What would you do instead?").click()
    expect(tools.locator(".lw-turn-editor .lw-stance")).to_have_text(
        "Revises", timeout=20_000)
    detail = tools.locator(".lw-note-detail")
    expect(detail.get_by_role("button", name="Accept")).to_be_visible()
    shot(page, "5-discussion")

    # Dismiss it instead; it moves to Done.
    tools.locator(".lw-note-detail").get_by_role("button", name="Dismiss").click()
    tools.get_by_role("button", name="All issues").click()
    done = tools.get_by_role("button", name=re.compile(r"^Done \d"))
    expect(done).to_have_text(re.compile(r"Done [12]"))

    # What the editor reads.
    tools.get_by_role("button", name="Review settings").click()
    options = page.locator(".lw-options-popover")
    options.get_by_role("button", name="What the editor will read").click()
    expect(options.locator(".lw-reads")).to_contain_text("The chapter, and")
    shot(page, "6-reads")
    page.keyboard.press("Escape")

    # A fresh review remembers what was dismissed.
    ask(page)
    done.click()
    expect(tools.get_by_role("list", name="Issues")).to_contain_text("Continuity")
    rows.first.click()
    expect(tools.get_by_text("Dismissed before")).to_be_visible()


def phone(page: Page) -> None:
    open_writer(page)
    assert_no_horizontal_overflow(page, "the writing page on a phone")
    page.get_by_role("button", name="Open writing tools").click()
    tools = page.get_by_role("complementary", name="Writing tools")
    expect(tools).to_be_in_viewport()
    tools.get_by_role("tab", name=re.compile("^Editor")).click()
    tools.get_by_role("button", name=re.compile(r"^Open \d")).click()
    tools.get_by_role("list", name="Issues").get_by_role("button").first.click()
    expect(tools.locator(".lw-note-detail")).to_be_visible()
    shot(page, "7-phone-detail")
    page.get_by_role("button", name="Close writing tools").click()
    expect(tools).not_to_be_in_viewport()
    page.locator(".logos-ann-editor").first.tap()
    sheet = page.locator(".lw-sheet")
    expect(sheet).to_be_visible()
    sheet.evaluate("el => Promise.all(el.getAnimations().map(a => a.finished))")
    box = sheet.bounding_box()
    viewport = page.viewport_size
    assert box and viewport and box["width"] <= viewport["width"] + 1
    assert box["y"] + box["height"] <= viewport["height"] + 1
    shot(page, "8-phone-sheet")


def main() -> None:
    with sync_playwright() as p:
        browser = getattr(p, os.environ.get("PLAYWRIGHT_BROWSER", "chromium")).launch()
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        login = context.request.post(f"{BASE}/login",
                                     data={"username": USER, "password": PASSWORD})
        assert login.ok, f"log in as {USER}: {login.status}"
        state = context.storage_state()
        desktop(context.new_page())
        context.close()
        handset = browser.new_context(viewport={"width": 390, "height": 844},
                                      has_touch=True, storage_state=state)
        phone(handset.new_page())
        handset.close()
        browser.close()
    print("Logos Editor smoke test passed.")


if __name__ == "__main__":
    main()
