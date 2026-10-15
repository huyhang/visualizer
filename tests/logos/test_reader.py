"""The read-only reader: its shell, its scene projection, and who sees what.

Two halves, both checked here. What the page *offers* -- a shell that needs a
login and carries the shared chrome -- and what the API behind it *allows*: the
scene projection goes through the same book grant as the prose, and it takes no
parameter through which a browser could ask about a scene this volume does not
name.
"""

import json
import re
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from visualizer.auth import ALL_PERMS
from visualizer.logos.app import BOOK_RESOURCE

from .conftest import BOOK, SECTION, VOLUME, login, section_payload

VOLUME_URL = f"/books/{BOOK}/volumes/{VOLUME}"
SCENES_URL = f"{VOLUME_URL}/ui/scenes"
SECTION_SCENES_URL = f"{VOLUME_URL}/sections/{SECTION}/ui/scenes"

_LOGOS = Path(__file__).resolve().parents[2] / "src" / "visualizer" / "logos"


# -- the shell ----------------------------------------------------------------


def test_the_reader_is_the_authenticated_home(client):
    response = client.get("/")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert 'id="content"' in body
    assert 'id="mode-toggle"' in body
    assert 'id="reader-toolbar"' in body
    assert 'id="reading-progress-meter"' in body
    assert 'id="jump-open"' in body
    assert 'id="section-jump"' in body
    assert 'window.__READER_USER__ = "mara"' in body
    # The shared chrome, not a Logos reinvention of it.
    assert 'id="font-toggle"' in body and 'id="theme-toggle"' in body
    assert "prefs.js" in body


