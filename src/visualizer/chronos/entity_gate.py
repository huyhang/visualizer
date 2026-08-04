"""The boundary to akasha (design §6.2).

Chronos never invents characters/items/locations -- they must exist as documents
in akasha. ``EntityGate`` answers "does this reference exist?"; it is a
seam so tests inject a fake that answers from a set literal.

``InProcessEntityGate`` is the production adapter for the shared-Mongo,
ships-together deployment (constraint #1): it wraps a ``DocumentStore`` and calls
``.get(...)`` -- no network. An HTTP adapter could implement the same protocol if
the services are ever split apart.
"""

from collections.abc import Iterable
from typing import Protocol

from visualizer.akasha.errors import AkashaError

from .errors import EntityNotFound
from .models import EntityRef


class EntityGate(Protocol):
    def exists(self, ref: EntityRef) -> bool: ...

    def missing(self, refs: Iterable[EntityRef]) -> list[EntityRef]: ...

    def fetch(self, ref: EntityRef) -> dict: ...


class _MissingMixin:
    def missing(self, refs: Iterable[EntityRef]) -> list[EntityRef]:
        """Return the subset of refs that do NOT exist (empty == all good)."""
        seen: set[EntityRef] = set()
        out: list[EntityRef] = []
        for ref in refs:
            if ref in seen:
                continue
            seen.add(ref)
            if not self.exists(ref):
                out.append(ref)
        return out


class InProcessEntityGate(_MissingMixin):
    def __init__(self, document_store):
        self._store = document_store

    def exists(self, ref: EntityRef) -> bool:
        try:
            self._store.get(ref.database, ref.collection, ref.id)
            return True
        except AkashaError:
            # Missing, deleted, reserved, or otherwise unreadable -> "not there".
            return False

    def fetch(self, ref: EntityRef) -> dict:
        """Return the referenced article for read-only display.

        The UI renders Chronos's own page but its events point at Akasha
        articles; reading them back through this seam keeps the browser
        same-origin (no cross-service CORS) and reuses the shared Mongo.
        """
        try:
            return self._store.get(ref.database, ref.collection, ref.id)
        except AkashaError as exc:
            # A ref can dangle: the article may have been deleted after the
            # event was written (reads never re-check existence). Surface it as
            # a Chronos not-found so the web layer answers 404, not 500.
            raise EntityNotFound(str(exc), evidence={"ref": ref.to_dict()}) from exc


class FakeEntityGate(_MissingMixin):
    """Test double: an explicit set of refs that exist, each with a document."""

    def __init__(self, existing: Iterable[EntityRef] = ()):
        self._docs: dict[EntityRef, dict] = {}
        for ref in existing:
            self.add(ref)

    def add(self, ref: EntityRef, document: dict | None = None) -> None:
        # Default to a minimal article so ``fetch`` has something to return.
        self._docs[ref] = document if document is not None else {"title": ref.id}

    def exists(self, ref: EntityRef) -> bool:
        return ref in self._docs

    def fetch(self, ref: EntityRef) -> dict:
        if ref not in self._docs:
            raise EntityNotFound(
                f"'{ref.id}' does not exist.", evidence={"ref": ref.to_dict()}
            )
        return {"id": ref.id, "document": self._docs[ref], "rev": 1}
