"""Integration tests for the admin observability page.

These run against the real ``MetricsStore`` rather than a stand-in, so the
route, the shaping and the storage layer are exercised as they actually ship --
a test double in place of the production collector is how a broken hot path
stays green.
"""

import re

import mongomock
import pytest
from werkzeug.security import generate_password_hash

from visualizer.akasha.app import create_app
from visualizer.akasha.store import DocumentStore
from visualizer.auth import AuthStore
from visualizer.observability import (
    Flusher,
    InProcessRecorder,
    MetricsStore,
    Observability,
    UsageScan,
)
from visualizer.observability.capacity import CapacitySample, StaticCapacitySource
from visualizer.observability.settings import CachedSwitch
from visualizer.observability.usage import MongoDocumentSource

TB = 1_000_000_000_000


@pytest.fixture
def stack():
    client = mongomock.MongoClient()
    auth = AuthStore(client)
    auth.create_user("root", generate_password_hash("root-pass"), role="admin")
    auth.create_user("mara", generate_password_hash("mara-pass"))
    documents = DocumentStore(client)
    documents.create_collection("world", "people")
    documents.create("world", "people", "mara", {"name": "Mara"}, author="mara")
    documents.update("world", "people", "mara", {"name": "Mara II"}, author="root")
    auth.grant_owner("mara", "world", "people", "mara", ["read", "write", "delete"])

    store = MetricsStore(client)
    recorder = InProcessRecorder()
    switch = CachedSwitch(store)
    app = create_app(
        documents,
        auth,
        secret_key="test",
        observability=Observability(recorder, switch, store),
    )
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)
    flusher = Flusher(
        recorder,
        store,
        switch,
        usage_scan=UsageScan(MongoDocumentSource(client), auth.all_grants, store),
        capacity_source=StaticCapacitySource(
            CapacitySample(
                volume_total=4 * TB,
                volume_free=int(1.2 * TB),
                memory_total=8_000_000_000,
                memory_available=4_000_000_000,
                mongo_bytes=2_100_000_000,
            )
        ),
    )
    return app, flusher, store


def _as(app, username, password):
    client = app.test_client()
    client.post("/login", json={"username": username, "password": password})
    return client


# -- access control ----------------------------------------------------------


def test_anonymous_visitors_are_sent_to_login(stack):
    app, _, _ = stack
    assert app.test_client().get("/admin/observability").status_code == 302


def test_a_non_admin_is_forbidden(stack):
    app, _, _ = stack
    assert _as(app, "mara", "mara-pass").get("/admin/observability").status_code == 403


def test_a_non_admin_cannot_flip_the_switch(stack):
    app, _, _ = stack
    response = _as(app, "mara", "mara-pass").post(
        "/admin/observability/switch", data={"enabled": "false"}
    )
    assert response.status_code == 403


def test_the_page_is_absent_when_no_store_was_injected():
    """Chronos records but never renders; it must not grow an admin route."""
    client = mongomock.MongoClient()
    auth = AuthStore(client)
    auth.create_user("root", generate_password_hash("root-pass"), role="admin")
    app = create_app(
        DocumentStore(client),
        auth,
        secret_key="test",
        observability=Observability(InProcessRecorder(), CachedSwitch(MetricsStore(client))),
    )
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)

    assert _as(app, "root", "root-pass").get("/admin/observability").status_code == 404


# -- rendering ---------------------------------------------------------------


def test_the_page_renders_before_any_data_exists(stack):
    app, _, _ = stack
    response = _as(app, "root", "root-pass").get("/admin/observability")

    assert response.status_code == 200
    assert b'class="service-nav"' in response.data
    assert b'aria-current="page"' not in response.data   # not a service surface
    assert b"not enough history" in response.data


def test_the_page_renders_the_full_picture_after_a_flush_and_scan(stack):
    app, flusher, _ = stack
    mara = _as(app, "mara", "mara-pass")
    for _ in range(3):
        mara.get("/databases/world/collections/people/documents/mara")
    mara.get("/databases/world/collections/people/documents/absent")
    flusher.flush_once()
    flusher.scan_once()

    body = _as(app, "root", "root-pass").get("/admin/observability").get_data(as_text=True)

    assert "2.8 TB of 4.0 TB" in body  # the volume meter, from the capacity sample
    assert "2.1 GB" in body  # MongoDB's own footprint
    assert "mara" in body  # the writers table
    assert "<svg" in body  # the latency chart rendered
    assert "Show as table" in body  # every chart has a table twin