def test_the_reader_needs_a_login(app):
    response = app.test_client().get("/", headers={"Accept": "text/html"})
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_a_browser_login_lands_on_the_reader(app):
    browser = app.test_client()
    response = browser.post("/login", data={"username": "mara", "password": "mara-pass"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_the_reader_sits_in_the_nav_as_the_current_service(client):
    html = client.get("/").get_data(as_text=True)
    nav = html.split('<nav class="service-nav"', 1)[1].split("</nav>", 1)[0]
    current = [
        chunk.split('<span class="service-nav-label">')[1].split("<")[0]
        for chunk in nav.split('<a class="service-nav-link')[1:]
        if 'aria-current="page"' in chunk.partition(">")[0]
    ]
    assert current == ["Manuscripts"]
    # Service links belong to the rail; the header carries none of them.
    header = html.split("<header", 1)[1].split("</header>", 1)[0]
    for label in ("Articles", "Timeline", "Maps", "Manuscripts"):
        assert label not in header


def test_the_display_choices_live_in_a_dialog_not_on_the_strip(client):
    """The toolbar is three buttons. Four selects in a row beside the prose is a
    control panel you read past every time you read a chapter."""
    html = client.get("/").get_data(as_text=True)
    toolbar = html.split('id="reader-toolbar"', 1)[1].split("</div>", 1)[0]
    dialog = html.split("<dialog", 1)[1].split("</dialog>", 1)[0]

    assert 'id="mode-toggle"' in toolbar
    assert 'id="settings-open"' in toolbar
    assert 'id="jump-open"' in toolbar
    assert 'id="review-open"' in toolbar
    for field in ("typeface", "leading", "measure", "align"):
        assert f'id="display-{field}"' not in toolbar, field
        assert f'id="display-{field}"' in dialog, field
    assert 'id="display-flow"' not in html
    assert 'id="display-reset"' in dialog
    # Native dialog semantics: labelled, and closable without JavaScript.
    assert 'aria-labelledby="settings-title"' in html
    assert 'method="dialog"' in dialog


def test_the_reader_has_no_whole_volume_flow(client):
    html = client.get("/").get_data(as_text=True)
    assert "The whole volume" not in html
    assert "Reading flow" not in html

    app = (_LOGOS / "static" / "js" / "app.js").read_text()
    assert "api.section(" in app
    assert "api.volume(" not in app


def test_the_reader_offers_search_and_jump_controls(client):
    html = client.get("/").get_data(as_text=True)
    assert 'id="jump-open"' in html
    assert 'id="section-jump"' in html
    assert 'id="jump-search"' in html

    app = (_LOGOS / "static" / "js" / "app.js").read_text()
    assert "filterOutline" in app
    assert "SECTION_PAGE_SIZE" in app
    assert "volume-card" in app and "pagedSectionList" in app


def test_writers_can_create_and_arrange_the_contents(client):
    html = client.get("/").get_data(as_text=True)
    app = (_LOGOS / "static" / "js" / "app.js").read_text()
    api = (_LOGOS / "static" / "js" / "api.js").read_text()
    manager = (_LOGOS / "static" / "js" / "contentmanager.js").read_text()

    for dialog in (
        "volume-create-dialog",
        "volume-rename-dialog",
        "section-create-dialog",
        "section-move-dialog",
    ):
        assert f'id="{dialog}"' in html
    for label in (
        "New volume", "New section", "Rename volume", "Manage contents", "Move…",
    ):
        assert label in app
    assert "Move interrupted" in app
    assert "Finish move" in app
    assert "Move connection lost" in manager
    assert "Retry move" in manager
    # Touch raises no drag events, so the handles carry a pointer gesture too
    # and the rows carry the geometry its hit-test reads.
    touch = (_LOGOS / "static" / "js" / "touchdrag.js").read_text()
    assert "onpointerdown" in app
    assert '"data-section"' in app and '"data-volume"' in app
    assert "setPointerCapture" in touch
    # Every kind a volume can hold is offered, not just chapters.
    assert 'id="section-create-kind"' in html
    for operation in (
        "reorderVolumes", "reorderSections", "moveSection", "updateVolume",
    ):
        assert operation in api


def _container_block(sheet: str, condition: str) -> str:
    body = sheet.split(f"@container ({condition}) {{", 1)[1].split("\n}\n", 1)[0]
    return re.sub(r"/\*.*?\*/", "", body, flags=re.DOTALL)


def test_an_action_group_compacts_on_its_own_width_not_the_window_s():
    """A row of actions asks "do the words still fit in this row", which the
    window cannot answer: the text-size control sets a root font-size, and a
    `max-width: 820px` query measures CSS pixels and never moves, so the row
    used to wrap at one reading size and not another. The hook is
    `.compact-actions`, which the markup has always carried and no stylesheet
    defined, and the threshold is in rem because `.content` is capped in rem --
    turning the size up shrinks the row in rem while the window stands still.

    Glyphs are the fallback for a row that has run out of room, not the resting
    state of a roomy one, so the threshold sits below the measure: the words
    stay put on a desktop and give way only when the row genuinely narrows.
    """
    sheet = (_LOGOS / "static" / "reader.css").read_text()
    app = (_LOGOS / "static" / "js" / "app.js").read_text()
    assert 'class: "book-actions compact-actions"' in app
    assert ".compact-actions { container-type: inline-size; }" in sheet

    block = _container_block(sheet, "max-width: 56rem")
    assert ".compact-actions .compact-action-glyph" in block
    assert ".compact-actions .compact-action-label" in block
    # A container query styles a container's contents, never the container, so
    # a rule naming `.compact-actions` alone in here would never apply.
    assert "flex-wrap" not in block, "dead rule: cannot style the container"
    # The glyph box stays in px. It is an icon, and the largest reading size on
    # the narrowest phone is where a rem-sized one would spill.
    assert "width: 36px" in block

    # A threshold only means anything if the words fit above it, and this row
    # is the one that did not: with "series" on three of the labels it wanted
    # about 964px against the 944 the measure gives, so one action dropped to a
    # second line. Estimated the same way, from the widest seven labels the row
    # can draw at once -- 8.5px a character plus each button's padding and
    # border, plus the gaps between them.
    body = _function_body(app, "function bookActions(")
    labels = sorted(
        re.findall(r'"([A-Z][A-Za-z ]{2,})"', body), key=len, reverse=True,
    )[:7]
    # Pessimistic on purpose: both arms of the arranging toggle are counted,
    # though only one is ever on screen.
    assert len(labels) == 7, labels
    assert "Manage contents" in labels, labels
    width = sum(len(label) * 8.5 + 25.6 + 2 for label in labels) + 8.8 * 6
    assert width < 56 * 16, (round(width), labels, "wider than the threshold")


def test_logos_folds_a_thing_the_way_its_siblings_do():
    """Akasha's tree browser and Chronos's story graph both mark a closed
    disclosure `+` and an open one `−`. A fourth service inventing its own
    glyph is the kind of drift that makes four services feel like four apps."""
    sheet = (_LOGOS / "static" / "reader.css").read_text()
    twisty = sheet.split(".twisty {", 1)[1].split(".volume-summary:hover", 1)[0]
    assert 'content: "+";' in twisty
    assert 'content: "−";' in twisty

    # Driven off `[open]`, so opening a volume *for* the reader -- the one
    # holding their place -- shows the same mark as opening it themselves.
    assert ".volume-card[open] .twisty::after" in sheet
    app = (_LOGOS / "static" / "js" / "app.js").read_text()
    assert 'class: "twisty"' in app


def test_the_book_page_offers_the_furthest_read_and_opens_where_you_are():
    """Two marks, two jobs. Continue points at the furthest section reached;
    the volume that opens is the one you were last in, so going back to
    re-read shows you where you are without losing the way forward."""
    app = (_LOGOS / "static" / "js" / "app.js").read_text()
    assert "sectionAhead(" in app
    assert "marks.furthest" in app and "marks.last" in app
    position = (_LOGOS / "static" / "js" / "position.js").read_text()
    assert "export function advance(" in position


def test_what_a_mode_shows_is_a_tooltip_not_standing_text(client):
    """It is an explanation you want on the way in and never again."""
    html = client.get("/").get_data(as_text=True)
    assert "Prose alone" not in html
    assert "nothing from any other service" not in html
    # …and it is not simply missing: `app.js` writes it onto the button.
    app = (_LOGOS / "static" / "js" / "app.js").read_text()
    assert "Prose and bookmarks — nothing from any other service" in app
    assert "modeButton.title" in app


def test_the_mode_switch_is_not_in_the_header(client):
    """It acts on the prose, so it lives with the prose.

    The header is the one part of every service that looks identical, and a
    control only Logos has would break that on sight.
    """
    html = client.get("/").get_data(as_text=True)
    header = html.split("<header", 1)[1].split("</header>", 1)[0]
    assert 'id="mode-toggle"' not in header
    assert 'id="display-typeface"' not in header


def test_reader_forms_never_submit_to_an_implicit_endpoint(client):
    """Reader writes are explicit JSON calls; forms only close native dialogs."""
    html = client.get("/").get_data(as_text=True)
    forms = re.findall(r"<form[^>]*>", html)
    assert forms, "expected at least the log-out form"
    for form in forms:
        assert 'method="dialog"' in form or "logout" in html.split(form, 1)[1][:200], form
    posts = [f for f in forms if 'method="post"' in f]
    assert len(posts) == 1, posts


def test_the_toolbar_offers_exactly_the_stored_choices():
    """The markup and the allowlist that validates it cannot drift.

    The options are written in the template so the page has controls before the
    module loads. That is a copy of what ``preferences.js`` will accept, and a
    copy nobody checks is a copy that goes stale: add a typeface to the select
    and every reader who picks it silently gets the default back.
    """
    markup = (_LOGOS / "templates" / "reader.html").read_text()
    module = (_LOGOS / "static" / "js" / "preferences.js").read_text()
    allowlist = module.split("CHOICES = Object.freeze(", 1)[1].split("});", 1)[0]

    for field in re.findall(r'^\s+(\w+): \[', allowlist, re.MULTILINE):
        if field == "mode":
            continue  # a button, not a select
        allowed = re.findall(
            rf'{field}: \[([^\]]*)\]', allowlist,
        )[0].replace('"', "").replace(" ", "").split(",")
        select = markup.split(f'id="display-{field}"', 1)[1].split("</select>", 1)[0]
        assert re.findall(r'value="([^"]+)"', select) == allowed, field


_IMPORT = re.compile(r'import\s+(?:([\w${},\s*]+?)\s+from\s+)?["\'](\.[^"\']+)["\']')
_EXPORT = re.compile(r"export\s+(?:async\s+)?(?:function|class|const|let|var)\s+([\w$]+)")


def _imports(module: Path):
    for names, target in _IMPORT.findall(module.read_text()):
        yield (module.parent / target).resolve(), [
            name.split(" as ")[0].strip()
            for name in names.strip("{} \n").split(",")
            if name.strip()
        ]


def test_every_import_resolves_to_a_module_that_exports_it():
    """The failure a rename makes, and the one that fails loudest and latest.

    There is no build step, so nothing checks these specifiers until a browser
    does -- and then the whole page is blank with one line in a console nobody
    is watching. The tests below all import the modules individually, so only
    this one sees the graph.
    """
    modules = sorted((_LOGOS / "static" / "js").glob("*.js"))
    assert modules, "the reader ships no modules at all"
    for module in modules:
        for target, names in _imports(module):
            assert target.exists(), f"{module.name} imports missing {target.name}"
            missing = sorted(set(names) - set(_EXPORT.findall(target.read_text())))
            assert not missing, f"{module.name} imports {missing} absent from {target.name}"


def test_the_entrypoint_reaches_every_module():
    """A module nothing imports is dead code, or a wire-up someone forgot."""
    js = _LOGOS / "static" / "js"
    reached, queue = set(), [js / "app.js"]
    while queue:
        current = queue.pop()
        if current in reached:
            continue
        reached.add(current)
        queue.extend(target for target, _ in _imports(current))
    assert {path.name for path in reached} == {p.name for p in js.glob("*.js")}


def test_every_stored_choice_actually_changes_something():
    """Each preference becomes a ``data-`` attribute on <html>; the stylesheet
    has to act on it. A choice with no rule behind it is a control that does
    nothing, which looks exactly like a bug in the saving.
    """
    js = _LOGOS / "static" / "js"
    allowlist = (js / "preferences.js").read_text()
    allowlist = allowlist.split("CHOICES = Object.freeze(", 1)[1].split("});", 1)[0]
    fields = re.findall(r"^\s+(\w+): \[", allowlist, re.MULTILINE)
    assert "mode" in fields and "flow" not in fields

    sheet = (_LOGOS / "static" / "reader.css").read_text()
    for field in fields:
        values = re.findall(rf"{field}: \[([^\]]*)\]", allowlist)[0]
        for value in re.findall(r'"([^"]+)"', values):
            assert f'[data-{field}="{value}"]' in sheet, (
                f'nothing in reader.css responds to [data-{field}="{value}"]'
            )


def test_the_stylesheet_only_spends_tokens_that_exist():
    """A typo'd `var(--surfce)` is silently transparent, and only in one rule.

    Three legitimate sources: this sheet, the shared palette it links first, and
    the two geometry tokens `service-nav.css` declares. Anything else is a typo.
    """
    shared = _LOGOS.parent / "static"
    sheet = (_LOGOS / "static" / "reader.css").read_text()
    available = set(re.findall(r"(--[a-z0-9-]+)\s*:", sheet))
    for name in ("tokens.css", "service-nav.css"):
        available |= set(re.findall(r"(--[a-z0-9-]+)\s*:", (shared / name).read_text()))

    undefined = sorted(set(re.findall(r"var\((--[a-z0-9-]+)", sheet)) - available)
    assert not undefined, f"reader.css reads {undefined} but nothing defines them"


def test_the_reader_assets_are_served(client):
    for path in (
        "/static/reader.css",
        "/static/logos-glyph.svg",
        "/static/logos-icon.svg",
        "/static/js/app.js",
        "/static/js/compactaction.js",
        "/static/js/api.js",
        "/static/js/dom.js",
        "/static/js/prose.js",
        "/static/js/preferences.js",
        "/static/js/position.js",
        "/static/js/progress.js",
        "/static/js/navigation.js",
        "/static/js/outline.js",
        "/static/js/contents.js",
        "/static/js/contentmanager.js",
        "/static/js/touchdrag.js",
        "/static/js/review.js",
        "/static/js/writerlinks.js",
        "/static/js/shared/prefs.js",
        "/static/shared/service-nav.css",
    ):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.get_data(), path


def test_logos_has_a_deliberate_mobile_action_hierarchy(client):
    html = client.get("/").get_data(as_text=True)
    sheet = (_LOGOS / "static" / "reader.css").read_text()
    app = (_LOGOS / "static" / "js" / "app.js").read_text()

    # The writing page's own hierarchy is the bundle's (frontend/src/logos),
    # held there by vitest and in a browser by docker/smoke_logos_writer.py.
    assert html.count("compact-action") >= 6
    assert "compact-actions" in app
    assert ".compact-action-label" in sheet
    assert ".compact-action-glyph" in sheet
    assert "min-height: 44px" in sheet
    assert "var(--service-nav-h)" in sheet
    assert "100dvh" in sheet


def _function_body(source: str, declaration: str) -> str:
    """The brace-matched body of a named function, so a glyph in one action
    group is never confused with the same glyph in another. The parameter list
    is skipped first: `function topbar({ base, ... })` opens a brace of its own
    that is not the body."""
    start = source.index(declaration) + len(declaration)
    opening = source.index("{", source.index(")", start))
    depth, index = 0, opening
    while index < len(source):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                break
        index += 1
    return source[opening:index]


def _between(source: str, opening: str, closing: str) -> str:
    start = source.index(opening) + len(opening)
    return source[start:source.index(closing, start)]


def _glyphs_in(body: str) -> list[str]:
    """Every glyph a group draws: the second positional argument of a local
    ``button``/``formatButton`` helper, a named ``glyph:``, the two arms of a
    state ternary, and the bare ``text:`` marks on the drawer toggles."""
    found = re.findall(r'\w+\(\s*"[^"]*",\s*"([^"]+)"', body)
    found += re.findall(r'glyph:\s*"([^"]+)"', body)
    found += re.findall(r'text:\s*"(\S{1,2})"', body)
    found += [
        arm
        for pair in re.findall(r'\?\s*"([^"]+)"\s*:\s*"([^"]+)"', body)
        for arm in pair
        if len(arm) <= 2
    ]
    return found


def test_one_action_group_never_draws_two_actions_the_same_way(client):
    """A glyph is the whole of a compacted button, so two actions wearing the
    same mark in one row are indistinguishable -- the reader cannot tell which
    of them makes a volume and which makes a section. Distinctness is a
    property of the *group*: the contents page's `Search` and the reader
    toolbar's share both a mark and a word, and that is correct because they
    never appear together, which is why this is not one global set.
    """
    app = (_LOGOS / "static" / "js" / "app.js").read_text()
    # The writing page's bar and formatting tools are the bundle's, and
    # frontend/src/logos/components/writer/chrome.test.tsx holds them to this.
    groups = {
        "book actions": _glyphs_in(_function_body(app, "function bookActions(")),
    }
    html = client.get("/").get_data(as_text=True)
    toolbar = html.split('id="reader-toolbar"', 1)[1].split("</div>", 1)[0]
    groups["reader toolbar"] = re.findall(
        r'class="compact-action-glyph"[^>]*>([^<]+)<', toolbar
    )

    for name, glyphs in groups.items():
        # Without this the regex could quietly match nothing and the test would
        # pass by finding no duplicates among no glyphs.
        assert len(glyphs) >= 4, (name, glyphs)
        duplicates = {g for g in glyphs if glyphs.count(g) > 1}
        assert not duplicates, (name, sorted(duplicates), glyphs)


def test_the_reading_mode_button_says_which_mode_it_is_in(client):
    """The label is visually hidden on a phone, so a mode toggle whose glyph
    never changes tells a phone reader nothing about which view they are in."""
    app = (_LOGOS / "static" / "js" / "app.js").read_text()
    modes = _between(app, "const MODE_TEXT = {", "};")
    marks = re.findall(r'\[\s*"[^"]+",\s*"([^"]+)"', modes)

    assert len(marks) == 2, modes
    assert marks[0] != marks[1], marks
    assert 'querySelector(".compact-action-glyph").textContent' in app


# -- the scene projection -----------------------------------------------------


def test_full_view_shows_only_the_scenes_the_sections_name(section, chronos_gateway):
    chronos_gateway.add_event(BOOK, "opening", title="The gate opens", when="Day 5")
    chronos_gateway.add_event(BOOK, "climax", title="A scene nobody wrote up")

    body = section.get(SCENES_URL).get_json()

    assert body == {
        "book": BOOK,
        "volume": VOLUME,
        "sections": [
            {
                "section": SECTION,
                "scenes": [
                    {
                        "id": "opening",
                        "title": "The gate opens",
                        "when": "Day 5",
                        "missing": False,
                    }
                ],
            }
        ],
    }


def test_section_view_fetches_only_its_own_linked_scenes(section, chronos_gateway):
    chronos_gateway.add_event(BOOK, "opening", title="The gate opens", when="Day 5")
    chronos_gateway.add_event(BOOK, "climax", title="The final clash", when="Day 9")
    assert section.post(
        f"{VOLUME_URL}/sections/finale",
        json=section_payload(title="Finale", events=("climax",)),
    ).status_code == 201

    body = section.get(SECTION_SCENES_URL).get_json()

    assert body == {
        "book": BOOK,
        "volume": VOLUME,
        "section": SECTION,
        "scenes": [
            {
                "id": "opening",
                "title": "The gate opens",
                "when": "Day 5",
                "missing": False,
            }
        ],
    }


def test_a_deleted_scene_is_flagged_rather_than_dropped(volume, chronos_gateway):
    """The prose still says a scene is behind this section. Say it is gone."""
    chronos_gateway.add_event(BOOK, "ghost")
    volume.post(
        f"{VOLUME_URL}/sections/{SECTION}", json=section_payload(events=("ghost",))
    )
    chronos_gateway.add_book(BOOK, "The Ember Pact", events=())

    (scene,) = volume.get(SCENES_URL).get_json()["sections"][0]["scenes"]

    assert scene == {"id": "ghost", "title": "ghost", "when": "", "missing": True}


def test_one_scene_realised_twice_is_looked_up_once(volume, chronos_gateway):
    chronos_gateway.add_event(BOOK, "opening", title="The gate opens", when="Day 5")
    for section_id in ("first", "second"):
        assert volume.post(
            f"{VOLUME_URL}/sections/{section_id}",
            json=section_payload(title=section_id, events=("opening",)),
        ).status_code == 201

    sections = volume.get(SCENES_URL).get_json()["sections"]

    assert [row["section"] for row in sections] == ["first", "second"]
    assert [row["scenes"][0]["title"] for row in sections] == [
        "The gate opens", "The gate opens",
    ]


def test_a_volume_with_no_linked_scenes_says_so_without_asking_chronos(volume):
    assert volume.post(
        f"{VOLUME_URL}/sections/{SECTION}", json=section_payload(events=())
    ).status_code == 201

    body = volume.get(SCENES_URL).get_json()

    assert body["sections"] == [{"section": SECTION, "scenes": []}]


def test_scenes_follow_section_order_not_insertion_order(volume, chronos_gateway):
    chronos_gateway.add_event(BOOK, "opening", title="Opening")
    for section_id in ("epilogue", "prologue"):
        volume.post(
            f"{VOLUME_URL}/sections/{section_id}",
            json=section_payload(kind=section_id, title=None, events=("opening",)),
        )
    reordered = volume.get(f"{VOLUME_URL}").get_json()
    volume.put(
        f"{VOLUME_URL}/section-order",
        json={"sections": ["prologue", "epilogue"]},
        headers={"If-Match": f'"{reordered["rev"]}"'},
    )

    body = volume.get(SCENES_URL).get_json()

    assert [row["section"] for row in body["sections"]] == ["prologue", "epilogue"]


# -- who may read -------------------------------------------------------------


def test_scenes_need_the_same_book_grant_the_prose_needs(app, auth_store):
    auth_store.create_user("solo", generate_password_hash("solo-pass"))
    browser = app.test_client()
    assert login(browser, "solo").status_code == 200

    assert browser.get(SCENES_URL).status_code == 403
    assert browser.get(SECTION_SCENES_URL).status_code == 403
    # No grant means forbidden even where there would be nothing to find, so
    # the reader cannot be used to discover which books exist.
    assert browser.get("/books/no-such-book/volumes/one/ui/scenes").status_code == 403


def test_scenes_on_a_book_that_is_gone_are_not_found(client, auth_store):
    auth_store.grant_owner(
        "mara", "ghost-book", None, None, list(ALL_PERMS), resource_type=BOOK_RESOURCE
    )
    response = client.get("/books/ghost-book/volumes/one/ui/scenes")

    assert response.status_code == 404
    assert response.get_json()["code"] == "BOOK_NOT_FOUND"


def test_scenes_on_a_volume_that_is_gone_are_not_found(client):
    response = client.get(f"/books/{BOOK}/volumes/nope/ui/scenes")

    assert response.status_code == 404
    assert response.get_json()["code"] == "VOLUME_NOT_FOUND"


def test_scenes_need_a_login(app):
    assert app.test_client().get(
        SCENES_URL, headers={"Accept": "application/json"}
    ).status_code == 401
    assert app.test_client().get(
        SECTION_SCENES_URL, headers={"Accept": "application/json"}
    ).status_code == 401


def test_a_read_only_collaborator_may_open_the_reader_and_its_scenes(reader, section):
    assert reader.get("/").status_code == 200
    assert reader.get(f"{VOLUME_URL}/manuscript").status_code == 200
    assert reader.get(SCENES_URL).status_code == 200
    assert reader.get(SECTION_SCENES_URL).status_code == 200


# -- preloading the module graph -------------------------------------------


def test_the_shell_preloads_every_module_the_entrypoint_reaches(client):
    """The browser would otherwise find the modules a layer at a time, one
    round trip each, before the reader can run."""
    from visualizer.logos.reader_modules import reader_modules

    html = client.get("/").get_data(as_text=True)
    preloaded = re.findall(r'<link rel="modulepreload" href="[^"]*/js/([^"?]+)\?v=\w+">', html)
    js = _LOGOS / "static" / "js"
    assert set(preloaded) == {p.name for p in js.glob("*.js")}
    assert set(reader_modules()) == {p.name for p in js.glob("*.js")} - {"app.js"}
    # Asked for in the head, well before the script that imports them.
    assert html.index("modulepreload") < html.index('<script type="module"')


def test_every_module_is_named_by_its_version_and_imports_find_theirs(client):
    """The modules import each other by plain relative paths; the import map
    is how those imports reach the versioned, cacheable files -- so it maps
    every module, and comes before the first one is asked for."""
    html = client.get("/").get_data(as_text=True)
    raw = re.search(r'<script type="importmap">(.*?)</script>', html, re.DOTALL).group(1)
    mapped = json.loads(raw)["imports"]
    preloads = re.findall(r'<link rel="modulepreload" href="([^"]+)">', html)
    assert sorted(mapped.values()) == sorted(preloads)
    for plain, versioned in mapped.items():
        assert versioned.startswith(plain + "?v=")
    assert html.index('type="importmap"') < html.index("modulepreload")
    assert re.search(r'<script type="module" src="[^"]*/js/app\.js\?v=\w+">', html)
    for sheet in ("tokens.css", "reader.css", "service-nav.css"):
        assert re.search(rf'href="[^"]*{re.escape(sheet)}\?v=\w+"', html)


@pytest.mark.parametrize("files, reached", [
    ({"app.js": 'import { a } from "./a.js";', "a.js": "export const a = 1;"}, ["a.js"]),
    ({"app.js": 'import "./side.js";', "side.js": ""}, ["side.js"]),
    (
        {
            "app.js": 'import { a } from "./a.js";\nimport { b } from "./b.js";',
            "a.js": 'import { c } from "./c.js";',
            "b.js": 'import { a } from "./a.js";',
            "c.js": 'import { a } from "./a.js";',
        },
        ["a.js", "b.js", "c.js"],
    ),
    ({"app.js": 'import { gone } from "./gone.js";'}, ["gone.js"]),
    ({"app.js": 'const url = "https://example.com/x.js";'}, []),
])
def test_the_module_graph_follows_each_import_once(tmp_path, files, reached):
    from visualizer.logos.reader_modules import module_graph

    for name, text in files.items():
        (tmp_path / name).write_text(text)
    assert module_graph(tmp_path) == reached
