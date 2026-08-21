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


class InProcessArticleGateway:
    """Read Akasha through an injected ``DocumentStore``, in the same process."""

    def __init__(self, document_store):
        self._store = document_store

    def require_world(self, world: str) -> None:
        try:
            self._store.list_collections(world)
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