def test_the_page_never_shows_a_raw_document_path(stack):
    """Route templates only -- telemetry must not become a second copy of the data."""
    app, flusher, _ = stack
    _as(app, "mara", "mara-pass").get("/databases/world/collections/people/documents/mara")
    flusher.flush_once()

    body = _as(app, "root", "root-pass").get("/admin/observability").get_data(as_text=True)

    assert "/documents/&lt;doc_id&gt;" in body
    assert "/documents/mara" not in body


def test_the_page_does_not_poll_itself(stack):
    """An auto-refreshing metrics page records its own refreshes forever."""
    app, _, _ = stack
    body = _as(app, "root", "root-pass").get("/admin/observability").get_data(as_text=True)

    assert "setInterval" not in body
    assert not re.search(r'http-equiv=["\']refresh', body, re.IGNORECASE)


def test_svg_coordinates_stay_within_the_declared_viewbox(stack):
    """The palette validator checks colour, not layout; this checks layout."""
    app, flusher, _ = stack
    mara = _as(app, "mara", "mara-pass")
    for _ in range(4):
        mara.get("/databases/world/collections/people/documents/mara")
    flusher.flush_once()

    body = _as(app, "root", "root-pass").get("/admin/observability").get_data(as_text=True)

    charts = 0
    for match in re.finditer(
        r'<svg viewBox="0 0 ([\d.]+) ([\d.]+)"(.*?)</svg>', body, re.DOTALL
    ):
        charts += 1
        width, height, content = float(match[1]), float(match[2]), match[3]
        for attribute in ("x", "cx", "x1", "x2"):
            for value in re.findall(rf'\b{attribute}="(-?[\d.]+)"', content):
                assert -1 <= float(value) <= width + 1, f"{attribute}={value} exceeds {width}"
        for attribute in ("y", "cy", "y1", "y2"):
            for value in re.findall(rf'\b{attribute}="(-?[\d.]+)"', content):
                assert -1 <= float(value) <= height + 1, f"{attribute}={value} exceeds {height}"
    assert charts, "expected at least one chart to have rendered"


@pytest.mark.parametrize("window", ["24h", "7d", "30d"])
def test_each_time_window_renders(stack, window):
    app, _, _ = stack
    response = _as(app, "root", "root-pass").get(f"/admin/observability?window={window}")
    assert response.status_code == 200


def test_an_unknown_window_falls_back_rather_than_failing(stack):
    app, _, _ = stack
    response = _as(app, "root", "root-pass").get("/admin/observability?window=../etc")
    assert response.status_code == 200


# -- the switch --------------------------------------------------------------


def test_an_admin_can_pause_and_resume(stack):
    app, _, store = stack
    admin = _as(app, "root", "root-pass")

    assert admin.post("/admin/observability/switch", data={"enabled": "false"}).status_code == 302
    assert store.get_monitoring_enabled() is False

    admin.post("/admin/observability/switch", data={"enabled": "true"})
    assert store.get_monitoring_enabled() is True


def test_pausing_takes_effect_without_waiting_for_the_cache_to_expire(stack):
    """``set`` adopts the new value immediately rather than after the TTL."""
    app, flusher, store = stack
    admin = _as(app, "root", "root-pass")
    admin.post("/admin/observability/switch", data={"enabled": "false"})
    flusher.flush_once()  # drain anything recorded before the pause
    before = sum(row["count"] for row in store.request_hours())

    for _ in range(5):
        _as(app, "mara", "mara-pass").get(
            "/databases/world/collections/people/documents/mara"
        )
    flusher.flush_once()

    assert sum(row["count"] for row in store.request_hours()) == before


def test_a_paused_page_says_so(stack):
    app, _, _ = stack
    admin = _as(app, "root", "root-pass")
    admin.post("/admin/observability/switch", data={"enabled": "false"})

    assert b"Monitoring is paused" in admin.get("/admin/observability").data


def test_a_malformed_switch_value_is_rejected(stack):
    app, _, store = stack
    response = _as(app, "root", "root-pass").post(
        "/admin/observability/switch", data={"enabled": "maybe"}
    )

    assert response.status_code == 403
    assert store.get_monitoring_enabled() is None


def test_the_switch_form_is_csrf_protected(stack):
    """The admin console's other state changes are; this one must be too."""
    app, _, store = stack
    app.config.update(WTF_CSRF_ENABLED=True)

    response = _as(app, "root", "root-pass").post(
        "/admin/observability/switch", data={"enabled": "false"}
    )

    assert response.status_code == 400
    assert store.get_monitoring_enabled() is None


def test_the_admin_console_links_to_the_page(stack):
    app, _, _ = stack
    body = _as(app, "root", "root-pass").get("/admin").get_data(as_text=True)
    assert "/admin/observability" in body
