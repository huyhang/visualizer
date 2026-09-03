"""The shared service navigation, and which item it calls current.

Articles/Timeline/Maps used to be a group inside each header; they are a left
rail (a bottom tab bar on a phone) now, so the header cannot spill onto a
second row. Admin and Account used to sit in that group too; they are one
"Access" link leading to a page with a tab each.

The active state is the part worth guarding. ``service_links.current`` says
which *app* is serving the request, which is not which *page* you are on: every
one of these pages is served by akasha, and keying the highlight on it used to
mark Articles as ``aria-current="page"`` while you stood on Access.
"""

import re
from pathlib import Path

import mongomock
from conftest import login
from werkzeug.security import generate_password_hash

from visualizer.akasha.app import create_app
from visualizer.akasha.store import DocumentStore
from visualizer.auth import AuthStore

_SRC = Path(__file__).resolve().parents[2] / "src" / "visualizer"

SERVICES = ("akasha", "chronos", "prithvi", "logos")

# Every page-level sheet loaded alongside the shared nav. None of them may
# redeclare the palette any more -- `static/tokens.css` owns it.
STYLESHEETS = {
    "akasha editor": "akasha/static/editor.css",
    "akasha shell": "akasha/static/base.css",
    "chronos": "chronos/static/visualizer.css",
    "prithvi": "prithvi/static/maps.css",
    "logos": "logos/static/reader.css",
    "auth pages": "static/auth.css",
}

# Every template that includes the navigation, and so must link the palette.
SHELLS = (
    "akasha/templates/editor.html",
    "akasha/templates/base.html",
    "chronos/templates/visualizer.html",
    "prithvi/templates/maps.html",
    "logos/templates/reader.html",
    "auth/templates/base.html",
)


def _header(html):
    """Just the header, so "no service links in here" can be asserted."""
    return html.split("<header", 1)[1].split("</header>", 1)[0]


def _nav(html):
    return html.split('<nav class="service-nav"', 1)[1].split("</nav>", 1)[0]


def _nav_current(html):
    """The nav label marked ``aria-current="page"``, or ``None`` for no item."""
    for link in _nav(html).split('<a class="service-nav-link')[1:]:
        tag, _, rest = link.partition(">")
        if 'aria-current="page"' in tag:
            return rest.split('<span class="service-nav-label">')[1].split("<")[0]
    return None


def _access_is_current(html):
    return "access-link active" in html


def test_the_editor_has_the_service_nav(client):
    html = client.get("/").get_data(as_text=True)
    assert 'class="service-nav"' in html
    assert 'aria-label="Applications"' in html
    assert all(
        label in html for label in ("Articles", "Timeline", "Maps", "Manuscripts")
    )
    assert "http://localhost:5003" in html          # default chronos URL
    assert "http://localhost:5004" in html          # default prithvi URL
    assert "http://localhost:5005" in html          # default logos URL
    # Admin is not a header link even for an admin: it is a tab inside Access,
    # so the nav carries services and nothing else.
    assert ">Admin<" not in html
    assert ">Access<" in html


def test_no_service_link_is_left_in_the_header(client):
    """The whole point: the widest group is gone, so the row cannot wrap."""
    header = _header(client.get("/").get_data(as_text=True))
    assert "Articles" not in header
    assert "Timeline" not in header
    assert "Maps" not in header


def test_the_editor_marks_articles_current(client):
    html = client.get("/").get_data(as_text=True)
    assert _nav_current(html) == "Articles"
    assert not _access_is_current(html)


def test_the_utility_pages_mark_no_service_current(client):
    """Access is not Articles, and a nav that says otherwise is lying.

    Before this, every one of these highlighted Articles and told a screen
    reader it was the current page.
    """
    for path in ("/account", "/admin", "/change-password"):
        html = client.get(path).get_data(as_text=True)
        assert 'class="service-nav"' in html, path
        assert _nav_current(html) is None, path
        assert _access_is_current(html), path


