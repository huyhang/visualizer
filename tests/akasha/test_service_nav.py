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

# Each service's own sheet -- the one loaded alongside the shared nav, and so
# the one that has to supply the palette the nav is drawn in.
STYLESHEETS = {
    "akasha": "akasha/static/editor.css",
    "chronos": "chronos/static/visualizer.css",
    "prithvi": "prithvi/static/maps.css",
    "logos": "logos/static/reader.css",
}


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


def test_every_service_defines_the_nav_tokens():
    """The shared nav spends colour tokens; every host must declare them.

    ``service-nav.css`` is shared but not self-contained: it is drawn in the
    host app's vocabulary so it looks like the app it sits in. A service whose
    stylesheet invents its own names instead gets a rail with no background and
    an active state that does nothing -- and because the glyphs are white
    strokes, they vanish against the white surface that never got painted. It
    still renders perfectly in dark mode, which is exactly how a change like
    that reaches a user: looking finished on the machine that made it.

    Nothing in CSS enforces this. This is the check that says so instead.
    """
    palette = _nav_palette()
    assert len(palette) >= 8, "expected the nav to lean on the host palette"

    for service, stylesheet in STYLESHEETS.items():
        for theme, declared in _tokens_per_theme((_SRC / stylesheet).read_text()).items():
            missing = sorted(palette - declared)
            assert not missing, (
                f"{service} does not define {missing} in {theme} mode, which "
                f"service-nav.css paints with: the rail will render unstyled "
                f"inside {service}'s pages"
            )
