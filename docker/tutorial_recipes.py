"""One recipe per lesson: the real UI, walked as a new writer, photographed.

Recipes run in the course's order against one bare stack, each carrying on
from where the last left the writer -- as a reader's own world grows lesson by
lesson -- so every picture shows what someone following along would see.

A recipe that cannot find what its lesson tells a writer to press fails the
run. That is the point: the lesson has gone stale, and the pictures must not
quietly keep showing an old screen.
"""

from __future__ import annotations

from tutorial_camera import Camera, Ui, element, per_size, window, window_top

WRITER = {"username": "wren", "email": "wren@example.com", "password": "first-novel-2026"}
WORLD, CATEGORY, CHARACTER = "lantern-coast", "characters", "Ysolde Marr"


def before_you_start(ui: Ui, cam: Camera) -> None:
    ui.go("/register")
    card = lambda page: page.locator(".card").first
    ui.fill("Username", WRITER["username"])
    ui.fill("Email", WRITER["email"])
    ui.fill("Password", WRITER["password"])
    cam.shoot("before-you-start/register", element(card, pad=12),
              rings=[lambda page: ui.button("Register")])
    ui.press("Register")

    ui.fill("Username", WRITER["username"])
    cam.shoot("before-you-start/log-in", element(card, pad=12),
              rings=[lambda page: ui.button("Log in")])
    ui.fill("Password", WRITER["password"])
    ui.press("Log in")

    cam.shoot("before-you-start/tabs", window(),
              rings=[lambda page: page.locator(".service-nav")])
    cam.shoot(
        "before-you-start/comfort",
        per_size(window_top(54, left=760), window_top(54)),
        rings=[lambda page: page.locator("#font-toggle"), lambda page: page.locator("#theme-toggle")],
    )


def a_home_for_your_story(ui: Ui, cam: Camera) -> None:
    content = per_size(window_top(300, left=216, top=54), window_top(420, top=54))
    cam.shoot("a-home-for-your-story/your-worlds", content,
              rings=[lambda page: ui.button("＋ New world")])
    ui.press("＋ New world")
    dialog = ui.dialog()
    ui.quiet_dialog_backdrop()
    ui.fill("World", WORLD, within=dialog)
    cam.shoot("a-home-for-your-story/name-it", element(lambda page: ui.dialog()),
              rings=[lambda page: ui.field("World", ui.dialog())])
    ui.fill("First category", CATEGORY, within=dialog)
    cam.shoot("a-home-for-your-story/first-category", element(lambda page: ui.dialog()),
              rings=[lambda page: ui.field("First category", ui.dialog()),
                     lambda page: ui.dialog().get_by_role("button", name="Create", exact=True)])
    dialog.get_by_role("button", name="Create", exact=True).click()
    ui.settle()
    ui.wait_for_toasts()
    cam.shoot("a-home-for-your-story/created",
              per_size(window_top(300, left=216, top=54), window_top(420, top=54)))


def your_first_article(ui: Ui, cam: Camera) -> None:
    content = per_size(window_top(240, left=216, top=54), window_top(380, top=54))
    cam.shoot("your-first-article/start", content,
              rings=[lambda page: ui.button("＋ New article")])
    ui.press("＋ New article")
    ui.quiet_dialog_backdrop()
    title = lambda page: page.get_by_placeholder("Aragorn", exact=True)
    title(ui.page).fill(CHARACTER)
    cam.shoot("your-first-article/name-it", element(lambda page: ui.dialog()), rings=[title])
    ui.press("Continue")

    ui.page.locator("textarea").first.fill(
        "Ysolde keeps the last lighthouse on the Lantern Coast.\n\n"
        "== Early life ==\n"
        "Born in a storm, she learned the lamp before she learned to read."
    )
    ui.wait_for_toasts()
    editor = per_size(window_top(330, left=516, top=54), window_top(560, top=54))
    cam.shoot("your-first-article/write", editor,
              rings=[lambda page: page.locator("textarea").first])
    cam.shoot("your-first-article/save",
              per_size(window_top(80, left=860, top=56), window_top(96, top=54)),
              rings=[lambda page: ui.button("Create")])
    ui.press("Create")
    ui.wait_for_toasts()
    cam.shoot("your-first-article/made",
              per_size(window_top(330, left=216, top=54), window_top(520, top=54)))


PLACE = "The Last Lighthouse"


def places_and_people(ui: Ui, cam: Camera) -> None:
    ui.page.locator("nav.crumbs").get_by_role("link", name="Lantern Coast", exact=True).click()
    ui.settle()
    content = per_size(window_top(260, left=216, top=54), window_top(400, top=54))
    cam.shoot("places-and-people/world", content,
              rings=[lambda page: ui.button("＋ New category")])
    ui.press("＋ New category")
    ui.quiet_dialog_backdrop()
    ui.fill("Category", "locations", within=ui.dialog())
    cam.shoot("places-and-people/locations", element(lambda page: ui.dialog()),
              rings=[lambda page: ui.field("Category", ui.dialog()),
                     lambda page: ui.dialog().get_by_role("button", name="Create", exact=True)])
    ui.dialog().get_by_role("button", name="Create", exact=True).click()
    ui.settle()
    ui.wait_for_toasts()

    ui.press("＋ New article")
    ui.page.get_by_placeholder("Aragorn", exact=True).fill(PLACE)
    ui.press("Continue")
    ui.page.locator("textarea").first.fill(
        "The only light left on the Lantern Coast, at the end of a mile of rock."
    )
    ui.wait_for_toasts()
    cam.shoot("places-and-people/place",
              per_size(window_top(300, left=516, top=54), window_top(480, top=54)),
              rings=[lambda page: ui.button("Create")])
    ui.press("Create")
    ui.wait_for_toasts()

    ui.go(f"/#/{WORLD}/{CATEGORY}/ysolde-marr")
    ui.press("Edit")
    area = ui.page.locator("textarea").first
    area.click()
    area.press("Control+End")
    area.type(" Home is ")
    found = lambda page: page.locator(".link-picker .lp-item").first  # the place

    def find_the_place(page) -> None:
        # The finder is placed where it opens, so open it afresh at each width.
        page.keyboard.press("Escape")
        area.click()
        area.press("Control+End")
        ui.press("🔗 Insert link")
        page.keyboard.type("Last")
        found(page).wait_for()
        page.wait_for_timeout(400)

    cam.shoot("places-and-people/link",
              per_size(window_top(520, left=516, top=180), window_top(620, top=150)),
              rings=[found], prepare=find_the_place)
    find_the_place(ui.page)
    found(ui.page).click()
    area.type(".")

    ui.press("＋ Add a fact")
    ui.page.get_by_placeholder("field", exact=True).fill("Home")
    ui.page.get_by_placeholder("value (comma-separates into a list)").fill(PLACE)
    facts = ui.page.get_by_role("heading", name="Article details (infobox)")
    facts.scroll_into_view_if_needed()
    cam.shoot("places-and-people/fact",
              element(lambda page: page.locator("section, div").filter(has=facts).last, pad=8),
              rings=[lambda page: page.get_by_placeholder("field", exact=True)])
    ui.press("Save")
    ui.wait_for_toasts()
    ui.page.evaluate("() => window.scrollTo(0, 0)")
    cam.shoot("places-and-people/made",
              per_size(window_top(360, left=216, top=54), window_top(560, top=54)))


# In the course's reading order.
RECIPES = (before_you_start, a_home_for_your_story, your_first_article, places_and_people)
