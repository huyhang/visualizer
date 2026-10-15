"""The writing page: the shell the React bundle (frontend/src/logos) mounts into.

The bundle itself is tested in frontend/ (vitest) and in a real browser
(docker/smoke_logos_writer.py); here, that ``?mode=write`` serves the writer's
shell at the address the writer always had, that the shell finds the bundle
through Vite's manifest and says so when there is none, and that the reader is
untouched.
"""

import json

import pytest

from visualizer import vite_assets
from visualizer.logos.app import create_app
from visualizer.logos.writer_page import ENTRY, manifest_assets

from .conftest import BOOK, login

ASSETS = {"script": "assets/main-abc123.js", "styles": ["assets/main-def456.css"]}
WRITE = f"/?book={BOOK}&volume=one&section=gate&mode=write"


@pytest.fixture
def writer(logos_store, chronos_gateway, article_gateway, auth_store):
    """A signed-in client for an app whose writer bundle the test decides."""

    def make(assets, user="mara"):
        app = create_app(logos_store, chronos_gateway, article_gateway, auth_store,
                         secret_key="test-secret", akasha_url="/akasha/",
                         writer_assets=lambda: assets)
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)
        client = app.test_client()
        assert login(client, user).status_code == 200
        return client

    return make


def test_mode_write_serves_the_writers_shell_with_its_bundle(writer):
    page = writer(ASSETS).get(WRITE).get_data(as_text=True)
    assert 'id="writer-root"' in page
    assert 'data-user="mara"' in page and 'data-akasha-url="/akasha/"' in page
    assert '<script type="module" src="/static/writer/assets/main-abc123.js">' in page
    assert 'href="/static/writer/assets/main-def456.css"' in page
    assert "app.js" not in page


@pytest.mark.parametrize("sheet", ["tokens.css", "reader.css", "service-nav.css"])
def test_the_writer_shares_the_readers_palette_typography_and_nav(writer, sheet):
    assert sheet in writer(ASSETS).get(WRITE).get_data(as_text=True)


def test_the_header_is_the_readers_own(writer):
    page = writer(ASSETS).get(WRITE).get_data(as_text=True)
    assert 'class="app-header"' in page and 'id="theme-toggle"' in page


def test_an_unbuilt_writer_says_how_to_build_it(writer):
    response = writer(None).get(WRITE)
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "The writing page has not been built" in page
    assert "npm --prefix frontend run build" in page
    assert '<script type="module"' not in page


@pytest.mark.parametrize("query", ["", f"?book={BOOK}", f"?book={BOOK}&mode=read"])
def test_anything_but_mode_write_is_the_reader(writer, query):
    page = writer(ASSETS).get("/" + query).get_data(as_text=True)
    assert "app.js" in page and 'id="writer-root"' not in page


def test_the_shell_needs_a_signed_in_writer(writer, app):
    anonymous = app.test_client().get(WRITE)
    assert anonymous.status_code == 302 and "/login" in anonymous.headers["Location"]


def test_the_shell_reveals_nothing_about_the_book(writer):
    """A read-only collaborator gets the same shell; the bundle asks the API,
    which authorises, and sends them to the reader."""
    page = writer(ASSETS, user="devi").get(WRITE).get_data(as_text=True)
    assert 'data-user="devi"' in page and BOOK not in page.split('id="writer-root"')[1]


@pytest.mark.parametrize("content", [
    None, "not json", json.dumps({"src/main.tsx": {"file": "x.js"}}),
])
def test_a_missing_or_unusable_manifest_means_no_bundle(tmp_path, content):
    path = tmp_path / "manifest.json"
    if content is not None:
        path.write_text(content)
    assert manifest_assets(path)() is None


def test_the_writer_is_its_own_entry_in_its_own_manifest(tmp_path):
    path = tmp_path / "manifest.json"
    built = {"file": "assets/main-9.js", "css": ["assets/main-9.css"]}
    path.write_text(json.dumps({ENTRY: built}))
    assert ENTRY == "src/logos/main.tsx"
    assert manifest_assets(path)() == {"script": "assets/main-9.js",
                                       "styles": ["assets/main-9.css"]}


@pytest.mark.parametrize("manifest,expected", [
    ({"e.tsx": {"file": "a.js", "css": ["a.css"]}},
     {"script": "a.js", "styles": ["a.css"]}),
    ({"e.tsx": {"file": "a.js", "imports": ["_s.js"]}, "_s.js": {"css": ["s.css"]}},
     {"script": "a.js", "styles": ["s.css"]}),
    ({"other.tsx": {"file": "o.js"}}, None),
    ({"e.tsx": "nonsense"}, None),
])
def test_the_shared_manifest_lookup(manifest, expected):
    assert vite_assets.entry_assets(manifest, "e.tsx") == expected
