"""Run the whole stack locally, without Docker or a MongoDB server.

    python -m visualizer.devserver              # http://127.0.0.1:5050
    python -m visualizer.devserver --seed       # ...with the demo story loaded
    python -m visualizer.devserver --fresh      # start from an empty database
    python -m visualizer.devserver --fake-gpubox busy   # research and LLM review, faked

The same four apps, wired by the same ``visualizer.stack.build_application``
that gunicorn serves in production, over an in-memory ``mongomock`` client
instead of a real one. Werkzeug's reloader restarts it when a Python file
changes, templates and static files are read fresh on every request, and an
unhandled exception renders the interactive debugger rather than a bare 500.

What the in-memory database holds is written to ``instance/devserver.json``
whenever the server stops -- including the stop a reload does -- and read back
when it starts, so editing code does not cost you your test data. ``--fresh``
discards it. ``--mongo-uri`` points at a real MongoDB instead, and then nothing
is written to the file at all.

An empty database gets the same ``mara`` account the Docker deployment uses, so
the seed and smoke scripts under ``docker/`` work here unchanged; ``--seed``
runs the demo seeds against this server once it is listening.

``--fake-gpubox [MODE]`` stands a fake GPU box behind Akasha's research and
Logos's LLM review (``visualizer.gpubox.fake``): jobs walk the real stages a
second or so apiece, and MODE puts the box in any state a writer can meet --
``ready`` by default, or ``cold``, ``busy``, ``degraded``, ``queue_full``,
``unreachable`` and the rest. Without it the box comes from ``GPU_WORKER_URL``
as in production, which on a laptop usually means both are off.

The dev server's session cookie has its own name, so it can run beside the
Docker stack on :5002 without the two logging each other out. It is mongomock
underneath, not MongoDB: anything the test suite does not exercise may behave
differently, and PDF export needs WeasyPrint's native libraries (Pango) on this
machine -- EPUB does not.
"""

import argparse
import atexit
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from bson import json_util
from pymongo import MongoClient
from werkzeug.serving import is_running_from_reloader, run_simple

from visualizer.auth import AuthStore
from visualizer.gpubox.fake import MODES as FAKE_GPUBOX_MODES
from visualizer.gpubox.fake import FakeWorker
from visualizer.stack import build_application

REPO = Path(__file__).resolve().parents[2]
DEFAULT_DATA = REPO / "instance" / "devserver.json"
DEFAULT_PORT = 5050
# Signs session cookies. Fixed rather than random so a login survives a reload;
# never used outside this module, which production does not import.
DEV_SECRET_KEY = "visualizer-devserver-not-a-secret"
SESSION_COOKIE = "visualizer_dev_session"

# The account the Docker deployment and every docker/seed_*.py script use.
DEV_USER = "mara"
DEV_PASSWORD = "ember-pact-demo"
DEV_EMAIL = "mara@example.com"

# Long enough to watch a fake job's progress in the UI, short enough to wait for.
FAKE_STAGE_SECONDS = 1.5

# seed_demo.py first: it registers mara and writes the book, world and canon
# the other three build on.
SEEDS = (
    "seed_demo.py",
    "seed_story_map.py",
    "seed_prithvi_demo.py",
    "seed_logos_demo.py",
)


def _say(message: str) -> None:
    # Flushed: the watcher's stdout is block-buffered whenever it is not a
    # terminal, which would hold these back until the server stopped.
    print(f"devserver: {message}", flush=True)


# -- persisting the in-memory database --------------------------------------


