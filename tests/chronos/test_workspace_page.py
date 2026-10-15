"""The workspace: the shell the React bundle (frontend/src/chronos) mounts into.

The bundle itself is tested in frontend/ (vitest); here, that ``?ui=next``
serves the workspace's shell at the visualiser's own address, that the shell
finds the bundle through Vite's manifest and says so when there is none, and
that the classic page is untouched.
"""

import json
from urllib.parse import parse_qs, urlsplit

import pytest

from visualizer.chronos.app import create_app
from visualizer.chronos.workspace_page import ENTRY, manifest_assets

from .conftest import WRITER, WRITER_PASS

ASSETS = {"script": "assets/main-abc123.js", "styles": ["assets/main-def456.css"]}
NEXT = "/?ui=next"


@pytest.fixture
def workspace(story_store, fake_gate, auth_store, calendar_store):
    """A signed-in client for an app whose workspace bundle the test decides."""

    def make(assets, signed_in=True):
        app = create_app(story_store, fake_gate, auth_store, secret_key="test-secret",
                         calendar_store=calendar_store, workspace_assets=lambda: assets)
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)
        client = app.test_client()
        if signed_in:
            login = client.post("/login", json={"username": WRITER, "password": WRITER_PASS})
            assert login.status_code == 200
        return client

    return make


def test_ui_next_serves_the_workspace_shell_with_its_bundle(workspace):
    page = workspace(ASSETS).get(NEXT).get_data(as_text=True)
    assert 'id="chronos-root"' in page
    assert f'data-user="{WRITER}"' in page and 'data-base=""' in page
    assert '<script type="module" src="/static/workspace/assets/main-abc123.js">' in page
    assert 'href="/static/workspace/assets/main-def456.css"' in page
    assert "js/app.js" not in page


@pytest.mark.parametrize("sheet", ["tokens.css", "workspace-shell.css", "service-nav.css"])
def test_the_workspace_shares_the_palette_and_nav(workspace, sheet):
    assert sheet in workspace(ASSETS).get(NEXT).get_data(as_text=True)


def test_the_palette_comes_first_and_the_nav_last(workspace):
    page = workspace(ASSETS).get(NEXT).get_data(as_text=True)
    order = [page.index(s) for s in ("tokens.css", "main-def456.css", "service-nav.css")]
    assert order == sorted(order)


def test_the_header_keeps_the_shared_controls(workspace):
    page = workspace(ASSETS).get(NEXT).get_data(as_text=True)
    assert 'id="theme-toggle"' in page and 'id="font-toggle"' in page and "prefs.js" in page


def test_the_shell_says_where_the_classic_page_is(workspace):
    page = workspace(ASSETS).get(NEXT).get_data(as_text=True)
    assert 'data-classic-url="/"' in page


def test_an_unbuilt_workspace_says_how_to_build_it(workspace):
    response = workspace(None).get(NEXT)
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "The workspace has not been built" in page
    assert "npm --prefix frontend run watch:chronos" in page
    assert '<script type="module"' not in page


@pytest.mark.parametrize("query", ["", "?ui=classic", "?ui=NEXT"])
def test_anything_but_ui_next_is_the_classic_page(workspace, query):
    page = workspace(ASSETS).get("/" + query).get_data(as_text=True)
    assert "js/app.js" in page and 'id="chronos-root"' not in page


def test_the_shell_needs_a_signed_in_writer(workspace):
    anonymous = workspace(ASSETS, signed_in=False).get(NEXT)
    assert anonymous.status_code == 302 and "/login" in anonymous.headers["Location"]


@pytest.mark.parametrize("content", [
    None, "not json", json.dumps({"src/main.tsx": {"file": "x.js"}}),
])
def test_a_missing_or_unusable_manifest_means_no_bundle(tmp_path, content):
    path = tmp_path / "manifest.json"
    if content is not None:
        path.write_text(content)
    assert manifest_assets(path)() is None


def test_the_workspace_is_its_own_entry_in_its_own_manifest(tmp_path):
    path = tmp_path / "manifest.json"
    built = {"file": "assets/main-9.js", "css": ["assets/main-9.css"]}
    path.write_text(json.dumps({ENTRY: built}))
    assert ENTRY == "src/chronos/main.tsx"
    assert manifest_assets(path)() == {"script": "assets/main-9.js",
                                       "styles": ["assets/main-9.css"]}


def test_the_classic_page_offers_the_workspace_at_the_same_place(workspace):
    page = workspace(ASSETS).get("/").get_data(as_text=True)
    assert 'id="workspace-link"' in page
    assert 'href="/?ui=next"' in page and 'data-base="/?ui=next"' in page


@pytest.mark.parametrize("assets, offered", [(ASSETS, True), (None, False)])
def test_the_classic_page_offers_the_workspace_only_once_it_is_built(
    workspace, assets, offered
):
    page = workspace(assets).get("/").get_data(as_text=True)
    assert ('id="workspace-link"' in page) is offered


def test_the_workspace_draws_the_page_s_one_main_landmark(workspace):
    # The bundle renders <main>; the shell around it must not add a second.
    assert "<main" not in workspace(ASSETS).get(NEXT).get_data(as_text=True)


def test_an_unbuilt_workspace_points_at_the_classic_page_at_the_same_place(workspace):
    page = workspace(None).get(NEXT).get_data(as_text=True)
    assert 'id="classic-link"' in page and "location.hash" in page


@pytest.mark.parametrize("script_root", ["", "/timeline"])
def test_a_signed_out_visit_is_sent_to_log_in_and_back_to_the_workspace(
    workspace, script_root
):
    response = workspace(ASSETS, signed_in=False).get(
        NEXT, headers={"Accept": "text/html"}, environ_overrides={"SCRIPT_NAME": script_root}
    )
    location = urlsplit(response.headers["Location"])
    assert location.path == f"{script_root}/login"
    # The gateway's prefix and the switch both ride along.
    assert parse_qs(location.query)["next"] == [f"{script_root}/?ui=next"]


@pytest.mark.parametrize("target, lands", [
    ("/timeline/?ui=next", "/timeline/?ui=next"),
    ("//evil.example/", "/"),
    ("/\\evil.example/", "/"),
    ("https://evil.example/", "/"),
])
def test_logging_in_follows_next_only_to_a_path_on_this_site(workspace, target, lands):
    client = workspace(ASSETS, signed_in=False)
    response = client.post(
        "/login", data={"username": WRITER, "password": WRITER_PASS, "next": target}
    )
    assert response.status_code == 302
    where = urlsplit(response.headers["Location"])
    assert where.netloc in ("", "localhost") and where._replace(scheme="", netloc="").geturl() == lands
