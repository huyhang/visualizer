"""Private reader data and optional cross-device reading position.

The manuscript is shared; everything in this module belongs to exactly one
authenticated account.  The username is supplied by the route, never by a
request body, so one reader cannot address another reader's records.
"""

from math import isfinite
from typing import Any

from .errors import (
    InvalidReaderItem,
    InvalidReadingPosition,
    ReaderItemNotFound,
    RevisionConflict,
)
from .richtext import block_text

ITEM_KINDS = ("note", "checklist", "bookmark")
MAX_NOTE_LENGTH = 10_000
MAX_ITEM_LENGTH = 1_000
MAX_BOOKMARK_LABEL_LENGTH = 300


def validate_reader_item(payload: Any) -> dict:
    body = _mapping(payload, InvalidReaderItem, "A reader item")
    kind = body.get("kind")
    if kind not in ITEM_KINDS:
        raise InvalidReaderItem(
            "'kind' must be note, checklist, or bookmark.",
            evidence={"kind": kind},
        )
    allowed = {
        "note": {"kind", "volume", "section", "block", "text"},
        "bookmark": {"kind", "volume", "section", "block", "text"},
        "checklist": {"kind", "scope", "volume", "section", "text", "done"},
    }[kind]
    _only(body, allowed, InvalidReaderItem, kind)
    if kind in {"note", "bookmark"}:
        maximum = MAX_NOTE_LENGTH if kind == "note" else MAX_BOOKMARK_LABEL_LENGTH
        text = _text(
            body.get("text", ""), "text", maximum, allow_empty=kind == "bookmark"
        )
        return {
            "kind": kind,
            "scope": "paragraph",
            "volume": _required_id(body.get("volume"), "volume"),
            "section": _required_id(body.get("section"), "section"),
            "block": _required_id(body.get("block"), "block"),
            "text": text,
        }

    scope = body.get("scope")
    if scope not in {"book", "section"}:
        raise InvalidReaderItem("A checklist item scope must be 'book' or 'section'.")
    result = {
        "kind": kind,
        "scope": scope,
        "text": _text(body.get("text"), "text", MAX_ITEM_LENGTH),
        "done": _boolean(body.get("done", False), "done"),
    }
    if scope == "section":
        result.update(
            volume=_required_id(body.get("volume"), "volume"),
            section=_required_id(body.get("section"), "section"),
        )
    elif "volume" in body or "section" in body:
        raise InvalidReaderItem("A book checklist item cannot name a section.")
    return result


def validate_reader_item_update(kind: str, payload: Any) -> dict:
    body = _mapping(payload, InvalidReaderItem, "A reader item update")
    if kind == "note":
        _only(body, {"text"}, InvalidReaderItem, "note update")
        return {"text": _text(body.get("text"), "text", MAX_NOTE_LENGTH)}
    if kind == "bookmark":
        _only(body, {"text"}, InvalidReaderItem, "bookmark update")
        return {
            "text": _text(
                body.get("text", ""),
                "text",
                MAX_BOOKMARK_LABEL_LENGTH,
                allow_empty=True,
            )
        }
    _only(body, {"text", "done"}, InvalidReaderItem, "checklist update")
    result = {}
    if "text" in body:
        result["text"] = _text(body["text"], "text", MAX_ITEM_LENGTH)
    if "done" in body:
        result["done"] = _boolean(body["done"], "done")
    if not result:
        raise InvalidReaderItem("A checklist update must change text or completion.")
    return result


def validate_reader_settings(payload: Any) -> dict:
    body = _mapping(payload, InvalidReadingPosition, "Reader settings")
    _only(body, {"sync_reading_position"}, InvalidReadingPosition, "reader settings")
    return {
        "sync_reading_position": _boolean(
            body.get("sync_reading_position"),
            "sync_reading_position",
            InvalidReadingPosition,
        )
    }


def validate_position(payload: Any) -> dict:
    body = _mapping(payload, InvalidReadingPosition, "A reading position")
    _only(body, {"last", "furthest"}, InvalidReadingPosition, "reading position")
    last = _spot(body.get("last"), anchor=True)
    furthest = _spot(body.get("furthest"), anchor=False)
    if last is None and furthest is None:
        raise InvalidReadingPosition("A reading position must contain a valid mark.")
    return {"last": last, "furthest": furthest}


