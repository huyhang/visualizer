"""The research studio, driven in a real browser against a running stack.

pytest covers the routes and the pure rules on both sides, and vitest the
components one at a time; what neither sees is the assembled page: polling a
job to its draft, hover tools, popovers, the note pane filling up, and a save
that moves sources out of the inbox while the draft stays open. This walks a
writer's whole loop:

    ask (checking the plan first) -> approve -> watch -> read a cited draft
    -> add a passage, a fact and an image -> dig deeper -> save a new note
    -> add to that note from the sub-topic -> a stale save is refused
    -> steer the first draft (its plan cancelled, then approved)
    -> close the first draft -> keep the sub-topic's whole draft as a note
    -> the narrow layout

It needs a stack with a GPU box behind research. Without one, use the dev
server's fake, which walks the real stages a second or so apiece::

    npm --prefix frontend ci && npm --prefix frontend run build
    python -m visualizer.devserver --fake-gpubox --seed --port 5099 &
    BASE=http://127.0.0.1:5099 python docker/smoke_research_studio_ui.py

``SHOTS=<dir>`` keeps a screenshot of each step. Against the Docker stack,
run it the way docker/smoke_prithvi_ui.py describes.
"""

import os
import re
import socket
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import Page, expect, sync_playwright


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
WORLD = os.environ.get("WORLD", "ember-pact")
SHOTS = Path(os.environ["SHOTS"]) if os.environ.get("SHOTS") else None
# A fake job walks seven stages; a real one reads the web.
JOB_TIMEOUT_MS = int(os.environ.get("JOB_TIMEOUT_MS", "90000"))
QUESTION = "How were lanterns lit in a medieval port city?"
NOTE_TITLE = "Harbour lanterns"


class Checks:
    def __init__(self):
        self.failures = []
        self.total = 0

    def __call__(self, label, ok, detail=""):
        self.total += 1
        print(f"  [{'ok  ' if ok else 'FAIL'}] {label}{f'  -- {detail}' if detail else ''}")
        if not ok:
            self.failures.append(label)


def shot(page: Page, name: str) -> None:
    if SHOTS:
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / f"{name}.png"))


