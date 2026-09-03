"""Production entrypoint.

Wires a real MongoDB client into both stores and exposes ``app`` for WSGI
servers (e.g. ``gunicorn wsgi:app`` from this directory).

There is no admin bootstrap: the first account registered via ``/register``
becomes the administrator, and every account after it is a plain user.
"""

from visualizer.auth import AuthStore
from visualizer.chronos.errors import ChronosError
from visualizer.chronos.store import StoryStore
from visualizer.observability import runtime as observability_runtime

from .app import create_app
from .config import (
    get_akasha_url,
    get_chronos_url,
    get_logos_url,
    get_mongo_client,
    get_prithvi_url,
    get_rate_limit_storage_uri,
    get_secret_key,
    get_secure_cookies,
    get_versions_keep,
)
from .store import DocumentStore

_client = get_mongo_client()
_auth_store = AuthStore(_client)
_observability = observability_runtime.start(_client, _auth_store)
_story_store = StoryStore(_client)


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
    akasha_url=get_akasha_url(),
    chronos_url=get_chronos_url(),
    prithvi_url=get_prithvi_url(),
    logos_url=get_logos_url(),
    observability=_observability,
)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
