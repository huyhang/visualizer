"""Application services -- thin orchestration between the two seams.

Everything a request means happens here: validate purely, ask the store, ask
Akasha, shape the answer. This module knows nothing about Flask and nothing
about Mongo internals, which is what lets most of the suite exercise it with a
dictionary-backed article gateway and an in-memory client.

One convention is load-bearing and worth stating plainly. Every method that can
return a pin takes ``may_read``, a predicate over an ``ArticleRef``, and it is a
required argument rather than an optional filter. Whether a reader may see a pin
depends on their grant over the *article* it names, not over the map, and that
rule is enforced here rather than in the route layer -- so a route added next
year cannot forget it, because it cannot call these methods without answering
the question. A reader who fails the predicate is told the pin does not exist,
since "forbidden" would confirm that something is pinned there.
"""

from collections.abc import Callable

from visualizer.akasha.labels import derive_title

from .articles import ArticleGateway
from .errors import (
    ArticleNotFound,
    Forbidden,
    PinNotFound,
    RevisionNotRetained,
    ViewBoxLocked,
)
from .models import ArticleRef, ViewBox
from .rendering import render_pins
from .store import PrithviStore
from .svg import SanitizedSvg
from .validation import (
    validate_article_address,
    validate_map_name,
    validate_position,
    validate_scale,
    validate_world,
)

MayRead = Callable[[ArticleRef], bool]


