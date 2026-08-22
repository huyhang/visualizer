"""The boundary from Prithvi to the canon.

Prithvi never invents an article and never copies one: a pin is a coordinate
plus an address, and everything a response says about the article behind that
address is read through here at the moment of asking. So a renamed article
shows its new title immediately, and a deleted one shows as missing rather than
as a stale copy of what it used to be.

The seam is a ``Protocol`` rather than a class to subclass, so a test can hand
the service a dictionary-backed stand-in without inheriting anything. In
production it is the in-process implementation below, reading Akasha's own
``DocumentStore`` directly -- the same trick Chronos plays with ``EntityGate``,
and the reason there is no service-to-service HTTP anywhere in this stack.
"""

from typing import Protocol

from visualizer.akasha.errors import AkashaError

from .errors import ArticleNotFound, WorldNotFound
from .models import ArticleRef


class ArticleGateway(Protocol):
    def require_world(self, world: str) -> None:
        """Raise ``WorldNotFound`` unless ``world`` is a real Akasha database."""

    def fetch(self, ref: ArticleRef) -> dict:
        """Return Akasha's public shape for one article, or raise."""

    def list_worlds(self) -> list[str]:
        """Every Akasha world, unfiltered. The caller applies its own grants."""

    def list_articles(self, world: str) -> list[dict]:
        """Every live article in ``world``, unfiltered, as flat rows.

        Rows carry ``database``/``collection``/``id``/``document``. Grant
        filtering is the caller's job, deliberately: this seam answers "what
        exists", and only the route knows who is asking.
        """


class InProcessArticleGateway:
    """Read Akasha through an injected ``DocumentStore``, in the same process."""

    def __init__(self, document_store):
        self._store = document_store

    def list_worlds(self) -> list[str]:
        return self._store.list_databases()

    def list_articles(self, world: str) -> list[dict]:
        collections = self._collections(world)
        return [
            {"database": world, "collection": collection, **article}
            for collection in collections
            for article in self._store.list_documents(world, collection)
        ]

    def require_world(self, world: str) -> None:
        self._collections(world)

    def _collections(self, world: str) -> list[str]:
        try:
            return self._store.list_collections(world)
        except AkashaError as exc:
            raise WorldNotFound(
                f"There is no Akasha world called '{world}'.",
                evidence={"world": world},
            ) from exc

    def fetch(self, ref: ArticleRef) -> dict:
        try:
            return self._store.get(ref.world, ref.collection, ref.article_id)
        except AkashaError as exc:
            raise ArticleNotFound(
                "That Akasha article does not exist.",
                evidence={"article": ref.to_dict(title=None, status="missing")},
            ) from exc
