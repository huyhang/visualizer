"""Static files named by their content, kept by the browser for a year.

``static_versions`` is shared code, used by Logos's reader and writing page;
these tests drive it through a minimal app over a static folder of their own.
"""

import pytest
from flask import Flask, render_template_string

from visualizer.shared_assets import register_shared_assets
from visualizer.static_versions import (
    ONE_YEAR,
    file_version,
    import_map,
    install_versioned_static,
)


@pytest.fixture
def site(tmp_path):
    (tmp_path / "js").mkdir()
    (tmp_path / "js" / "app.js").write_text('import { a } from "./a.js";')
    (tmp_path / "js" / "a.js").write_text("export const a = 1;")
    (tmp_path / "page.css").write_text("body { margin: 0 }")
    app = Flask(__name__, static_folder=str(tmp_path), static_url_path="/static")
    register_shared_assets(app)
    install_versioned_static(app)
    return app, tmp_path


def _version_in(url):
    return url.split("?v=", 1)[1]


def test_a_template_names_a_file_with_its_content_s_version(site):
    app, folder = site
    with app.test_request_context():
        url = render_template_string("{{ versioned('static', 'page.css') }}")
    assert url.startswith("/static/page.css?v=")
    assert _version_in(url) == file_version(folder / "page.css")


def test_new_content_is_a_new_address(site):
    app, folder = site
    with app.test_request_context():
        before = render_template_string("{{ versioned('static', 'page.css') }}")
        (folder / "page.css").write_text("body { margin: 1rem }")
        after = render_template_string("{{ versioned('static', 'page.css') }}")
    assert before != after


@pytest.mark.parametrize("query, kept_for_a_year", [
    ("current", True),
    ("", False),
    ("?v=0123456789ab", False),
])
def test_only_the_current_version_is_cacheable_for_a_year(site, query, kept_for_a_year):
    app, folder = site
    if query == "current":
        query = f"?v={file_version(folder / 'js' / 'app.js')}"
    response = app.test_client().get(f"/static/js/app.js{query}")
    assert response.status_code == 200
    cache = response.headers["Cache-Control"]
    if kept_for_a_year:
        assert f"max-age={ONE_YEAR}" in cache and "immutable" in cache
        assert "no-cache" not in cache
    else:
        assert "no-cache" in cache and "immutable" not in cache


def test_the_shared_files_are_versioned_too(site):
    app, _ = site
    with app.test_request_context():
        url = render_template_string("{{ versioned('shared_static', 'tokens.css') }}")
    response = app.test_client().get(url)
    assert response.status_code == 200 and "immutable" in response.headers["Cache-Control"]


@pytest.mark.parametrize("path", ["/static/missing.js?v=abc", "/static/../secret.txt?v=abc"])
def test_a_file_that_is_not_there_is_never_cached(site, path):
    app, _ = site
    response = app.test_client().get(path)
    assert response.status_code == 404
    assert "immutable" not in response.headers.get("Cache-Control", "")


def test_the_import_map_sends_plain_imports_to_versioned_files(site):
    app, folder = site
    with app.test_request_context():
        mapped = import_map("static", ["js/app.js", "js/a.js"])["imports"]
    assert mapped == {
        "/static/js/app.js": f"/static/js/app.js?v={file_version(folder / 'js' / 'app.js')}",
        "/static/js/a.js": f"/static/js/a.js?v={file_version(folder / 'js' / 'a.js')}",
    }
