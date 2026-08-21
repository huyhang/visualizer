"""The persistence seam for maps and their pins.

Thin on purpose. Both collections are ``VersionedDocuments`` from
``visualizer.documents`` -- the shared mechanics that already give Chronos its
composite keys and optimistic concurrency -- so nothing here reimplements a
revision, a tombstone or a compare-and-swap. What this module contributes is the
two identities and the error vocabulary that goes with them:

- a **map** is ``(world, map)``, so two worlds may each have a "capital" and
  neither can take that name from the other;
- a **pin** is ``(world, map, collection, article_id)``, which is to say a pin
  *is* an article's presence on a map. One article, one place per map, and a pin
  that points outside its world cannot be expressed at all.

Everything lives in a reserved ``_prithvi`` database, which the article API
never exposes. The client and clock arrive by injection, so the whole suite runs
against ``mongomock`` and a fixed time.
"""

from collections.abc import Callable
from datetime import datetime

from visualizer.documents import VersionedDocuments

from .errors import (
    AlreadyExists,
    MapNotFound,
    PinNotFound,
    RevisionConflict,
    RevisionNotRetained,
)

PRITHVI_DB = "_prithvi"
MAPS = "maps"
MAP_REVISIONS = "map_revisions"
PINS = "pins"
PIN_REVISIONS = "pin_revisions"

MAP_IDENTITY = ("world", "map")
PIN_IDENTITY = ("world", "map", "collection", "article_id")


class PrithviStore:
    """Maps and pins, each with a bounded history of its own.

    :param client: a pymongo-compatible client (or mongomock).
    :param map_revisions_keep: how many map revisions to retain. Each one holds
        a whole SVG, which is why it is capped separately and lower.
    :param pin_revisions_keep: how many pin revisions to retain. A moved pin
        costs two numbers, so this can afford to be generous.
    :param clock: returns the current time; injected for deterministic tests.
    """

    def __init__(
        self,
        client,
        *,
        map_revisions_keep: int = 5,
        pin_revisions_keep: int = 20,
        clock: Callable[[], datetime] | None = None,
    ):
        database = client[PRITHVI_DB]
        self._maps = VersionedDocuments(
            database[MAPS],
            database[MAP_REVISIONS],
            MAP_IDENTITY,
            map_revisions_keep,
            clock,
            conflict=RevisionConflict,
            gone=RevisionNotRetained,
        )
        self._pins = VersionedDocuments(
            database[PINS],
            database[PIN_REVISIONS],
            PIN_IDENTITY,
            pin_revisions_keep,
            clock,
            conflict=RevisionConflict,
            gone=RevisionNotRetained,
        )

    # -- maps -----------------------------------------------------------------

    def create_map(self, world, name, body, author) -> dict:
        return self._maps.create(_map(world, name), body, author, AlreadyExists)

    def get_map(self, world, name) -> dict:
        return self._maps.get(_map(world, name), MapNotFound)

    def list_maps(self, world) -> list[dict]:
        return self._maps.list({"world": world})

    def update_map(self, world, name, body, expected_rev, author) -> dict:
        return self._maps.update(
            _map(world, name), body, expected_rev, author, MapNotFound
        )

    def delete_map(self, world, name, expected_rev, author) -> None:
        self._maps.delete(_map(world, name), expected_rev, author, MapNotFound)

    def map_history(self, world, name) -> list[dict]:
        return self._maps.history(_map(world, name), MapNotFound)

    def map_revision(self, world, name, rev) -> dict:
        return self._maps.revision(_map(world, name), rev, MapNotFound)

    def restore_map(self, world, name, rev, expected_rev, author) -> dict:
        return self._maps.restore(
            _map(world, name), rev, expected_rev, author, MapNotFound
        )

    # -- pins -----------------------------------------------------------------

    def create_pin(self, world, name, collection, article, body, author) -> dict:
        return self._pins.create(
            _pin(world, name, collection, article), body, author, AlreadyExists
        )

    def get_pin(self, world, name, collection, article) -> dict:
        return self._pins.get(_pin(world, name, collection, article), PinNotFound)

    def list_pins(self, world, name) -> list[dict]:
        return self._pins.list({"world": world, "map": name})

    def count_pins(self, world, name) -> int:
        return self._pins.count({"world": world, "map": name})

    def update_pin(
        self, world, name, collection, article, body, expected_rev, author
    ) -> dict:
        return self._pins.update(
            _pin(world, name, collection, article),
            body,
            expected_rev,
            author,
            PinNotFound,
        )

    def delete_pin(
        self, world, name, collection, article, expected_rev, author
    ) -> None:
        self._pins.delete(
            _pin(world, name, collection, article), expected_rev, author, PinNotFound
        )

    def pin_history(self, world, name, collection, article) -> list[dict]:
        return self._pins.history(_pin(world, name, collection, article), PinNotFound)

    def pin_revision(self, world, name, collection, article, rev) -> dict:
        return self._pins.revision(
            _pin(world, name, collection, article), rev, PinNotFound
        )

    def restore_pin(
        self, world, name, collection, article, rev, expected_rev, author
    ) -> dict:
        return self._pins.restore(
            _pin(world, name, collection, article),
            rev,
            expected_rev,
            author,
            PinNotFound,
        )


def _map(world: str, name: str) -> dict:
    return {"world": world, "map": name}


def _pin(world: str, name: str, collection: str, article: str) -> dict:
    return {
        "world": world,
        "map": name,
        "collection": collection,
        "article_id": article,
    }
