"""The research studio's page: the shell the React bundle mounts into.

The bundle itself is tested in frontend/ (vitest) and in the browser
(docker/smoke_research_studio_ui.py); here, that the page finds the bundle
through Vite's manifest, says so when there is none, and serves no one it
should not.
"""

import json

import pytest
from conftest import ADMIN_PASS, ADMIN_USER, login

from visualizer.akasha.app import create_app
from visualizer.akasha.studio_routes import entry_assets, manifest_assets

ASSETS = {"script": "assets/main-abc123.js", "styles": ["assets/main-def456.css"]}


@pytest.mark.parametrize("manifest,expected", [
    ({"src/main.tsx": {"file": "assets/main-abc.js", "css": ["assets/main.css"],
                       "isEntry": True}},
     {"script": "assets/main-abc.js", "styles": ["assets/main.css"]}),
    ({"src/main.tsx": {"file": "assets/main-abc.js", "imports": ["_shared.js"]},
      "_shared.js": {"file": "assets/shared.js", "css": ["assets/shared.css"]}},
     {"script": "assets/main-abc.js", "styles": ["assets/shared.css"]}),
    ({"src/main.tsx": {"file": "assets/main.js", "css": ["assets/a.css"],
                       "imports": ["_x.js"]},
      "_x.js": {"file": "assets/x.js", "css": ["assets/a.css"]}},
     {"script": "assets/main.js", "styles": ["assets/a.css"]}),
    ({"src/other.tsx": {"file": "assets/other.js"}}, None),
    ({"src/main.tsx": {"css": []}}, None),
    ({"src/main.tsx": "nonsense"}, None),
])
def test_the_entry_and_its_stylesheets_come_from_the_manifest(manifest, expected):
    assert entry_assets(manifest) == expected


@pytest.mark.parametrize("content", [None, "not json", json.dumps({"x": {}})])
def test_a_missing_or_unusable_manifest_means_no_bundle(tmp_path, content):
    path = tmp_path / "manifest.json"
    if content is not None:
        path.write_text(content)
    assert manifest_assets(path)() is None


def test_a_manifest_is_read_afresh_so_a_rebuild_shows_on_reload(tmp_path):
    path = tmp_path / "manifest.json"
    load = manifest_assets(path)
    assert load() is None
    path.write_text(json.dumps({"src/main.tsx": {"file": "assets/main-1.js"}}))
    assert load()["script"] == "assets/main-1.js"


@pytest.fixture
def studio(store, auth_store):
    """A signed-in client for an app whose bundle the test decides."""

    def make(assets):
        app = create_app(store, auth_store, secret_key="test-secret",
                         studio_assets=lambda: assets)
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)
        client = app.test_client()
        assert login(client, ADMIN_USER, ADMIN_PASS).status_code == 200
        return client

    return make


def test_the_page_loads_the_bundle_and_tells_it_the_world(studio):
    page = studio(ASSETS).get("/studio/ember-pact")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'src="/static/studio/assets/main-abc123.js"' in html
    assert 'href="/static/studio/assets/main-def456.css"' in html
    assert 'data-world="ember-pact"' in html and 'data-world-title="Ember Pact"' in html
    assert "Research · Ember Pact" in html
    assert "has not been built" not in html


def test_an_unbuilt_studio_says_how_to_build_it(studio):
    html = studio(None).get("/studio/ember-pact").get_data(as_text=True)
    assert "has not been built" in html and "npm --prefix frontend" in html
    assert "/static/studio/" not in html


def test_the_page_links_back_to_the_world_and_wears_the_service_nav(studio):
    html = studio(ASSETS).get("/studio/ember-pact").get_data(as_text=True)
    assert 'href="/#/ember-pact"' in html
    assert 'class="service-nav"' in html


def test_a_reserved_database_has_no_studio(studio):
    assert studio(ASSETS).get("/studio/_auth").status_code == 400


def test_the_page_needs_a_session(store, auth_store):
    app = create_app(store, auth_store, secret_key="test-secret",
                     studio_assets=lambda: ASSETS)
    app.config.update(TESTING=True)
    response = app.test_client().get("/studio/ember-pact")
    assert response.status_code == 302
    assert response.headers["Location"] == "/login?next=/studio/ember-pact"