class ReaderService:
    def __init__(self, store, manuscripts):
        self.store = store
        self.manuscripts = manuscripts

    def list_items(self, username: str, book: str) -> dict:
        manuscript = self.manuscripts.publication(book)
        anchors = self._anchors(manuscript)
        items = []
        for item in self.store.list_reader_items(username, book):
            key = (item.get("volume"), item.get("section"), item.get("block"))
            anchored = item["scope"] == "paragraph"
            section_scoped = item["scope"] == "section"
            section_key = (item.get("volume"), item.get("section"))
            item["available"] = (
                key in anchors
                if anchored
                else section_key in anchors
                if section_scoped
                else True
            )
            if anchored and key in anchors:
                item["excerpt"] = anchors[key]
            items.append(item)
        return {"book": book, "items": items}

    def create_item(self, username: str, book: str, payload: Any) -> dict:
        item = validate_reader_item(payload)
        manuscript = self.manuscripts.publication(book)
        anchors = self._anchors(manuscript)
        self._require_target(item, anchors)
        if item["kind"] == "bookmark":
            for current in self.store.list_reader_items(username, book):
                if current["kind"] == "bookmark" and all(
                    current.get(field) == item.get(field)
                    for field in ("volume", "section", "block")
                ):
                    return {
                        **current,
                        "available": True,
                        "excerpt": anchors[
                            (item["volume"], item["section"], item["block"])
                        ],
                    }
        created = self.store.create_reader_item(username, book, item)
        created["available"] = True
        if item["scope"] == "paragraph":
            created["excerpt"] = anchors[
                (item["volume"], item["section"], item["block"])
            ]
        return created

    def update_item(
        self, username: str, book: str, item_id: str, payload: Any, expected_rev: int
    ) -> dict:
        self.manuscripts.require(book)
        current = self.store.find_reader_item(username, book, item_id)
        if current is None:
            raise ReaderItemNotFound(f"Reader item '{item_id}' was not found.")
        changes = validate_reader_item_update(current["kind"], payload)
        return self.store.update_reader_item(
            username, book, item_id, changes, expected_rev
        )

    def delete_item(
        self, username: str, book: str, item_id: str, expected_rev: int
    ) -> None:
        self.manuscripts.require(book)
        self.store.delete_reader_item(username, book, item_id, expected_rev)

    def get_settings(self, username: str) -> dict:
        return self.store.get_reader_settings(username)

    def set_settings(self, username: str, payload: Any) -> dict:
        settings = validate_reader_settings(payload)
        saved = self.store.set_reader_settings(username, settings)
        if not saved["sync_reading_position"]:
            self.store.delete_reading_positions(username)
        return saved

    def get_position(self, username: str, book: str) -> dict:
        if not self.get_settings(username)["sync_reading_position"]:
            self.manuscripts.require(book)
            return {"book": book, "position": None}
        # Also cheap, and for a second reason: opening the library asks this of
        # every book on the shelf at once.
        order = set(self.manuscripts.reading_order(book))
        current = self.store.get_reading_position(username, book)
        return {"book": book, "position": self._placed(order, current)}

    def set_position(self, username: str, book: str, payload: Any) -> dict:
        if not self.get_settings(username)["sync_reading_position"]:
            self.manuscripts.require(book)
            raise InvalidReadingPosition("Reading-position sync is disabled.")
        # Written on every scroll pause. Ordering records answer both questions
        # this path actually asks -- is the section still here, and which of two
        # marks is further on -- so no prose is read.
        order = self.manuscripts.reading_order(book)
        placed = set(order)
        incoming = self._placed(placed, validate_position(payload)) or {
            "last": None,
            "furthest": None,
        }
        for _attempt in range(3):
            stored = self.store.get_reading_position(username, book)
            current = self._placed(placed, stored)
            merged = {
                "last": incoming.get("last") or (current or {}).get("last"),
                "furthest": self._furthest(
                    order,
                    (current or {}).get("furthest"),
                    incoming.get("furthest") or incoming.get("last"),
                ),
            }
            try:
                saved = self.store.set_reading_position(
                    username, book, merged, expected_rev=(stored or {}).get("rev", 0)
                )
                return {"book": book, "position": saved}
            except RevisionConflict:
                continue
        raise RevisionConflict("Reading position kept changing; retry the update.")

    @staticmethod
    def _anchors(manuscript: dict) -> dict:
        anchors = {}
        for volume in manuscript["volumes"]:
            for section in volume["sections"]:
                anchors[(volume["id"], section["id"])] = ""
                for block in section["document"].get("content", []):
                    if block.get("type") != "paragraph":
                        continue
                    anchors[(volume["id"], section["id"], block["id"])] = block_text(
                        block
                    ).strip()[:240]
        return anchors

    @staticmethod
    def _require_target(item: dict, anchors: dict) -> None:
        if item["scope"] == "book":
            return
        key = (item.get("volume"), item.get("section"))
        if item["scope"] == "paragraph":
            key += (item.get("block"),)
        if key not in anchors:
            raise InvalidReaderItem("The item target is not in the current manuscript.")

    @staticmethod
    def _placed(sections: set, position: dict | None) -> dict | None:
        """Drop marks whose section has left the book, keeping their anchors.

        Whether the anchored *paragraph* still exists is not checked, here or
        anywhere: it would cost every document on a path that runs at scroll
        rate and again for every book on the shelf, and it buys nothing. The
        reader already treats an anchor it cannot find as absent and falls back
        to the mark's progress through the section.
        """
        if not position:
            return None
        result = {
            field: (
                dict(mark)
                if mark and (mark["volume"], mark["section"]) in sections
                else None
            )
            for field, mark in (
                ("last", position.get("last")),
                ("furthest", position.get("furthest")),
            )
        }
        return result if result["last"] or result["furthest"] else None

    @staticmethod
    def _furthest(
        order: list[tuple[str, str]], first: dict | None, second: dict | None
    ):
        """Whichever mark is further through the book. Ties go to progress."""
        if first is None:
            return second
        if second is None:
            return first
        rank = {pair: index for index, pair in enumerate(order)}
        left = rank.get((first["volume"], first["section"]), -1)
        right = rank.get((second["volume"], second["section"]), -1)
        if left != right:
            return second if right > left else first
        return second if second["progress"] > first["progress"] else first


