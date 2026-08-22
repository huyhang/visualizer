"""Prithvi behind the shared origin: one login, three services, no CORS."""

import json

from werkzeug.test import Client

from visualizer.akasha.app import create_app as create_akasha_app
from visualizer.chronos.app import create_app as create_chronos_app
from visualizer.chronos.entity_gate import FakeEntityGate
from visualizer.chronos.store import CalendarStore, StoryStore
from visualizer.gateway import DEFAULT_PRITHVI_PREFIX, combine
from visualizer.prithvi.app import create_app as create_prithvi_app

from .conftest import SVG, WORLD


def _stack(mongo_client, document_store, prithvi_store, article_gateway, auth_store):
    shared = {
        "secret_key": "test-secret",
        "akasha_url": "/",
        "chronos_url": "/timeline",
        "prithvi_url": DEFAULT_PRITHVI_PREFIX,
    }
    apps = (
        create_akasha_app(document_store, auth_store, **shared),
        create_chronos_app(
            StoryStore(mongo_client),
            FakeEntityGate(),
            auth_store,
            calendar_store=CalendarStore(mongo_client),
            **shared,
        ),
        create_prithvi_app(prithvi_store, article_gateway, auth_store, **shared),
    )
    for app in apps:
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)
    return Client(combine(apps[0], apps[1], prithvi_app=apps[2]))


def _body(response):
    return json.loads(response.get_data(as_text=True))


def test_one_login_at_the_root_reaches_the_prithvi_mount(
    mongo_client, document_store, prithvi_store, article_gateway, auth_store
):
    stack = _stack(mongo_client, document_store, prithvi_store, article_gateway, auth_store)

    assert stack.post(
        "/login", json={"username": "mara", "password": "mara-pw"}
    ).status_code == 200

    created = stack.post(
        f"{DEFAULT_PRITHVI_PREFIX}/worlds/{WORLD}/maps/west",
        data=SVG,
        content_type="image/svg+xml",
    )
    listed = stack.get(f"{DEFAULT_PRITHVI_PREFIX}/worlds/{WORLD}/maps")

    assert created.status_code == 201
    assert [row["id"] for row in _body(listed)["maps"]] == ["west"]


def test_the_map_browser_and_its_assets_are_served_under_the_mount(
    mongo_client, document_store, prithvi_store, article_gateway, auth_store
):
    """Relative asset paths are the point: nothing may hardcode the prefix.

    The page asks for `static/js/app.js` relative to `request.script_root`, so
    the same markup works at `/prithvi` here and at `/` when prithvi runs on
    its own port. A hardcoded `/static/...` would 404 behind the gateway.
    """
    stack = _stack(mongo_client, document_store, prithvi_store, article_gateway, auth_store)
    assert stack.post(
        "/login", json={"username": "mara", "password": "mara-pw"}
    ).status_code == 200

    page = stack.get(f"{DEFAULT_PRITHVI_PREFIX}/")
    assert page.status_code == 200
    markup = page.get_data(as_text=True)
    assert f"{DEFAULT_PRITHVI_PREFIX}/static/js/app.js" in markup
    assert f'window.__BASE__ = "{DEFAULT_PRITHVI_PREFIX}"' in markup

    for asset in ("static/maps.css", "static/js/app.js", "static/js/shared/slug.js"):
        served = stack.get(f"{DEFAULT_PRITHVI_PREFIX}/{asset}")
        assert served.status_code == 200, asset

    catalog = stack.get(f"{DEFAULT_PRITHVI_PREFIX}/ui/worlds")
    assert catalog.status_code == 200
    assert [w["id"] for w in _body(catalog)["worlds"]] == [WORLD]


def test_the_mount_does_not_disturb_the_other_two(
    mongo_client, document_store, prithvi_store, article_gateway, auth_store
):
    stack = _stack(mongo_client, document_store, prithvi_store, article_gateway, auth_store)

    assert _body(stack.get("/health"))["status"] == "ok"
    assert _body(stack.get("/timeline/health"))["service"] == "chronos"
    assert _body(stack.get(f"{DEFAULT_PRITHVI_PREFIX}/health"))["service"] == "prithvi"


def test_prithvi_is_optional_so_the_older_two_service_call_still_works(
    mongo_client, document_store, auth_store
):
    shared = {"secret_key": "test-secret"}
    akasha = create_akasha_app(document_store, auth_store, **shared)
    chronos = create_chronos_app(
        StoryStore(mongo_client),
        FakeEntityGate(),
        auth_store,
        calendar_store=CalendarStore(mongo_client),
        **shared,
    )
    stack = Client(combine(akasha, chronos))

    assert stack.get("/health").status_code == 200
    assert stack.get(f"{DEFAULT_PRITHVI_PREFIX}/health").status_code == 404
