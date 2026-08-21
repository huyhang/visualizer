"""Fixtures for the Prithvi suite -- in-memory Mongo, a fixed clock, no server.

Two writers exist throughout, because most of what is interesting about this
service is who may see what:

- **mara** holds read/write/delete on the ``ember-pact`` world.
- **devi** holds read on the world, and an explicitly empty grant on the single
  article ``locations/oathstone`` -- the narrower grant wins, so she is a
  perfectly ordinary reader who happens to be shut out of one article.
"""

from datetime import UTC, datetime

import mongomock
import pytest
from werkzeug.security import generate_password_hash

from visualizer.akasha.store import DocumentStore
from visualizer.auth import AuthStore
from visualizer.prithvi.app import create_app
from visualizer.prithvi.articles import InProcessArticleGateway
from visualizer.prithvi.errors import ArticleNotFound, WorldNotFound
from visualizer.prithvi.models import ArticleRef
from visualizer.prithvi.store import PrithviStore

FIXED_TIME = datetime(2026, 1, 1, tzinfo=UTC)

WORLD = "ember-pact"
MAP = "western-realms"
COLLECTION = "locations"
OPEN_ARTICLE = "highkeep"
CLOSED_ARTICLE = "oathstone"

MAP_URL = f"/worlds/{WORLD}/maps/{MAP}"
PIN_URL = f"{MAP_URL}/pins/{COLLECTION}/{OPEN_ARTICLE}"
CLOSED_PIN_URL = f"{MAP_URL}/pins/{COLLECTION}/{CLOSED_ARTICLE}"

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50"/>'


class FakeArticleGateway:
    """A dictionary where Akasha would be, for tests about everything else."""

    def __init__(self, worlds=()):
        self._worlds = set(worlds)
        self._articles: dict[ArticleRef, dict] = {}

    def add(self, ref: ArticleRef, document: dict | None = None) -> None:
        self._worlds.add(ref.world)
        self._articles[ref] = document or {"title": ref.article_id.title()}

    def remove(self, ref: ArticleRef) -> None:
        self._articles.pop(ref, None)

    def require_world(self, world: str) -> None:
        if world not in self._worlds:
            raise WorldNotFound(f"There is no Akasha world called '{world}'.")

    def fetch(self, ref: ArticleRef) -> dict:
        try:
            document = self._articles[ref]
        except KeyError as exc:
            raise ArticleNotFound("That Akasha article does not exist.") from exc
        return {"id": ref.article_id, "document": dict(document), "rev": 1}


@pytest.fixture
def mongo_client():
    return mongomock.MongoClient()


@pytest.fixture
def document_store(mongo_client):
    store = DocumentStore(mongo_client)
    store.create_collection(WORLD, COLLECTION)
    store.create(WORLD, COLLECTION, OPEN_ARTICLE, {"title": "Highkeep"}, author="mara")
    store.create(WORLD, COLLECTION, CLOSED_ARTICLE, {"title": "Oathstone"}, author="mara")
    return store


@pytest.fixture
def article_gateway(document_store):
    return InProcessArticleGateway(document_store)


@pytest.fixture
def fake_articles():
    gateway = FakeArticleGateway()
    gateway.add(ArticleRef(WORLD, COLLECTION, OPEN_ARTICLE))
    gateway.add(ArticleRef(WORLD, COLLECTION, CLOSED_ARTICLE))
    return gateway


@pytest.fixture
def auth_store(mongo_client):
    store = AuthStore(mongo_client)
    for username in ("mara", "devi"):
        store.create_user(username, generate_password_hash(f"{username}-pw"))
    store.add_grant("mara", WORLD, None, None, ["read", "write", "delete"],
                    granted_by="admin")
    store.add_grant("devi", WORLD, None, None, ["read"], granted_by="admin")
    store.add_grant("devi", WORLD, COLLECTION, CLOSED_ARTICLE, [], granted_by="admin")
    return store


@pytest.fixture
def prithvi_store(mongo_client):
    return PrithviStore(mongo_client, clock=lambda: FIXED_TIME)


@pytest.fixture
def app(prithvi_store, article_gateway, auth_store):
    application = create_app(
        prithvi_store,
        article_gateway,
        auth_store,
        secret_key="test-secret",
        max_svg_bytes=10_000,
        akasha_url="/",
    )
    application.config.update(
        TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False
    )
    return application


def login(client, username="mara"):
    return client.post(
        "/login", json={"username": username, "password": f"{username}-pw"}
    )


@pytest.fixture
def client(app):
    """Signed in as mara, who may write."""
    test_client = app.test_client()
    assert login(test_client).status_code == 200
    return test_client


@pytest.fixture
def reader(app):
    """Signed in as devi, who may read everything except one article."""
    test_client = app.test_client()
    assert login(test_client, "devi").status_code == 200
    return test_client


@pytest.fixture
def mapped(client):
    """A world with one map already uploaded."""
    assert client.post(MAP_URL, data=SVG, content_type="image/svg+xml").status_code == 201
    return client
