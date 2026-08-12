"""The single-origin gateway: both apps on one WSGI callable (DispatcherMiddleware).

akasha at ``/``, chronos at ``/timeline``. The load-bearing property is that one
login (via akasha at the root) authenticates chronos under the prefix, because
they share the cookie and the auth store.
"""

import json

import pytest
from werkzeug.test import Client

from visualizer.akasha.app import create_app as create_akasha_app
from visualizer.chronos.app import create_app as create_chronos_app
from visualizer.gateway import combine


@pytest.fixture
def gateway(doc_store, story_store, fake_gate, auth_store, calendar_store):
    kw = {"secret_key": "test-secret", "akasha_url": "/", "chronos_url": "/timeline"}
    akasha_app = create_akasha_app(doc_store, auth_store, **kw)
    chronos_app = create_chronos_app(
        story_store, fake_gate, auth_store, calendar_store=calendar_store, **kw
    )
    for app in (akasha_app, chronos_app):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)
    return combine(akasha_app, chronos_app)


@pytest.fixture
def gc(gateway):
    return Client(gateway)


def _json(resp):
    return json.loads(resp.get_data(as_text=True))


def _login(gc):
    return gc.post("/login", json={"username": "mara", "password": "mara-pass"})


def test_akasha_served_at_root(gc):
    resp = gc.get("/health")  # akasha liveness, no auth
    assert resp.status_code == 200 and _json(resp)["status"] == "ok"


def test_chronos_served_under_prefix(gc):
    resp = gc.get("/timeline/health")
    assert resp.status_code == 200 and _json(resp)["service"] == "chronos"


def test_root_index_requires_auth(gc):
    assert gc.get("/").status_code in (302, 401)


def test_one_login_at_root_covers_chronos_prefix(gc):
    # The crux: log in once (akasha, at /), then reach chronos under /timeline.
    assert _login(gc).status_code == 200
    resp = gc.get("/timeline/books")
    assert resp.status_code == 200 and "books" in _json(resp)


def test_spa_injects_mount_prefix_as_base(gc):
    _login(gc)
    html = gc.get("/timeline/").get_data(as_text=True)
    # The SPA learns its mount from request.script_root so its fetches are prefixed.
    assert 'window.__BASE__ = "/timeline"' in html


def test_chronos_static_served_under_prefix(gc):
    resp = gc.get("/timeline/static/visualizer.css")
    assert resp.status_code == 200


def test_shared_modules_are_served_by_both_apps_at_their_own_mounts(gc):
    """Why the shared tree is imported with a *relative* specifier.

    It lives once (``visualizer/static/js``) and each app serves it beneath its
    own static path, so `./shared/slug.js` resolves to a different URL per app
    and per mount -- and to a real file at every one of them. An absolute
    ``/shared/...`` would work here only because akasha happens to own ``/``,
    and would 404 the moment chronos ran standalone on its own port.
    """
    for url in ("/static/js/shared/slug.js", "/timeline/static/js/shared/slug.js"):
        resp = gc.get(url)
        assert resp.status_code == 200, url
        assert "export function slugify" in resp.get_data(as_text=True), url
