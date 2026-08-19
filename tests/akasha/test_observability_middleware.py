"""Tests for the request-path behaviour of observability.

Three promises are enforced here, because each one is easy to break invisibly:
the request path does no I/O, the excluded routes really are excluded, and a
failure anywhere in observability cannot fail the request that triggered it.
"""

import contextlib

import mongomock
import pytest
from werkzeug.security import generate_password_hash

from visualizer.akasha.app import create_app
from visualizer.akasha.store import DocumentStore
from visualizer.auth import AuthStore
from visualizer.observability import (
    InProcessRecorder,
    MetricsStore,
    Observability,
    StaticSwitch,
)
from visualizer.observability.middleware import ANONYMOUS
from visualizer.observability.settings import CachedSwitch

_WRITE_OPS = ("insert_one", "insert_many", "update_one", "update_many", "delete_many")
_READ_OPS = ("find", "find_one", "count_documents", "aggregate", "distinct")


@contextlib.contextmanager
def counting_ops(database: str):
    """Count every MongoDB call made against ``database`` inside the block."""
    calls: list[str] = []
    originals = {}

    def wrap(name, original):
        def wrapper(self, *args, **kwargs):
            if self.database.name == database:
                calls.append(f"{name}:{self.name}")
            return original(self, *args, **kwargs)

        return wrapper

    for name in _WRITE_OPS + _READ_OPS:
        originals[name] = getattr(mongomock.collection.Collection, name)
        setattr(mongomock.collection.Collection, name, wrap(name, originals[name]))
    try:
        yield calls
    finally:
        for name, original in originals.items():
            setattr(mongomock.collection.Collection, name, original)


def _app(recorder=None, switch=None, store=None):
    client = mongomock.MongoClient()
    auth = AuthStore(client)
    auth.create_user("mara", generate_password_hash("mara-pass"))
    documents = DocumentStore(client)
    documents.create_collection("world", "people")
    documents.create("world", "people", "mara", {"name": "Mara"}, author="mara")
    auth.grant_owner("mara", "world", "people", "mara", ["read", "write", "delete"])
    observability = Observability(
        recorder=recorder if recorder is not None else InProcessRecorder(),
        switch=switch or StaticSwitch(True),
        store=store,
    )
    app = create_app(documents, auth, secret_key="test", observability=observability)
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)
    return app, client


def _login(app):
    client = app.test_client()
    client.post("/login", json={"username": "mara", "password": "mara-pass"})
    return client


def test_route_is_recorded_as_a_template_not_a_path():
    """Document ids in the URL must not become telemetry labels."""
    recorder = InProcessRecorder()
    app, _ = _app(recorder)
    _login(app).get("/databases/world/collections/people/documents/mara")

    buckets, _, _ = recorder.drain()

    routes = {bucket.route for bucket in buckets}
    assert "/databases/<database>/collections/<collection>/documents/<doc_id>" in routes
    assert not any("mara" in route for route in routes)


def test_health_is_never_recorded():
    """A liveness probe fires on a timer and would swamp every other count."""
    recorder = InProcessRecorder()
    app, _ = _app(recorder)
    for _ in range(5):
        app.test_client().get("/health")

    buckets, _, _ = recorder.drain()

    assert buckets == []


def test_static_assets_are_never_recorded():
    recorder = InProcessRecorder()
    app, _ = _app(recorder)
    app.test_client().get("/static/akasha-icon.svg")

    buckets, _, _ = recorder.drain()

    assert [b for b in buckets if b.route.startswith("/static")] == []


def test_unauthenticated_requests_are_attributed_to_anonymous():
    recorder = InProcessRecorder()
    app, _ = _app(recorder)
    app.test_client().get("/databases/world/collections/people/documents/mara")

    buckets, _, _ = recorder.drain()

    assert {bucket.writer for bucket in buckets} == {ANONYMOUS}