def test_aria_current_page_appears_only_where_it_is_true(client):
    """``page`` is a promise about an exact URL, not about a section.

    Scoped to the navigation and the header on purpose. The Access page has a
    tab strip of its own, and those tabs *do* point at the page you are on, so
    their ``aria-current="page"`` is correct and none of this test's business.
    """
    assert 'aria-current="page"' in _nav(client.get("/").get_data(as_text=True))
    for path in ("/account", "/admin", "/change-password"):
        html = client.get(path).get_data(as_text=True)
        assert 'aria-current="page"' not in _nav(html), path
        # Access still says "you are in here", with the weaker, truthful value.
        assert 'aria-current="page"' not in _header(html), path
        assert 'aria-current="true"' in _header(html), path


def test_the_service_nav_urls_are_configurable():
    client_db = mongomock.MongoClient()
    auth = AuthStore(client_db)
    auth.create_user("mara", generate_password_hash("pw"), role="user")
    app = create_app(
        DocumentStore(client_db), auth, secret_key="s",
        akasha_url="https://world.example/akasha",
        chronos_url="https://world.example/chronos",
        prithvi_url="https://world.example/maps",
        logos_url="https://world.example/manuscripts",
    )
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)
    c = app.test_client()
    assert login(c, "mara", "pw").status_code == 200
    html = c.get("/").get_data(as_text=True)
    assert "https://world.example/chronos" in html
    assert "https://world.example/maps" in html
    assert "https://world.example/manuscripts" in html
    assert _nav_current(html) == "Articles"
    # Nobody gets an Admin link in the header any more.
    assert "https://world.example/akasha/admin" not in html


def test_non_admin_has_no_admin_link():
    client_db = mongomock.MongoClient()
    auth = AuthStore(client_db)
    auth.create_user("plain", generate_password_hash("pw"), role="user")
    app = create_app(DocumentStore(client_db), auth, secret_key="s")
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)
    c = app.test_client()
    assert login(c, "plain", "pw").status_code == 200
    html = c.get("/").get_data(as_text=True)
    assert 'class="service-nav"' in html
    assert ">Admin<" not in html


def test_the_nav_glyphs_match_the_service_marks():
    """The inlined artwork cannot drift from the files it was taken from.

    The nav inlines each ``<service>-glyph.svg`` rather than fetching four
    images across four origins. That is a copy, and a copy nobody checks is a
    copy that goes stale: redraw a mark and the header shows the new one while
    the nav quietly keeps the old.
    """
    nav = (_SRC / "auth" / "templates" / "_service_nav.html").read_text()

    for service in SERVICES:
        glyph = (_SRC / service / "static" / f"{service}-glyph.svg").read_text()
        paths = re.findall(r'\sd="([^"]+)"', glyph)
        assert paths, f"{service}-glyph.svg has no paths to compare"
        for drawing in paths:
            assert drawing in nav, f"{service}: nav is missing {drawing[:40]}..."


def _nav_palette():
    """The host-supplied tokens ``service-nav.css`` paints itself with."""
    nav = (_SRC / "static" / "service-nav.css").read_text()
    spent = set(re.findall(r"var\((--[a-z0-9-]+)", nav))
    # The two it declares itself are geometry, not palette.
    return spent - set(re.findall(r"^\s*(--service-nav-[a-z]+)\s*:", nav, re.MULTILINE))


def _tokens_per_theme(stylesheet: str) -> dict[str, set[str]]:
    """Tokens in force under each theme: ``light`` by default, ``dark`` on top.

    Per theme, not per file. A token declared only under ``[data-theme="dark"]``
    leaves light mode unpainted, and a whole-file check would call that fine --
    which is the exact shape of the bug this guards. Dark inherits whatever it
    does not override, so it is the light set plus its own.
    """
    light, dark = set(), set()
    # Comments first: one of these sheets opens with "light/dark via
    # [data-theme]", and a selector that swallows it reads as a dark block.
    stylesheet = re.sub(r"/\*.*?\*/", "", stylesheet, flags=re.DOTALL)
    for selector, body in re.findall(r"([^{}@]*?)\{([^{}]*)\}", stylesheet, re.DOTALL):
        selector = " ".join(selector.split())
        declared = set(re.findall(r"(--[a-z0-9-]+)\s*:", body))
        if "dark" in selector:
            dark |= declared
        elif ":root" in selector or "data-theme" in selector:
            light |= declared
    return {"light": light, "dark": light | dark}


