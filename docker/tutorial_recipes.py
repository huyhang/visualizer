"""One recipe per lesson: the real UI, walked as a new writer, photographed.

Recipes run in the course's order against one bare stack, each carrying on
from where the last left the writer -- as a reader's own world grows lesson by
lesson -- so every picture shows what someone following along would see.

A recipe that cannot find what its lesson tells a writer to press fails the
run. That is the point: the lesson has gone stale, and the pictures must not
quietly keep showing an old screen.
"""

from __future__ import annotations

import re

from tutorial_camera import Camera, Ui, around, element, per_size, window, window_top

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


BOOK = "The Last Lamp"


def _tab(ui: Ui, label: str) -> None:
    ui.page.locator(".service-nav").get_by_role("link", name=label, exact=True).click()
    ui.settle()


def start_a_book(ui: Ui, cam: Camera) -> None:
    _tab(ui, "Timeline")
    new_book = lambda page: page.get_by_role("button", name="＋ New book").first
    cam.shoot("start-a-book/books",
              per_size(window_top(220, left=216, top=54), window_top(320, top=54)),
              rings=[new_book])
    new_book(ui.page).click()
    ui.settle()
    ui.quiet_dialog_backdrop()
    title = lambda page: page.get_by_placeholder("The Ember Pact")
    world = lambda page: ui.dialog().locator("select").first
    title(ui.page).fill(BOOK)
    world(ui.page).select_option(WORLD)
    cam.shoot("start-a-book/name-it", around(title, world, pad=36, within=lambda page: ui.dialog()),
              rings=[title, world])
    no_calendar = lambda page: ui.dialog().get_by_role("button", name="No calendar", exact=True)
    create = lambda page: ui.dialog().get_by_role("button", name="Create book", exact=True)
    cam.shoot("start-a-book/create", around(no_calendar, create, pad=20, within=lambda page: ui.dialog()),
              rings=[no_calendar, create])
    create(ui.page).click()
    ui.settle()
    ui.wait_for_toasts()
    cam.shoot("start-a-book/made",
              per_size(window_top(320, left=216, top=54), window_top(460, top=54)))


def _fill_scene(ui: Ui, title: str, start: str, end: str) -> None:
    ui.page.get_by_placeholder("The Harbor Exchange").fill(title)
    _choose(ui, 0, "Last", PLACE)
    _choose(ui, 1, "Ysol", CHARACTER)
    ui.page.get_by_placeholder("e.g. 240").fill(start)
    ui.page.get_by_placeholder("e.g. 264").fill(end)


def _choose(ui: Ui, box: int, typed: str, name: str) -> None:
    ui.page.get_by_placeholder("Search the canon…").nth(box).fill(typed)
    _offered(ui, name).click()
    ui.page.wait_for_timeout(300)


def _offered(ui: Ui, name: str):
    row = ui.page.locator("button.suggest-row").filter(has_text=name).first
    row.wait_for()
    return row


def your_first_scene(ui: Ui, cam: Camera) -> None:
    ui.press("Scenes")
    cam.shoot("your-first-scene/scenes",
              per_size(window_top(260, left=216, top=54), window_top(420, top=54)),
              rings=[lambda page: ui.button("+ New scene")])
    ui.press("+ New scene")
    ui.quiet_dialog_backdrop()
    title = lambda page: page.get_by_placeholder("The Harbor Exchange")
    title(ui.page).fill("The lamp goes out")
    ui.page.get_by_placeholder("Search the canon…").nth(0).fill("Last")
    place = lambda page: _offered(ui, PLACE)
    place(ui.page)
    cam.shoot("your-first-scene/place", around(title, place, pad=30, within=lambda page: ui.dialog()),
              rings=[place])
    place(ui.page).click()
    ui.page.wait_for_timeout(300)
    ui.page.get_by_placeholder("Search the canon…").nth(1).fill("Ysol")
    _offered(ui, CHARACTER).click()
    ui.page.wait_for_timeout(300)
    chosen = lambda page: page.locator("button").filter(has_text="characters / ysolde-marr").first
    characters = lambda page: page.get_by_placeholder("Search the canon…").nth(1)
    cam.shoot("your-first-scene/characters", around(characters, chosen, pad=30, within=lambda page: ui.dialog()),
              rings=[chosen])
    start = lambda page: page.get_by_placeholder("e.g. 240")
    start(ui.page).fill("1")
    ui.page.get_by_placeholder("e.g. 264").fill("2")
    create = lambda page: ui.dialog().get_by_role("button", name="Create scene", exact=True)
    cam.shoot("your-first-scene/when", around(start, create, pad=24, within=lambda page: ui.dialog()),
              rings=[start, create])
    create(ui.page).click()
    ui.settle()
    ui.wait_for_toasts()
    cam.shoot("your-first-scene/made",
              per_size(window_top(560, left=216, top=54), window_top(640, top=54)))