def test_an_unhandled_exception_is_captured_as_the_error_type():
    """This is what fills the `Error` column of the recent-problems table."""
    recorder = InProcessRecorder()
    app, _ = _app(recorder)

    @app.get("/boom")
    def boom():
        raise ZeroDivisionError("nope")

    app.config.update(TESTING=False, PROPAGATE_EXCEPTIONS=False)
    response = app.test_client().get("/boom")

    _, problems, _ = recorder.drain()
    assert response.status_code == 500
    assert [(p.status, p.error) for p in problems] == [(500, "ZeroDivisionError")]


def test_paused_monitoring_records_nothing():
    recorder = InProcessRecorder()
    app, _ = _app(recorder, switch=StaticSwitch(False))
    _login(app).get("/databases/world/collections/people/documents/mara")

    buckets, _, _ = recorder.drain()

    assert buckets == []


def test_the_request_path_performs_no_database_operations():
    """Recording must never add a round trip to a request.

    The audit that preceded this feature found an implementation doing five per
    request against the very database it was meant to be protecting.
    """
    store = MetricsStore(mongomock.MongoClient())
    app, _ = _app(switch=CachedSwitch(store), store=store)
    client = _login(app)  # also warms the switch cache

    with counting_ops("_ops") as calls:
        for _ in range(20):
            client.get("/databases/world/collections/people/documents/mara")

    assert calls == []


def test_the_switch_is_read_once_per_ttl_not_once_per_request():
    store = MetricsStore(mongomock.MongoClient())
    now = [0.0]
    switch = CachedSwitch(store, ttl_seconds=30.0, clock=lambda: now[0])
    app, _ = _app(switch=switch, store=store)
    client = app.test_client()

    # ``find_one`` is the call the switch makes; the in-memory client fans it
    # out to ``find`` internally, which is not a second round trip.
    def reads(calls):
        return [call for call in calls if call.startswith("find_one:")]

    with counting_ops("_ops") as calls:
        for _ in range(20):
            client.get("/databases/world/collections/people/documents/mara")
        assert reads(calls) == ["find_one:settings"], calls
        now[0] = 31.0
        client.get("/databases/world/collections/people/documents/mara")
        assert reads(calls) == ["find_one:settings"] * 2, calls


def test_paused_requests_also_touch_no_database():
    store = MetricsStore(mongomock.MongoClient())
    switch = CachedSwitch(store)
    switch.set(False)
    app, _ = _app(switch=switch, store=store)
    client = _login(app)

    with counting_ops("_ops") as calls:
        for _ in range(20):
            client.get("/databases/world/collections/people/documents/mara")

    assert calls == []


def test_a_failing_switch_cannot_fail_the_request():
    """A MongoDB blip must degrade observability, never the application."""

    class Broken:
        def get_monitoring_enabled(self):
            raise RuntimeError("mongo unreachable")

        def set_monitoring_enabled(self, enabled):
            raise RuntimeError("mongo unreachable")

    app, _ = _app(switch=CachedSwitch(Broken()))
    app.config.update(TESTING=False, PROPAGATE_EXCEPTIONS=False)

    response = _login(app).get("/databases/world/collections/people/documents/mara")

    assert response.status_code == 200


def test_a_failing_recorder_cannot_fail_the_request():
    class Exploding:
        def record(self, sample):
            raise RuntimeError("recorder is broken")

    app, _ = _app(recorder=Exploding())
    app.config.update(TESTING=False, PROPAGATE_EXCEPTIONS=False)

    response = _login(app).get("/databases/world/collections/people/documents/mara")

    assert response.status_code == 200


@pytest.mark.parametrize("path", ["/health", "/databases/world/collections/people"])
def test_observability_never_changes_a_response(path):
    plain, _ = _app(recorder=InProcessRecorder())
    with_none = create_app(
        DocumentStore(mongomock.MongoClient()),
        AuthStore(mongomock.MongoClient()),
        secret_key="test",
    )
    with_none.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)

    observed = plain.test_client().get(path)
    baseline = with_none.test_client().get(path)

    assert observed.status_code == baseline.status_code