class PrithviService:
    """:param store: the Mongo seam.
    :param articles: the Akasha seam.
    :param sanitize: turns uploaded bytes into a ``SanitizedSvg``; injected so
        the size cap is configuration rather than a constant in this module.
    :param akasha_url: where a rendered pin should link to.
    """

    def __init__(
        self,
        store: PrithviStore,
        articles: ArticleGateway,
        sanitize: Callable[[bytes], SanitizedSvg],
        akasha_url: str,
    ):
        self._store = store
        self._articles = articles
        self._sanitize = sanitize
        self._akasha_url = akasha_url

    # -- maps -----------------------------------------------------------------

    def create_map(self, world, name, upload: bytes, author: str) -> dict:
        self._address(world, name)
        self._articles.require_world(world)
        body = _body(self._sanitize(upload), scale=None)
        return _map_view(self._store.create_map(world, name, body, author))

    def list_maps(self, world) -> list[dict]:
        validate_world(world)
        return [_map_view(row) for row in self._store.list_maps(world)]

    def get_map(self, world, name) -> dict:
        return _map_view(self._record(world, name))

    def get_svg(self, world, name) -> dict:
        """The stored drawing itself, with the revision it belongs to."""
        return self._record(world, name)

    def replace_svg(self, world, name, upload: bytes, expected_rev, author) -> dict:
        current = self._record(world, name)
        sanitized = self._sanitize(upload)
        self._require_same_space(world, name, sanitized.view_box.to_list(), current)
        body = _body(sanitized, scale=current.get("scale"))
        updated = self._store.update_map(world, name, body, expected_rev, author)
        return _map_view(updated)

    def set_scale(self, world, name, payload, expected_rev, author) -> dict:
        """Record how far across the map is. Its own revision, like any edit."""
        current = self._record(world, name)
        scale = validate_scale(payload)
        body = {
            "svg": current["svg"],
            "view_box": current["view_box"],
            "sanitization": current["sanitization"],
            "scale": scale.to_dict(),
        }
        return _map_view(self._store.update_map(world, name, body, expected_rev, author))

    def delete_map(self, world, name, expected_rev, author) -> None:
        self._address(world, name)
        self._store.delete_map(world, name, expected_rev, author)

    def map_history(self, world, name) -> list[dict]:
        self._address(world, name)
        return self._store.map_history(world, name)

    def map_revision(self, world, name, rev) -> dict:
        self._address(world, name)
        return _revision_view(self._store.map_revision(world, name, rev))

    def restore_map(self, world, name, rev, expected_rev, author) -> dict:
        self._address(world, name)
        target = self._store.map_revision(world, name, rev)
        if target["deleted"]:
            raise RevisionNotRetained(f"Revision {rev} is a deletion; nothing to restore.")
        self._require_same_space(world, name, target["view_box"], self._last_drawn(world, name))
        restored = self._store.restore_map(world, name, rev, expected_rev, author)
        return _map_view(restored)

    def render(self, world, name, may_read: MayRead) -> str:
        record = self._record(world, name)
        pins = self.list_pins(world, name, may_read)
        view_box = ViewBox.from_list(record["view_box"])
        return render_pins(record["svg"], view_box, pins, self._akasha_url)

    # -- pins -----------------------------------------------------------------

    def create_pin(self, world, name, collection, article, payload, may_read, author):
        ref = self._pin_address(world, name, collection, article)
        # Permission first: a caller who may not read the article should not be
        # able to learn the map's shape from an out-of-bounds error.
        self._require_readable(ref, may_read)
        position = validate_position(payload, self._space(world, name))
        self._articles.fetch(ref)
        record = self._store.create_pin(
            world, name, collection, article, position.to_dict(), author
        )
        return self._pin_view(record)

    def list_pins(self, world, name, may_read: MayRead) -> list[dict]:
        self._record(world, name)
        rows = self._store.list_pins(world, name)
        return [self._pin_view(row) for row in rows if may_read(_ref(row))]

    def get_pin(self, world, name, collection, article, may_read: MayRead) -> dict:
        ref = self._pin_address(world, name, collection, article)
        self._record(world, name)
        self._require_visible(ref, may_read)
        return self._pin_view(self._store.get_pin(world, name, collection, article))

    def update_pin(
        self, world, name, collection, article, payload, may_read, expected_rev, author
    ) -> dict:
        ref = self._pin_address(world, name, collection, article)
        self._require_readable(ref, may_read)
        position = validate_position(payload, self._space(world, name))
        record = self._store.update_pin(
            world, name, collection, article, position.to_dict(), expected_rev, author
        )
        return self._pin_view(record)

    def delete_pin(
        self, world, name, collection, article, may_read, expected_rev, author
    ) -> None:
        ref = self._pin_address(world, name, collection, article)
        self._record(world, name)
        self._require_visible(ref, may_read)
        self._store.delete_pin(world, name, collection, article, expected_rev, author)

    def pin_history(self, world, name, collection, article, may_read) -> list[dict]:
        ref = self._pin_address(world, name, collection, article)
        self._record(world, name)
        self._require_visible(ref, may_read)
        return self._store.pin_history(world, name, collection, article)

    def pin_revision(self, world, name, collection, article, rev, may_read) -> dict:
        ref = self._pin_address(world, name, collection, article)
        self._record(world, name)
        self._require_visible(ref, may_read)
        record = self._store.pin_revision(world, name, collection, article, rev)
        return self._pin_revision_view(record)

    def restore_pin(
        self, world, name, collection, article, rev, may_read, expected_rev, author
    ) -> dict:
        ref = self._pin_address(world, name, collection, article)
        space = self._space(world, name)
        self._require_readable(ref, may_read)
        target = self._store.pin_revision(world, name, collection, article, rev)
        if target["deleted"]:
            raise RevisionNotRetained(f"Revision {rev} is a deletion; nothing to restore.")
        # The map's box cannot have moved under a live pin, but a restore may
        # reach back past a period when the map had none and was reshaped.
        validate_position({"x": target["x"], "y": target["y"]}, space)
        record = self._store.restore_pin(
            world, name, collection, article, rev, expected_rev, author
        )
        return self._pin_view(record)

    # -- shared -----------------------------------------------------------------

    def _address(self, world, name) -> None:
        validate_world(world)
        validate_map_name(name)

    def _pin_address(self, world, name, collection, article) -> ArticleRef:
        self._address(world, name)
        validate_article_address(collection, article)
        return ArticleRef(world, collection, article)

    def _record(self, world, name) -> dict:
        self._address(world, name)
        return self._store.get_map(world, name)

    def _space(self, world, name) -> ViewBox:
        return ViewBox.from_list(self._record(world, name)["view_box"])

    def _require_readable(self, ref: ArticleRef, may_read: MayRead) -> None:
        """For writes: naming an article you cannot read is refused outright."""
        if not may_read(ref):
            raise Forbidden("You lack read permission on that Akasha article.")

    def _require_visible(self, ref: ArticleRef, may_read: MayRead) -> None:
        """For reads: an invisible pin is indistinguishable from an absent one."""
        if not may_read(ref):
            raise PinNotFound("That pin was not found.")

    def _require_same_space(self, world, name, incoming, against) -> None:
        """A map with pins on it may not change the space they are measured in."""
        existing = (against or {}).get("view_box")
        if existing is None or incoming == existing:
            return
        if self._store.count_pins(world, name):
            raise ViewBoxLocked(
                "A map's viewBox cannot change while it has pins.",
                evidence={"current": existing, "submitted": incoming},
            )

    def _last_drawn(self, world, name) -> dict | None:
        """The newest retained revision that still has a drawing in it.

        Needed because a restore may be aimed at a tombstoned map, where "the
        box the pins were placed against" is not the current head's.
        """
        for meta in self._store.map_history(world, name):
            if not meta["deleted"]:
                return self._store.map_revision(world, name, meta["rev"])
        return None

    def _pin_view(self, record: dict) -> dict:
        return {
            "world": record["world"],
            "map": record["map"],
            "article": self._describe(_ref(record)),
            "position": {"x": record["x"], "y": record["y"]},
            "rev": record["rev"],
            "created_by": record.get("created_by"),
            "updated_by": record.get("updated_by"),
            "updated_at": record.get("updated_at"),
        }

    def _pin_revision_view(self, record: dict) -> dict:
        body = {
            "world": record["world"],
            "map": record["map"],
            "article": self._describe(_ref(record)),
            "position": None,
            **_revision_meta(record),
        }
        if not record["deleted"]:
            body["position"] = {"x": record["x"], "y": record["y"]}
        return body

    def _describe(self, ref: ArticleRef) -> dict:
        """The article as it is *now* -- one read per pin, never a stored copy.

        A map holds tens of pins, not thousands, so a read each is cheaper than
        the staleness a cached title would buy.
        """
        try:
            found = self._articles.fetch(ref)
        except ArticleNotFound:
            return ref.to_dict(title=None, status="missing")
        title = (found.get("document") or {}).get("title") or ref.article_id
        return ref.to_dict(title=str(title), status="available")