def _spot(value: Any, *, anchor: bool) -> dict | None:
    if value is None:
        return None
    body = _mapping(value, InvalidReadingPosition, "A reading mark")
    allowed = {"volume", "section", "progress"}
    if anchor:
        allowed |= {"block", "offset"}
    _only(body, allowed, InvalidReadingPosition, "reading mark")
    progress = body.get("progress")
    if (
        isinstance(progress, bool)
        or not isinstance(progress, (int, float))
        or not isfinite(progress)
    ):
        raise InvalidReadingPosition("'progress' must be a finite number.")
    if progress < 0 or progress > 1:
        raise InvalidReadingPosition("'progress' must be between 0 and 1.")
    result = {
        "volume": _required_id(body.get("volume"), "volume", InvalidReadingPosition),
        "section": _required_id(body.get("section"), "section", InvalidReadingPosition),
        "progress": float(progress),
    }
    if anchor:
        block = body.get("block")
        if block is not None and (not isinstance(block, str) or not block):
            raise InvalidReadingPosition("'block' must be text or null.")
        offset = body.get("offset", 0)
        if (
            isinstance(offset, bool)
            or not isinstance(offset, (int, float))
            or not isfinite(offset)
        ):
            raise InvalidReadingPosition("'offset' must be a finite number.")
        result.update(block=block, offset=float(offset))
    return result


def _mapping(value: Any, error, label: str) -> dict:
    if not isinstance(value, dict):
        raise error(f"{label} must be a JSON object.")
    return value


def _only(body: dict, allowed: set[str], error, label: str) -> None:
    unexpected = sorted(set(body) - allowed)
    if unexpected:
        raise error(
            f"The {label} contains unsupported fields.",
            evidence={"unexpected": unexpected},
        )


def _required_id(value: Any, field: str, error=InvalidReaderItem) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise error(f"'{field}' must be non-empty text of at most 128 characters.")
    return value.strip()


def _text(value: Any, field: str, maximum: int, *, allow_empty=False) -> str:
    if not isinstance(value, str):
        raise InvalidReaderItem(f"'{field}' must be text.")
    text = value.strip()
    if not allow_empty and not text:
        raise InvalidReaderItem(f"'{field}' must not be empty.")
    if len(text) > maximum:
        raise InvalidReaderItem(f"'{field}' must be at most {maximum} characters.")
    return text


def _boolean(value: Any, field: str, error=InvalidReaderItem) -> bool:
    if not isinstance(value, bool):
        raise error(f"'{field}' must be true or false.")
    return value
