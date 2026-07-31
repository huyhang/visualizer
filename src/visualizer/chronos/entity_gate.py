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

from .models import EntityRef


class EntityGate(Protocol):
    def exists(self, ref: EntityRef) -> bool: ...

    def missing(self, refs: Iterable[EntityRef]) -> list[EntityRef]: ...


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


class FakeEntityGate(_MissingMixin):
    """Test double: an explicit set of refs that exist."""

    def __init__(self, existing: Iterable[EntityRef] = ()):
        self._existing = set(existing)

    def add(self, ref: EntityRef) -> None:
        self._existing.add(ref)

    def exists(self, ref: EntityRef) -> bool:
        return ref in self._existing
