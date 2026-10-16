"""The dev server: the production wiring, over mongomock, kept between runs.

Lives with akasha's suite because akasha owns ``/`` and the shared ``/login``
every other mount is reached through.
"""

import mongomock
import pytest
from werkzeug.test import Client

from visualizer import devserver
from visualizer.stack import build_application


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    # build() fills these in with setdefault; start each test without them so
    # the values it picks are the ones under test, and none leak out.
    for name in ("SECRET_KEY", "MONITORING_DATA_PATH", "MONITORING_ENABLED",
                 "GPU_WORKER_URL", "GPU_WORKER_TOKEN"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def exit_hooks(monkeypatch):
    """What runs at exit, as ``(fn, args)``, captured instead of registered.

    That includes the observability flusher's own hook, so ``stop`` also ends
    the background thread each build starts.
    """
    hooks = []
    monkeypatch.setattr(
        devserver.atexit, "register", lambda fn, *args: hooks.append((fn, args))
    )
    yield hooks
    stop(hooks)


def run(data, *flags):
    """One dev-server lifetime: build over ``data``, hand back a client."""
    args = devserver.parse_args(["--data", str(data), *flags])
    return Client(devserver.build(args))


def stop(exit_hooks):
    """What exiting would do: the hooks, most recently registered first."""
    while exit_hooks:
        fn, args = exit_hooks.pop()
        fn(*args)


def saved_client(exit_hooks):
    """The Mongo client the dev server will snapshot on the way out."""
    (args,) = [args for fn, args in exit_hooks if fn is devserver.save_snapshot]
    return args[0]


def login(client):
    return client.post(
        "/login",
        json={"username": devserver.DEV_USER, "password": devserver.DEV_PASSWORD},
    )


def test_stack_serves_every_service_from_one_origin(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    client = Client(build_application(mongomock.MongoClient()))
    for path in ("/health", "/timeline/health", "/prithvi/health", "/logos/health"):
        assert client.get(path).status_code == 200, path


def research_state(client):
    return client.get("/research/availability").get_json()["state"]


def test_research_is_off_unless_the_environment_names_a_box(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    app = build_application(mongomock.MongoClient())
    assert app.app.test_client().get(
        "/research/availability", headers={"Accept": "application/json"}
    ).status_code == 401, "and, as everywhere, it needs a session"
    client = Client(app)
    client.post("/register", json={"username": "w", "password": "Correct-horse-9",
                                   "email": "w@example.com"})
    client.post("/login", json={"username": "w", "password": "Correct-horse-9"})
    assert research_state(client) == "off"


def test_a_box_named_in_the_environment_is_asked(monkeypatch):
    import socket

    with socket.socket() as probe:          # a port nothing listens on
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("GPU_WORKER_URL", f"http://127.0.0.1:{port}")
    monkeypatch.setenv("GPU_WORKER_TOKEN", "t")
    client = Client(build_application(mongomock.MongoClient()))
    client.post("/register", json={"username": "w", "password": "Correct-horse-9",
                                   "email": "w@example.com"})
    client.post("/login", json={"username": "w", "password": "Correct-horse-9"})
    assert research_state(client) == "unreachable"


def test_a_half_configured_box_stops_the_stack_at_startup(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("GPU_WORKER_URL", "https://gpubox.example.ts.net:8443")
    with pytest.raises(RuntimeError, match="GPU_WORKER_TOKEN"):
        build_application(mongomock.MongoClient())


def test_the_fake_box_flag(tmp_path, exit_hooks):
    assert devserver.parse_args(["--fake-gpubox"]).fake_gpubox == "ready"
    assert devserver.parse_args([]).fake_gpubox is None
    client = run(tmp_path / "db.json", "--fake-gpubox", "busy")
    login(client)
    assert research_state(client) == "busy"


def test_only_a_flag_lifts_the_login_rate_limit(tmp_path, exit_hooks):
    """A run of smoke scripts logs in from one address over and over; it may
    ask for the limit to go, but the dev server keeps production's by default."""
    def seven_logins(client):
        return [login(client).status_code for _ in range(7)]

    assert 429 in seven_logins(run(tmp_path / "limited.json"))
    lifted = run(tmp_path / "lifted.json", "--no-rate-limit")
    assert set(seven_logins(lifted)) == {200}


def test_empty_database_gets_the_docker_admin(tmp_path, exit_hooks):
    client = run(tmp_path / "db.json")
    response = login(client)
    assert response.status_code == 200
    assert response.get_json()["role"] == "admin"
    # Its own cookie name, so it cannot clobber the Docker stack's session.
    assert client.get_cookie(devserver.SESSION_COOKIE) is not None
    # One login still covers every mount.
    assert client.get("/logos/books").status_code == 200


def test_data_survives_a_restart(tmp_path, exit_hooks):
    data = tmp_path / "db.json"
    client = run(data)
    login(client)
    # Making a category is what grants its contents to its maker.
    assert client.post("/databases/ember/collections/characters").status_code == 201
    assert client.post(
        "/databases/ember/collections/characters/documents/lyra",
        json={"title": "Lyra Vane"},
    ).status_code == 201
    # An empty category is still something a writer made.
    assert client.post("/databases/ember/collections/places").status_code == 201
    stop(exit_hooks)
    assert data.exists()

    client = run(data)
    assert login(client).status_code == 200
    doc = client.get("/databases/ember/collections/characters/documents/lyra")
    assert doc.get_json()["document"]["title"] == "Lyra Vane"
    names = [c["name"] for c in client.get(
        "/databases/ember/collections").get_json()["collections"]]
    assert sorted(names) == ["characters", "places"]


def test_restore_survives_mongomock_partial_index_quirk(tmp_path, exit_hooks):
    """Notes share the keys of Logos's bookmark-only unique index.

    mongomock ignores the partial filter when an index is created over
    existing documents, so restoring before the stores build their indexes
    would reject two perfectly valid notes.
    """
    data = tmp_path / "db.json"
    run(data)
    client = saved_client(exit_hooks)
    note = {"username": "mara", "book": "b", "kind": "note", "volume": "v",
            "section": "s", "draft": "d", "block": "p1"}
    client["_logos"]["reader_items"].insert_many([dict(note), dict(note)])
    stop(exit_hooks)

    run(data)
    client = saved_client(exit_hooks)
    assert client["_logos"]["reader_items"].count_documents({"kind": "note"}) == 2


def test_snapshot_keeps_binary_and_dates(tmp_path):
    from datetime import UTC, datetime

    source = mongomock.MongoClient()
    when = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    source["w"]["blobs"].insert_one({"_id": "x", "data": b"\x00\xffpng", "at": when})
    devserver.save_snapshot(source, tmp_path / "db.json")

    target = mongomock.MongoClient()
    devserver.load_snapshot(target, tmp_path / "db.json")
    restored = target["w"]["blobs"].find_one({"_id": "x"})
    assert restored["data"] == b"\x00\xffpng"
    assert restored["at"].replace(tzinfo=UTC) == when


def test_a_snapshot_that_will_not_load_is_never_overwritten(tmp_path, exit_hooks):
    data = tmp_path / "db.json"
    data.write_text("{not json")
    with pytest.raises(ValueError):
        run(data)
    assert devserver.save_snapshot not in [fn for fn, _ in exit_hooks]
    assert data.read_text() == "{not json"