def test_the_shared_tokens_cover_what_the_nav_paints_with():
    """``service-nav.css`` is shared but not self-contained: it is drawn in the
    stack's palette so it looks like the app it sits in. That palette is now one
    file, and this is the check that it still carries everything the nav spends
    -- in *both* themes, because a token declared only under
    ``[data-theme="dark"]`` leaves light mode unpainted and looks perfect on the
    machine that made it.
    """
    palette = _nav_palette()
    assert len(palette) >= 8, "expected the nav to lean on the shared palette"

    tokens = (_SRC / "static" / "tokens.css").read_text()
    for theme, declared in _tokens_per_theme(tokens).items():
        missing = sorted(palette - declared)
        assert not missing, (
            f"tokens.css does not define {missing} in {theme} mode, which "
            f"service-nav.css paints with: the rail will render unstyled"
        )


def test_every_shell_links_the_shared_tokens():
    """Every page that includes the navigation must link the palette first.

    This is the check the fourth service needed and did not have. When the
    palette lived in six copies, a new one could declare its own names, and the
    result was a rail with no surface behind it and white glyphs on white --
    invisible in light mode, flawless in dark. There is nothing to misspell now,
    but a shell can still simply forget the link, and the symptom is identical.

    Order matters too: the palette has to arrive before the sheet that reads it.
    """
    for shell in SHELLS:
        markup = (_SRC / shell).read_text()
        assert "_service_nav.html" in markup, f"{shell} is not a nav-bearing shell"
        assert "tokens.css" in markup, (
            f"{shell} includes the service nav but never links tokens.css; "
            f"its rail will render unstyled"
        )
        assert markup.index("tokens.css") < markup.index("service-nav.css"), (
            f"{shell} links tokens.css after service-nav.css"
        )


def test_no_stylesheet_reads_a_token_nothing_defines():
    """The other half of moving the palette into one file.

    A ``var(--surfce)`` that resolves to nothing is invisible: the property is
    simply dropped and one rule renders unpainted. That was survivable while
    every sheet declared its own tokens and could only mistype its own; now a
    sheet can also read one that was never moved, or one that has since been
    renamed in ``tokens.css`` on behalf of five other pages.
    """
    shared = set()
    for name in ("tokens.css", "service-nav.css"):
        shared |= set(re.findall(r"(--[a-z0-9-]+)\s*:", (_SRC / "static" / name).read_text()))

    for sheet in sorted(_SRC.rglob("*.css")):
        text = sheet.read_text()
        available = shared | set(re.findall(r"(--[a-z0-9-]+)\s*:", text))
        undefined = sorted(set(re.findall(r"var\((--[a-z0-9-]+)", text)) - available)
        assert not undefined, (
            f"{sheet.relative_to(_SRC)} reads {undefined}, which neither it nor "
            f"tokens.css defines"
        )


def test_nothing_keeps_a_private_copy_of_the_palette():
    """One file, or the six copies grow back one page at a time.

    Templates are checked as well as stylesheets, because two of those six
    copies were not in a stylesheet at all -- they sat in ``<style>`` blocks
    inside the shells, where no linter and no earlier version of this test
    could see them.
    """
    palette = _nav_palette()

    for shell, stylesheet in STYLESHEETS.items():
        text = (_SRC / stylesheet).read_text()
        redeclared = sorted(palette & set(re.findall(r"(--[a-z0-9-]+)\s*:", text)))
        assert not redeclared, (
            f"{shell} ({stylesheet}) redeclares {redeclared}; tokens.css owns those"
        )

    for template in _SRC.rglob("templates/*.html"):
        inline = "\n".join(
            re.findall(r"<style[^>]*>(.*?)</style>", template.read_text(), re.DOTALL)
        )
        redeclared = sorted(palette & set(re.findall(r"(--[a-z0-9-]+)\s*:", inline)))
        assert not redeclared, (
            f"{template.relative_to(_SRC)} declares {redeclared} in an inline "
            f"<style>; put page rules in a stylesheet and leave the palette to "
            f"tokens.css"
        )