def threads_through_the_story(ui: Ui, cam: Camera) -> None:
    ui.press("+ New scene")
    _fill_scene(ui, "The ship that didn't come", "3", "4")
    ui.dialog().get_by_role("button", name="Create scene", exact=True).click()
    ui.settle()
    ui.wait_for_toasts()
    cam.shoot("threads-through-the-story/two-scenes",
              per_size(window_top(560, left=216, top=54), window_top(640, top=54)))

    ui.page.locator("nav").get_by_role("link", name=BOOK, exact=True).first.click()
    ui.settle()
    ui.press("+ New plotline")
    ui.quiet_dialog_backdrop()
    name = lambda page: page.get_by_placeholder("The Knight's Road")
    name(ui.page).fill("Keeping the light")
    cam.shoot("threads-through-the-story/name-it", around(name, pad=40, within=lambda page: ui.dialog()), rings=[name])
    for scene in ("The lamp goes out", "The ship that didn't come"):
        ui.press("+ Add scene")
        offered = lambda page, scene=scene: page.locator("button.suggest-row").filter(has_text=scene).first
        offered(ui.page).wait_for()
        if scene == "The lamp goes out":
            search = lambda page: page.get_by_placeholder("Search this book's scenes…")
            cam.shoot("threads-through-the-story/add-scene",
                      around(search, offered, pad=30, within=lambda page: ui.dialog()),
                      rings=[offered])
        offered(ui.page).click()
        ui.page.wait_for_timeout(400)
    ui.dialog().get_by_role("button", name="Create plotline", exact=True).click()
    ui.settle()
    ui.wait_for_toasts()
    cam.shoot("threads-through-the-story/created",
              per_size(window_top(420, left=216, top=54), window_top(560, top=54)))



def _books(ui: Ui) -> None:
    ui.page.locator("nav").get_by_role("link", name="Books", exact=True).first.click()
    ui.settle()


def consistent_or_conflicted(ui: Ui, cam: Camera) -> None:
    books = per_size(window_top(260, left=216, top=54), window_top(360, top=54))
    _books(ui)
    cam.shoot("consistent-or-conflicted/conflicted", books,
              rings=[lambda page: page.get_by_text(re.compile(r"^\s*conflicted\s*$", re.IGNORECASE)).first])
    ui.page.get_by_text(BOOK, exact=True).first.click()
    ui.settle()
    # "Report · 1 problem": the button counts what it found.
    ui.page.get_by_role("button", name=re.compile(r"^Report")).first.click()
    ui.settle()
    cam.shoot("consistent-or-conflicted/report",
              per_size(window_top(380, left=216, top=54), window_top(560, top=54)))

    ui.page.locator("nav").get_by_role("link", name=BOOK, exact=True).first.click()
    ui.settle()
    ui.page.get_by_text("Keeping the light", exact=True).first.click()
    ui.settle()
    ui.press("Edit plotline")
    star = lambda page: page.locator("button").filter(has_text="✦").last
    save = lambda page: page.get_by_role("button", name="Save changes", exact=True)
    star(ui.page).click()
    ui.page.wait_for_timeout(400)
    cam.shoot("consistent-or-conflicted/ending", around(star, save, pad=24, within=lambda page: ui.dialog()),
              rings=[star, save])
    save(ui.page).click()
    ui.settle()
    ui.wait_for_toasts()

    _books(ui)
    cam.shoot("consistent-or-conflicted/consistent", books,
              rings=[lambda page: page.get_by_text(re.compile(r"^\s*consistent\s*$", re.IGNORECASE)).first])


SAMPLE_MAP = "/app/src/visualizer/tutorials/static/downloads/lantern-coast-map.svg"


def _on_map(page, x: float, y: float) -> tuple[float, float]:
    """A point on the sample map, from its own 1200 × 760 drawing to the screen."""
    box = page.locator("svg").filter(has=page.locator("title")).first.bounding_box()
    return box["x"] + box["width"] * x / 1200, box["y"] + box["height"] * y / 760


def draw_the_world(ui: Ui, cam: Camera) -> None:
    _tab(ui, "Maps")
    world = lambda page: page.get_by_role("button", name=re.compile(r"^Lantern Coast")).first
    cam.shoot("draw-the-world/worlds",
              per_size(window_top(260, left=216, top=54), window_top(360, top=54)),
              rings=[world])
    world(ui.page).click()
    ui.settle()
    ui.page.locator("input[type=file]").set_input_files(SAMPLE_MAP)
    ui.page.wait_for_timeout(300)
    form = lambda page: page.locator("form").filter(has=page.get_by_role("button", name="Upload SVG")).first
    cam.shoot("draw-the-world/upload", element(form, pad=10),
              rings=[lambda page: ui.button("Upload SVG")])
    ui.press("Upload SVG")
    ui.wait_for_toasts()

    place = lambda page: page.get_by_role("button", name=re.compile(r"^The Last Lighthouse")).first
    place(ui.page).click()
    ui.wait_for_toasts()
    workspace = per_size(window_top(640, left=216, top=54), window())
    cam.shoot("draw-the-world/pick", workspace, rings=[place])
    ui.page.mouse.click(*_on_map(ui.page, 236, 612))
    ui.wait_for_toasts()
    cam.shoot("draw-the-world/save", workspace,
              rings=[lambda page: ui.button("Save")])
    ui.press("Save")
    ui.wait_for_toasts()
    cam.shoot("draw-the-world/made",
              element(lambda page: page.locator("svg").filter(has=page.locator("title")).first))


# In the course's reading order.
RECIPES = (
    before_you_start, a_home_for_your_story, your_first_article, places_and_people,
    start_a_book, your_first_scene, threads_through_the_story, consistent_or_conflicted,
    draw_the_world,
)