def _ref(record: dict) -> ArticleRef:
    return ArticleRef(record["world"], record["collection"], record["article_id"])


def _body(svg: SanitizedSvg, scale) -> dict:
    return {
        "svg": svg.content,
        "view_box": svg.view_box.to_list(),
        "sanitization": svg.report,
        "scale": scale,
    }


def _map_view(record: dict) -> dict:
    """A map without its drawing -- that is a separate, much larger request.

    ``title`` is derived here rather than in the browser: ``labels.py`` exists
    so there is exactly one implementation of that rule, and a listing ships
    the readable name beside the slug so a page can print what it was given.
    """
    return {
        "world": record["world"],
        "id": record["map"],
        "title": derive_title(record["map"]),
        "rev": record["rev"],
        "view_box": record["view_box"],
        "scale": record.get("scale"),
        "sanitization": record["sanitization"],
        "created_by": record.get("created_by"),
        "updated_by": record.get("updated_by"),
        "updated_at": record.get("updated_at"),
    }


def _revision_view(record: dict) -> dict:
    body = {"world": record["world"], "id": record["map"], **_revision_meta(record)}
    if not record["deleted"]:
        body["view_box"] = record["view_box"]
        body["scale"] = record.get("scale")
    return body


def _revision_meta(record: dict) -> dict:
    return {
        "rev": record["rev"],
        "op": record["op"],
        "author": record.get("author"),
        "timestamp": record["timestamp"],
        "deleted": record["deleted"],
    }
