"""Production entrypoint.

Wires a real MongoDB client into both stores and exposes ``app`` for WSGI
servers (e.g. ``gunicorn wsgi:app`` from this directory).

There is no admin bootstrap: the first account registered via ``/register``
becomes the administrator, and every account after it is a plain user.
"""

from visualizer.auth import AuthStore
from visualizer.chronos.errors import ChronosError
from visualizer.chronos.store import StoryStore
from visualizer.gpubox import worker_from_env
from visualizer.observability import runtime as observability_runtime

from .app import create_app
from .config import (
    get_glb_limits,
    get_image_processor,
    get_mongo_client,
    get_rate_limit_storage_uri,
    get_secret_key,
    get_secure_cookies,
    get_service_links,
    get_versions_keep,
)
from .media_service import build_media_service
from .research import RemoteResearcher
from .research_jobs import ResearchJobStore
from .store import DocumentStore

_client = get_mongo_client()
_auth_store = AuthStore(_client)
_observability = observability_runtime.start(_client, _auth_store)
_story_store = StoryStore(_client)
_worker = worker_from_env()


def _book_world(book: str) -> str | None:
    """Which world a book is set in -- what makes sharing a book share it too.

    The account page can share a book, so it needs the one fact about Chronos
    that decides what else that hands over. Read straight from the store both
    services already share: standalone or combined, the same MongoDB, so the
    account page behaves identically either way.
    """
    try:
        return _story_store.get_book(book).get("world")
    except ChronosError:
        return None


app = create_app(
    DocumentStore(_client, versions_keep=get_versions_keep()),
    _auth_store,
    secret_key=get_secret_key(),
    book_world=_book_world,
    secure_cookies=get_secure_cookies(),
    rate_limit_storage_uri=get_rate_limit_storage_uri(),
    links=get_service_links(),
    observability=_observability,
    media_service=build_media_service(
        _client, get_image_processor(), get_glb_limits()
    ),
    researcher=RemoteResearcher(_worker) if _worker is not None else None,
    research_jobs=ResearchJobStore(_client) if _worker is not None else None,
)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