def save_snapshot(client, path: Path) -> None:
    """Write every database, collection and document to ``path``.

    Indexes are not kept: every one is declared in a store's constructor, so
    building the stack recreates them all before anything is restored.
    """
    data = {
        db_name: {
            name: list(client[db_name][name].find())
            for name in client[db_name].list_collection_names()
        }
        for db_name in client.list_database_names()
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    # Written aside and renamed, so a stop mid-write cannot leave half a file.
    partial = path.with_name(path.name + ".partial")
    partial.write_text(json_util.dumps(data))
    os.replace(partial, path)


def load_snapshot(client, path: Path) -> None:
    """Put back what ``save_snapshot`` wrote, into an already-built stack.

    Restored after the stores have made their indexes, never before: mongomock
    ignores ``partialFilterExpression`` when it checks an index being created
    over existing documents, so Logos's bookmark-only unique index would reject
    perfectly valid notes. Checks made as documents arrive honour it.
    """
    data = json_util.loads(path.read_text())
    for db_name, collections in data.items():
        db = client[db_name]
        existing = set(db.list_collection_names())
        for name, documents in collections.items():
            # Created explicitly: an empty collection is still a namespace a
            # writer made (an Akasha category with nothing in it yet).
            if name not in existing:
                db.create_collection(name)
            collection = db[name]
            if not documents:
                continue
            if collection.estimated_document_count() == 0:
                collection.insert_many(documents)
            else:
                # Something a constructor wrote on the way up; the saved copy
                # is the one the writer last saw.
                for document in documents:
                    collection.replace_one(
                        {"_id": document["_id"]}, document, upsert=True
                    )


# -- building the app --------------------------------------------------------


def _in_memory_client():
    try:
        import mongomock
        import mongomock.gridfs
    except ImportError:
        sys.exit(
            "The dev server needs mongomock: pip install -e '.[dev]' "
            "(or pass --mongo-uri to use a real MongoDB)."
        )
    # Akasha keeps uploaded images in GridFS, which mongomock only fakes once
    # asked to.
    mongomock.gridfs.enable_gridfs_integration()
    return mongomock.MongoClient()


def _register_dev_user(application) -> None:
    """Register ``mara`` through the real endpoint, into an empty database.

    The first account registered becomes the administrator -- the same path a
    fresh Docker deployment takes, not a shortcut around it.
    """
    response = application.app.test_client().post(
        "/register",
        json={"username": DEV_USER, "password": DEV_PASSWORD, "email": DEV_EMAIL},
    )
    if response.status_code != 201:
        _say(f"registering {DEV_USER} returned "
             f"{response.status_code}: {response.get_data(as_text=True)}")


def build(args):
    # build_application reads its settings from the environment; supply the
    # ones that are required, or wrong for a laptop, unless already set.
    os.environ.setdefault("SECRET_KEY", DEV_SECRET_KEY)
    # The capacity sampler measures this path's disk. The production default,
    # /data, is the NAS volume and does not exist here.
    os.environ.setdefault("MONITORING_DATA_PATH", str(REPO))
    # Paused at boot, though the admin page can resume it: mongomock has no
    # dbStats, so every capacity sample would log a traceback.
    os.environ.setdefault("MONITORING_ENABLED", "false")

    in_memory = not args.mongo_uri
    client = _in_memory_client() if in_memory else MongoClient(args.mongo_uri)
    gpu_worker = None
    if args.fake_gpubox:
        gpu_worker = FakeWorker(args.fake_gpubox, stage_seconds=FAKE_STAGE_SECONDS)
    application = build_application(client, gpu_worker=gpu_worker)
    if in_memory:
        if args.data.exists():
            load_snapshot(client, args.data)
        # Only once the restore has worked: a file that failed to load must
        # not be overwritten on the way out by the empty database.
        atexit.register(save_snapshot, client, args.data)

    for app in (application.app, *application.mounts.values()):
        app.config["SESSION_COOKIE_NAME"] = SESSION_COOKIE
        # Exceptions reach the debugger, and templates reload when edited.
        app.debug = True
    if AuthStore(client).count_users() == 0:
        _register_dev_user(application)
    return application


def _not_served(environ, start_response):
    """Stands in for the app in the reloader's watcher process, which only
    restarts the worker and never answers a request itself."""
    start_response("503 Service Unavailable", [("Content-Type", "text/plain")])
    return [b"starting\n"]


# -- seeding -----------------------------------------------------------------


def _wait_for_port(host: str, port: int, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def _seed(base: str, host: str, port: int) -> None:
    """Run the demo seeds against this server, over HTTP like any client."""
    if not _wait_for_port(host, port):
        _say("server never came up; not seeding")
        return
    env = {
        **os.environ,
        "AKASHA_BASE": base,
        "CHRONOS_BASE": f"{base}/timeline",
        "PRITHVI_BASE": f"{base}/prithvi",
        "LOGOS_BASE": f"{base}/logos",
    }
    for script in SEEDS:
        _say(f"running docker/{script}")
        result = subprocess.run(
            [sys.executable, str(REPO / "docker" / script)],
            env=env, cwd=REPO, check=False,
        )
        if result.returncode != 0:
            _say(f"docker/{script} failed ({result.returncode}); "
                 "stopping the seed here")
            return
    _say(f"seeded -- log in at {base}/login as {DEV_USER} / {DEV_PASSWORD}")


# -- entry point -------------------------------------------------------------


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m visualizer.devserver",
        description="Run the visualizer stack locally, without Docker or MongoDB.",
    )
    parser.add_argument("--host", default="127.0.0.1",
                        help="interface to bind (default: %(default)s)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help="port to serve on (default: %(default)s)")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA,
                        help="where the in-memory database is kept between "
                             "runs (default: instance/devserver.json)")
    parser.add_argument("--fresh", action="store_true",
                        help="discard the kept database and start empty")
    parser.add_argument("--seed", action="store_true",
                        help="load the demo story once the server is up")
    parser.add_argument("--mongo-uri",
                        help="use this MongoDB instead of the in-memory one")
    parser.add_argument("--fake-gpubox", nargs="?", const="ready", default=None,
                        choices=FAKE_GPUBOX_MODES, metavar="MODE",
                        help="put a fake GPU box behind research and LLM "
                             "review, in MODE "
                             f"({', '.join(FAKE_GPUBOX_MODES)}; default ready)")
    parser.add_argument("--no-reload", dest="reload", action="store_false",
                        help="do not restart when a Python file changes")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    # With the reloader on, this module runs twice: once as the watcher the
    # user started, which only ever restarts the other, and once per restart as
    # the worker that serves. --fresh and --seed are the user's one-off
    # requests, so only the watcher acts on them; only the worker builds.
    watcher = not is_running_from_reloader()
    serves = is_running_from_reloader() or not args.reload
    browse_host = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    base = f"http://{browse_host}:{args.port}"

    if watcher:
        if args.fresh and not args.mongo_uri and args.data.exists():
            args.data.unlink()
        where = args.mongo_uri or f"in memory, kept in {args.data}"
        _say(f"database {where}")
        _say(f"akasha {base}/  chronos {base}/timeline  "
             f"prithvi {base}/prithvi  logos {base}/logos")
        _say(f"log in as {DEV_USER} / {DEV_PASSWORD}")
        if args.fake_gpubox:
            _say(f"GPU box: fake, {args.fake_gpubox}")
        elif os.environ.get("GPU_WORKER_URL", "").strip():
            _say(f"GPU box: {os.environ['GPU_WORKER_URL'].strip()}")
        if args.seed:
            threading.Thread(
                target=_seed, args=(base, browse_host, args.port), daemon=True
            ).start()

    application = build(args) if serves else _not_served
    run_simple(
        args.host,
        args.port,
        application,
        use_reloader=args.reload,
        use_debugger=True,
        threaded=True,
    )


if __name__ == "__main__":
    main()