def login(page: Page) -> None:
    page.goto(f"{BASE}/login")
    page.fill("input[name=username]", USER)
    page.fill("input[name=password]", PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")


def open_studio(page: Page) -> None:
    page.goto(f"{BASE}/studio/{WORLD}")
    page.locator(".st-studio").wait_for()


def wait_for_draft(page: Page) -> None:
    page.locator(".st-article").wait_for(timeout=JOB_TIMEOUT_MS)


def check_ask_with_a_plan(page: Page, check: Checks) -> None:
    expect(page.locator(".st-box-pill")).to_contain_text("Ready")
    check("the box's state is shown", True)
    page.get_by_label("Research settings").click()
    page.get_by_text("Let me check the search plan first").click()
    page.keyboard.press("Escape")
    page.get_by_label("Research question").fill(QUESTION)
    expect(page.get_by_role("button", name="Research", exact=True)).to_be_enabled()
    page.get_by_label("Research question").press("Enter")

    plan = page.locator(".st-plan")
    plan.wait_for(timeout=JOB_TIMEOUT_MS)
    shot(page, "01-plan")
    first = page.get_by_label("Search 1", exact=True)
    check("the plan arrives with its searches", first.input_value() != "")
    first.fill("medieval harbour lanterns oil")
    page.get_by_role("button", name="Search with these").click()

    page.locator(".st-progress-card").wait_for()
    shot(page, "02-progress")
    check("the stages of the work are shown", page.locator(".st-stage").count() == 7)
    wait_for_draft(page)
    shot(page, "03-draft")
    check("the draft arrives without a reload", page.locator(".st-topic.is-selected").count() == 1)


def check_reading(page: Page, check: Checks) -> None:
    chips = page.locator(".st-article .st-cite")
    check("citations render as numbered chips", chips.count() > 0, f"{chips.count()} chips")
    chips.first.click()
    card = page.locator(".st-cite-card")
    card.wait_for()
    check("a citation shows its source's exact words", card.locator("blockquote").count() > 0)
    shot(page, "04-citation")
    page.keyboard.press("Escape")
    check("the draft says whether it was second-checked",
          page.locator(".st-topic-meta .st-badge").first.inner_text() != "")


def add_first_passage(page: Page) -> None:
    passage = page.locator(".st-article .st-passage").first
    passage.hover()
    passage.get_by_role("button", name="Add").click()


def check_collecting(page: Page, check: Checks) -> None:
    add_first_passage(page)
    blocks = page.locator(".st-blocks .st-block")
    expect(blocks).to_have_count(1)
    check("a passage lands in the note", True)
    check("the passage shows it is in the note",
          page.locator(".st-article .st-passage.is-added").count() == 1)

    page.get_by_role("tab", name="Facts").click()
    page.locator(".st-fact").first.get_by_role("button", name="Add").click()
    expect(blocks).to_have_count(2)
    check("a fact lands in the note", True)

    images = page.get_by_role("tab", name="Images")
    if images.count():
        images.click()
        page.locator(".st-image").first.get_by_role("button", name="Add to note").click()
        expect(blocks).to_have_count(3)
        check("an image lands in the note", True)
        # The fake box always offers one picture that has since vanished; a
        # real one may not.
        gone = page.locator(".st-image.is-gone")
        if gone.count():
            check("a picture gone from the web cannot be added",
                  gone.first.get_by_role("button").is_disabled())
    page.get_by_role("tab", name="Article").click()
    shot(page, "05-collected")


def check_dig_deeper(page: Page, check: Checks) -> str:
    parent = page.locator(".st-topic.is-selected .st-topic-title").inner_text()
    passage = page.locator(".st-article .st-passage").nth(1)
    passage.hover()
    passage.get_by_role("button", name="Dig deeper").click()
    dialog = page.get_by_role("dialog")
    question = dialog.get_by_label("Question for the sub-topic")
    check("the sub-topic question is worded from the passage",
          question.input_value().startswith("Tell me more about:"))
    shot(page, "06-dig-deeper")
    dialog.get_by_role("button", name="Research").click()
    expect(dialog).to_have_count(0)
    child = page.locator(".st-tree [role=group] .st-topic")
    check("the sub-topic appears under its parent", child.count() == 1)
    wait_for_draft(page)
    check("the sub-topic's path leads back to its parent",
          parent in page.locator(".st-topic-path").inner_text())
    shot(page, "07-sub-topic")
    return parent


def check_save_new_note(page: Page, check: Checks) -> None:
    page.get_by_label("Note title").fill(NOTE_TITLE)
    page.get_by_role("button", name="Save note").click()
    toast = page.locator(".st-toast")
    toast.wait_for()
    check("saving says so", NOTE_TITLE in toast.inner_text(), toast.inner_text())
    expect(page.get_by_role("button", name="Update note")).to_be_visible()
    check("the composer now writes into the saved note", True)
    check("the note is listed in the world's notes",
          page.locator(".st-note-link", has_text=NOTE_TITLE).count() == 1)
    shot(page, "08-saved")


def check_add_to_existing(page: Page, check: Checks) -> None:
    before = page.locator(".st-blocks .st-block").count()
    add_first_passage(page)
    expect(page.locator(".st-blocks .st-block")).to_have_count(before + 1)
    page.get_by_role("button", name="Update note").click()
    page.locator(".st-toast").last.wait_for()
    check("material from the sub-topic is added to the existing note",
          page.locator(".st-save-error").count() == 0)


def check_a_stale_save_is_refused(page: Page, check: Checks) -> None:
    slug = NOTE_TITLE.lower().replace(" ", "-")
    url = f"{BASE}/databases/{WORLD}/collections/research/documents/{slug}"
    current = page.request.get(url).json()
    edited = {**current["document"], "body": current["document"]["body"] + "\n\nEdited elsewhere."}
    page.request.put(url, data=edited, headers={"If-Match": str(current["rev"])})
    page.get_by_role("button", name="Write your own").click()
    page.keyboard.type("A line written while someone else edited.")
    page.get_by_label("Note title").click()
    page.get_by_role("button", name="Update note").click()
    error = page.locator(".st-save-error")
    error.wait_for()
    check("a note changed meanwhile is refused, not overwritten",
          "changed" in error.inner_text().lower(), error.inner_text())
    shot(page, "09-conflict")
    page.get_by_role("button", name="Load the latest version").click()
    expect(page.locator(".st-save-error")).to_have_count(0)
    blocks = page.locator(".st-blocks")
    expect(blocks).to_contain_text("Edited elsewhere.")
    expect(blocks).to_contain_text("A line written while")
    check("the latest version loads, keeping what was added", True)


def steer(page: Page, feedback: str) -> None:
    page.get_by_role("button", name="Steer", exact=True).click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_role("textbox").fill(feedback)
    dialog.get_by_role("button", name="Research again").click()
    page.get_by_text("Here's how I'll search again").wait_for(timeout=JOB_TIMEOUT_MS)


def check_steer_with_a_plan(page: Page, check: Checks, parent: str) -> None:
    """The parent was asked with the plan check on, so its steers stop for one."""
    page.locator(".st-topic-main", has_text=parent).first.click()
    wait_for_draft(page)
    steer(page, "Say more about who kept the lanterns lit.")
    check("a steer's search plan is shown over its draft", True)
    check("the topic says the steer needs an OK",
          "Steer needs your OK" in page.locator(".st-topic.is-selected").inner_text())
    shot(page, "10-steer-plan")
    page.get_by_role("button", name="Cancel the steer").click()
    expect(page.get_by_role("button", name="Steer", exact=True)).to_be_enabled()
    check("a steer cancelled at its plan leaves the draft as it was", True)

    steer(page, "Focus on the oil the lanterns burned.")
    page.get_by_role("button", name="Search with these").click()
    expect(page.locator(".st-banner")).to_have_count(0, timeout=JOB_TIMEOUT_MS)
    # Exactly: the sub-topic's question quotes its parent's.
    titled = page.locator(".st-topic-title", has_text=re.compile(f"^{re.escape(parent)}$"))
    expect(titled).to_have_count(1)
    check("the steered draft replaces its topic rather than sitting beside it", True)


def check_keep_whole_draft(page: Page, check: Checks) -> None:
    page.locator(".st-tree [role=group] .st-topic-main").first.click()
    wait_for_draft(page)
    page.get_by_role("button", name="Keep as note").click()
    page.get_by_role("dialog").get_by_role("button", name="Keep as note").click()
    expect(page.locator(".st-toast").last).to_contain_text("Kept as a research note")
    page.locator(".st-callout.is-ok").wait_for()
    check("a whole draft can be kept as a note", True)
    shot(page, "12-kept")


def check_close_parent(page: Page, check: Checks, parent: str) -> None:
    page.locator(".st-topic-main", has_text=parent).first.click()
    wait_for_draft(page)
    check("sources the note accepted are now cited from the world",
          page.locator(".st-article .st-cite.is-accepted").count() > 0)
    page.get_by_role("button", name="Done with it").click()
    page.get_by_role("button", name="Close the draft").click()
    page.locator(".st-callout.is-ok").wait_for()
    check("a closed topic says where its material went",
          NOTE_TITLE.lower().replace(" ", "-") in page.locator(".st-callout").inner_text())
    shot(page, "11-closed")


def check_narrow_layout(page: Page, check: Checks) -> None:
    page.set_viewport_size({"width": 420, "height": 860})
    switch = page.locator(".st-pane-switch")
    switch.wait_for()
    check("a narrow screen shows one pane at a time", page.locator(".st-pane").count() == 1)
    switch.get_by_role("button", name="Note").click()
    check("the note pane is a tap away", page.locator(".st-note").count() == 1)
    shot(page, "13-narrow")


def main() -> int:
    check = Checks()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        login(page)
        open_studio(page)
        print("asking")
        check_ask_with_a_plan(page, check)
        print("reading")
        check_reading(page, check)
        print("collecting")
        check_collecting(page, check)
        print("digging deeper")
        parent = check_dig_deeper(page, check)
        print("saving")
        check_save_new_note(page, check)
        check_add_to_existing(page, check)
        check_a_stale_save_is_refused(page, check)
        print("steering")
        check_steer_with_a_plan(page, check, parent)
        print("closing")
        check_close_parent(page, check, parent)
        check_keep_whole_draft(page, check)
        check_narrow_layout(page, check)
        check("no script errors on the page", not errors, "; ".join(errors))
        browser.close()
    print(f"\n{check.total - len(check.failures)}/{check.total} checks passed")
    return 1 if check.failures else 0


if __name__ == "__main__":
    sys.exit(main())
