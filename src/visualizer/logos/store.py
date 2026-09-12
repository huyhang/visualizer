"""MongoDB persistence for manuscripts, publication data and private reader state.

Manuscript and publication records use the shared ``VersionedDocuments`` engine
in the reserved ``_logos`` database. Sections and their named drafts retain real
history because prose cannot be reconstructed; ordering and publication metadata
retain only their current revision. Private reader items use smaller
account-keyed records with compare-and-swap updates.

Search is a projection maintained on the *write* path. Reads never rebuild it:
a rebuild driven by a reader would make one account's search a write against
state every other account reads, and two interleaved rebuilds from different
manuscript snapshots can reinstate a section that was just deleted.

Every account-scoped record is addressed by separate ``username`` and ``book``
fields rather than a joined key. Neither usernames nor Chronos book ids restrict
the punctuation a separator would need, so a joined key is a collision waiting
for the right pair of names.

``find_*`` answers "is this here?" with ``None`` rather than an exception, so the
services can ask without using exceptions for control flow. ``get_*`` raises.
"""

import re
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from visualizer.documents import VersionedDocuments

from .errors import (
    AlreadyExists,
    DraftNotFound,
    ManuscriptNotFound,
    ReaderItemNotFound,
    RevisionConflict,
    RevisionNotRetained,
    SectionNotFound,
    VolumeNotFound,
)

LOGOS_DB = "_logos"
OUTLINES = "outlines"
OUTLINE_REVISIONS = "outline_revisions"
VOLUMES = "volumes"
VOLUME_REVISIONS = "volume_revisions"
SECTIONS = "sections"
SECTION_REVISIONS = "section_revisions"
DRAFTS = "drafts"
DRAFT_REVISIONS = "draft_revisions"
PUBLICATIONS = "publications"
PUBLICATION_REVISIONS = "publication_revisions"
PUBLICATION_COVERS = "publication_covers"
READER_ITEMS = "reader_items"
READER_SETTINGS = "reader_settings"
READING_POSITIONS = "reading_positions"
SEARCH_BLOCKS = "search_blocks"
EXPORT_JOBS = "export_jobs"
SECTION_MOVES = "section_moves"

OUTLINE_IDENTITY = ("book",)
VOLUME_IDENTITY = ("book", "volume")
SECTION_IDENTITY = ("book", "volume", "section")
DRAFT_IDENTITY = ("book", "volume", "section", "draft")
PUBLICATION_IDENTITY = ("book",)

# Ordering records carry no prose, so their history would be a list of
# rearrangements nobody asks to read back.
ORDERING_REVISIONS_KEEP = 1


class LogosStore:
    def __init__(
        self,
        client,
        *,
        section_revisions_keep: int = 20,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ):
        database = client[LOGOS_DB]
        self._database = database
        self._outlines = self._documents(
            database, OUTLINES, OUTLINE_REVISIONS, OUTLINE_IDENTITY,
            ORDERING_REVISIONS_KEEP, clock,
        )
        self._volumes = self._documents(
            database, VOLUMES, VOLUME_REVISIONS, VOLUME_IDENTITY,
            ORDERING_REVISIONS_KEEP, clock,
        )
        self._sections = self._documents(
            database, SECTIONS, SECTION_REVISIONS, SECTION_IDENTITY,
            section_revisions_keep, clock,
        )
        self._drafts = self._documents(
            database, DRAFTS, DRAFT_REVISIONS, DRAFT_IDENTITY,
            section_revisions_keep, clock,
        )
        self._publications = self._documents(
            database,
            PUBLICATIONS,
            PUBLICATION_REVISIONS,
            PUBLICATION_IDENTITY,
            ORDERING_REVISIONS_KEEP,
            clock,
        )
        self._reader_items = database[READER_ITEMS]
        self._reader_settings = database[READER_SETTINGS]
        self._reading_positions = database[READING_POSITIONS]
        self._publication_covers = database[PUBLICATION_COVERS]
        self._search_blocks = database[SEARCH_BLOCKS]
        self._export_jobs = database[EXPORT_JOBS]
        self._section_moves = database[SECTION_MOVES]
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: str(uuid4()))
        self._reader_items.create_index([("username", 1), ("book", 1)])
        self._reader_items.create_index(
            [
                ("username", 1),
                ("book", 1),
                ("kind", 1),
                ("volume", 1),
                ("section", 1),
                ("block", 1),
            ],
            unique=True,
            partialFilterExpression={"kind": "bookmark"},
        )
        # Unique, because an absent position is created with a compare-and-swap
        # against "no record yet"; two devices racing that must not both win.
        self._reading_positions.create_index(
            [("username", 1), ("book", 1)], unique=True
        )
        self._search_blocks.create_index([("book", 1), ("order", 1)])
        self._export_jobs.create_index([("book", 1), ("owner", 1)])
        self._export_jobs.create_index([("started_at", 1)])
        self._section_moves.create_index(
            [("book", 1), ("source_volume", 1), ("section", 1)], unique=True
        )

    @staticmethod
    def _documents(database, heads, revisions, identity, keep, clock):
        return VersionedDocuments(
            database[heads],
            database[revisions],
            identity,
            keep,
            clock,
            conflict=RevisionConflict,
            gone=RevisionNotRetained,
        )

    # -- outline --------------------------------------------------------------

    def find_outline(self, book: str) -> dict | None:
        try:
            return self._outlines.get({"book": book}, ManuscriptNotFound)
        except ManuscriptNotFound:
            return None

    def create_outline(self, book: str, body: dict, author: str) -> dict:
        return self._outlines.create({"book": book}, body, author, AlreadyExists)

    def update_outline(
        self, book: str, body: dict, expected_rev: int, author: str
    ) -> dict:
        return self._outlines.update(
            {"book": book}, body, expected_rev, author, ManuscriptNotFound
        )

    # -- volumes --------------------------------------------------------------

    def create_volume(self, book: str, volume: str, body: dict, author: str) -> dict:
        return self._volumes.create(
            self._volume_key(book, volume), body, author, AlreadyExists
        )

    def get_volume(self, book: str, volume: str) -> dict:
        return self._volumes.get(self._volume_key(book, volume), VolumeNotFound)

    def find_volume(self, book: str, volume: str) -> dict | None:
        try:
            return self.get_volume(book, volume)
        except VolumeNotFound:
            return None

    def list_volumes(self, book: str) -> list[dict]:
        return self._volumes.list({"book": book})

    def update_volume(
        self, book: str, volume: str, body: dict, expected_rev: int, author: str
    ) -> dict:
        return self._volumes.update(
            self._volume_key(book, volume), body, expected_rev, author, VolumeNotFound
        )

    def delete_volume(
        self, book: str, volume: str, expected_rev: int, author: str
    ) -> None:
        self._volumes.delete(
            self._volume_key(book, volume), expected_rev, author, VolumeNotFound
        )

    # -- sections -------------------------------------------------------------

    def create_section(
        self, book: str, volume: str, section: str, body: dict, author: str
    ) -> dict:
        return self._sections.create(
            self._section_key(book, volume, section), body, author, AlreadyExists
        )

    def get_section(self, book: str, volume: str, section: str) -> dict:
        return self._sections.get(
            self._section_key(book, volume, section), SectionNotFound
        )

    def find_section(self, book: str, volume: str, section: str) -> dict | None:
        try:
            return self.get_section(book, volume, section)
        except SectionNotFound:
            return None

    def list_sections(self, book: str, volume: str | None = None) -> list[dict]:
        filters = {"book": book}
        if volume is not None:
            filters["volume"] = volume
        return self._sections.list(filters)

    def section_ids(self, book: str) -> set[tuple[str, str]]:
        """Live ``(volume, section)`` pairs, without loading a word of prose.

        Anything that only needs to know *whether* a section exists — checking a
        note's anchor, ordering two reading marks — asks here instead of
        assembling the manuscript.
        """
        rows = self._database[SECTIONS].find(
            {"book": book, "deleted": False}, {"volume": 1, "section": 1, "_id": 0}
        )
        return {(row["volume"], row["section"]) for row in rows}

    def update_section(
        self,
        book: str,
        volume: str,
        section: str,
        body: dict,
        expected_rev: int,
        author: str,
    ) -> dict:
        return self._sections.update(
            self._section_key(book, volume, section),
            body,
            expected_rev,
            author,
            SectionNotFound,
        )

    def delete_section(
        self, book: str, volume: str, section: str, expected_rev: int, author: str
    ) -> None:
        self._sections.delete(
            self._section_key(book, volume, section),
            expected_rev,
            author,
            SectionNotFound,
        )

    def section_history(self, book: str, volume: str, section: str) -> list[dict]:
        return self._sections.history(
            self._section_key(book, volume, section), SectionNotFound
        )

    def section_revision(
        self, book: str, volume: str, section: str, rev: int
    ) -> dict:
        return self._sections.revision(
            self._section_key(book, volume, section), rev, SectionNotFound
        )

    def restore_section(
        self,
        book: str,
        volume: str,
        section: str,
        rev: int,
        expected_rev: int,
        author: str,
        primary_draft_id: str | None = None,
    ) -> dict:
        def preserve_primary(body: dict) -> dict:
            if primary_draft_id:
                body["primary_draft_id"] = primary_draft_id
            return body

        return self._sections.restore(
            self._section_key(book, volume, section),
            rev,
            expected_rev,
            author,
            SectionNotFound,
            preserve_primary,
        )

    def relocate_section(
        self,
        book: str,
        source_volume: str,
        target_volume: str,
        section: str,
        expected_rev: int,
        author: str,
    ) -> dict:
        return self._sections.relocate(
            self._section_key(book, source_volume, section),
            self._section_key(book, target_volume, section),
            expected_rev,
            author,
            SectionNotFound,
            AlreadyExists,
        )

    def section_identity_exists(self, book: str, volume: str, section: str) -> bool:
        return self._sections.identity_exists(
            self._section_key(book, volume, section)
        )

    # -- drafts ---------------------------------------------------------------

    def new_draft_id(self) -> str:
        return self._id_factory()

    def create_draft(
        self, book: str, volume: str, section: str, draft: str,
        body: dict, author: str,
    ) -> dict:
        return self._drafts.create(
            self._draft_key(book, volume, section, draft),
            body,
            author,
            AlreadyExists,
        )

    def get_draft(
        self, book: str, volume: str, section: str, draft: str
    ) -> dict:
        return self._drafts.get(
            self._draft_key(book, volume, section, draft), DraftNotFound
        )

    def find_draft(
        self, book: str, volume: str, section: str, draft: str
    ) -> dict | None:
        try:
            return self.get_draft(book, volume, section, draft)
        except DraftNotFound:
            return None

    def list_drafts(self, book: str, volume: str, section: str) -> list[dict]:
        return self._drafts.list(
            {"book": book, "volume": volume, "section": section}
        )

    def update_draft(
        self, book: str, volume: str, section: str, draft: str,
        body: dict, expected_rev: int, author: str,
    ) -> dict:
        return self._drafts.update(
            self._draft_key(book, volume, section, draft),
            body,
            expected_rev,
            author,
            DraftNotFound,
        )

    def delete_draft(
        self, book: str, volume: str, section: str, draft: str,
        expected_rev: int, author: str,
    ) -> None:
        self._drafts.delete(
            self._draft_key(book, volume, section, draft),
            expected_rev,
            author,
            DraftNotFound,
        )

    def draft_history(
        self, book: str, volume: str, section: str, draft: str
    ) -> list[dict]:
        return self._drafts.history(
            self._draft_key(book, volume, section, draft), DraftNotFound
        )

    def draft_revision(
        self, book: str, volume: str, section: str, draft: str, rev: int
    ) -> dict:
        return self._drafts.revision(
            self._draft_key(book, volume, section, draft), rev, DraftNotFound
        )

    def restore_draft(
        self,
        book: str,
        volume: str,
        section: str,
        draft: str,
        rev: int,
        expected_rev: int,
        author: str,
    ) -> dict:
        return self._drafts.restore(
            self._draft_key(book, volume, section, draft),
            rev,
            expected_rev,
            author,
            DraftNotFound,
        )

    def relocate_draft(
        self,
        book: str,
        source_volume: str,
        target_volume: str,
        section: str,
        draft: str,
        expected_rev: int,
        author: str,
    ) -> dict:
        return self._drafts.relocate(
            self._draft_key(book, source_volume, section, draft),
            self._draft_key(book, target_volume, section, draft),
            expected_rev,
            author,
            DraftNotFound,
            AlreadyExists,
        )

    def draft_identity_exists(
        self, book: str, volume: str, section: str, draft: str
    ) -> bool:
        return self._drafts.identity_exists(
            self._draft_key(book, volume, section, draft)
        )

    # -- section movement ----------------------------------------------------

    def find_section_move(
        self, book: str, source_volume: str, section: str
    ) -> dict | None:
        return self._section_moves.find_one(
            {
                "book": book,
                "source_volume": source_volume,
                "section": section,
            },
            {"_id": 0},
        )

    def begin_section_move(
        self,
        book: str,
        source_volume: str,
        target_volume: str,
        section: str,
        before: str | None,
        expected_rev: int,
        author: str,
        title: str | None,
        kind: str,
        *,
        restart: bool = False,
    ) -> dict:
        existing = self.find_section_move(book, source_volume, section)
        if existing is not None and not restart:
            return existing
        body = {
            "book": book,
            "source_volume": source_volume,
            "target_volume": target_volume,
            "section": section,
            "before": before,
            "section_rev": expected_rev,
            "author": author,
            "title": title,
            "kind": kind,
            "state": "moving",
            "started_at": self._now(),
        }
        if restart:
            self._section_moves.update_one(
                {
                    "book": book,
                    "source_volume": source_volume,
                    "section": section,
                    "state": "complete",
                },
                {"$set": body, "$unset": {"completed_at": ""}},
            )
            return self.find_section_move(book, source_volume, section)
        record = {"_id": self._id_factory(), **body}
        try:
            self._section_moves.insert_one(record)
        except DuplicateKeyError:
            return self.find_section_move(book, source_volume, section)
        return {key: value for key, value in record.items() if key != "_id"}

    def complete_section_move(
        self, book: str, source_volume: str, section: str, target_volume: str
    ) -> None:
        """Retire a move, then collapse the aliases it leaves behind.

        Every completed alias for this section is re-pointed at the volume it
        now lives in, and the one that would name its own home is dropped. So a
        section that has toured five volumes leaves four aliases, not a row per
        hop, and a round trip leaves none at all -- the table is bounded by the
        volumes a section has lived in rather than by how often it was filed.
        """
        self._section_moves.update_one(
            {
                "book": book,
                "source_volume": source_volume,
                "section": section,
            },
            {"$set": {"state": "complete", "completed_at": self._now()}},
        )
        self._section_moves.update_many(
            {"book": book, "section": section, "state": "complete"},
            {"$set": {"target_volume": target_volume}},
        )
        self._section_moves.delete_many(
            {
                "book": book,
                "section": section,
                "state": "complete",
                "source_volume": target_volume,
            }
        )

    def release_section_move(self, book: str, volume: str, section: str) -> None:
        """Forget the alias leaving ``volume``, because that address is in use again.

        An alias only makes sense while nothing lives at the address it points
        away from. Creating a section there makes it ambiguous, so the alias
        goes: a stale link stops resolving, which is a smaller loss than
        refusing to let a writer reuse a name they have freed.
        """
        self._section_moves.delete_many(
            {
                "book": book,
                "source_volume": volume,
                "section": section,
                "state": "complete",
            }
        )

    def list_section_moves(self, book: str) -> list[dict]:
        rows = self._section_moves.find(
            {"book": book, "state": "complete"},
            {"_id": 0, "source_volume": 1, "target_volume": 1, "section": 1},
        ).sort([("source_volume", 1), ("section", 1)])
        return list(rows)

    def list_pending_section_moves(self, book: str) -> list[dict]:
        fields = {
            "_id": 0,
            "source_volume": 1,
            "target_volume": 1,
            "section": 1,
            "before": 1,
            "section_rev": 1,
            "title": 1,
            "kind": 1,
        }
        rows = self._section_moves.find(
            {"book": book, "state": "moving"}, fields
        ).sort("started_at", 1)
        return list(rows)

    def has_pending_section_moves(self, book: str, volume: str) -> bool:
        return self._section_moves.find_one(
            {
                "book": book,
                "state": "moving",
                "$or": [
                    {"source_volume": volume},
                    {"target_volume": volume},
                ],
            },
            {"_id": 1},
        ) is not None

    def resolve_section_location(
        self, book: str, volume: str, section: str
    ) -> tuple[str, str]:
        """Follow completed move aliases for stale links and reading marks.

        A live section at the address given wins outright: an alias describes
        where something *went*, and nothing went anywhere if it is still here.
        Aliases are collapsed on completion, so the walk below settles in one
        hop; the loop and its guard remain because a half-collapsed table after
        an interrupted write must still terminate.
        """
        if self.find_section(book, volume, section) is not None:
            return volume, section
        seen = set()
        current = volume
        while current not in seen:
            seen.add(current)
            moved = self._section_moves.find_one(
                {
                    "book": book,
                    "source_volume": current,
                    "section": section,
                    "state": "complete",
                }
            )
            if moved is None:
                break
            current = moved["target_volume"]
        return current, section

    def move_reader_locations(
        self, book: str, source_volume: str, target_volume: str, section: str
    ) -> None:
        match = {"book": book, "volume": source_volume, "section": section}
        self._reader_items.update_many(match, {"$set": {"volume": target_volume}})
        for row in self._reading_positions.find({"book": book}):
            changes = {}
            for field in ("last", "furthest"):
                mark = row.get(field)
                if (
                    mark
                    and mark.get("volume") == source_volume
                    and mark.get("section") == section
                ):
                    changes[field] = {**mark, "volume": target_volume}
            if changes:
                self._reading_positions.update_one(
                    {"_id": row["_id"], "rev": row.get("rev", 1)},
                    {"$set": {**changes, "updated_at": self._now()}, "$inc": {"rev": 1}},
                )

    # -- shelf-wide reads -----------------------------------------------------

    def outlines_by_book(self) -> dict[str, dict]:
        """Every outline in one query, so listing books is not one query each."""
        return {row["book"]: row for row in self._outlines.list({})}

    def volumes_by_book(self) -> dict[str, list[dict]]:
        grouped: dict[str, list[dict]] = {}
        for row in self._volumes.list({}):
            grouped.setdefault(row["book"], []).append(row)
        return grouped

    # -- private reader data -------------------------------------------------

    def list_reader_items(self, username: str, book: str) -> list[dict]:
        rows = self._reader_items.find({"username": username, "book": book})
        return [self._public_reader_item(row) for row in rows.sort("created_at", 1)]

    def create_reader_item(self, username: str, book: str, body: dict) -> dict:
        moment = self._now()
        record = {
            "_id": self._id_factory(),
            "username": username,
            "book": book,
            "rev": 1,
            "created_at": moment,
            "updated_at": moment,
            **body,
        }
        try:
            self._reader_items.insert_one(record)
        except DuplicateKeyError as exc:
            raise AlreadyExists("That reader item already exists.") from exc
        return self._public_reader_item(record)

    def find_reader_item(self, username: str, book: str, item: str) -> dict | None:
        row = self._reader_items.find_one(
            {"_id": item, "username": username, "book": book}
        )
        return self._public_reader_item(row) if row else None

    def update_reader_item(
        self,
        username: str,
        book: str,
        item: str,
        body: dict,
        expected_rev: int,
    ) -> dict:
        record = self._reader_items.find_one_and_update(
            {
                "_id": item,
                "username": username,
                "book": book,
                "rev": expected_rev,
            },
            {"$set": {**body, "updated_at": self._now()}, "$inc": {"rev": 1}},
            return_document=ReturnDocument.AFTER,
        )
        if record is None:
            self._reader_item_write_error(username, book, item, expected_rev)
        return self._public_reader_item(record)

    def delete_reader_item(
        self, username: str, book: str, item: str, expected_rev: int
    ) -> None:
        result = self._reader_items.delete_one(
            {
                "_id": item,
                "username": username,
                "book": book,
                "rev": expected_rev,
            }
        )
        if result.deleted_count == 0:
            self._reader_item_write_error(username, book, item, expected_rev)

    def _reader_item_write_error(
        self, username: str, book: str, item: str, expected_rev: int
    ) -> None:
        current = self.find_reader_item(username, book, item)
        if current is None:
            raise ReaderItemNotFound(f"Reader item '{item}' was not found.")
        raise RevisionConflict(
            f"Modified since revision {expected_rev}; reload and retry.",
            evidence={"expected": expected_rev, "actual": current["rev"]},
        )

    def get_reader_settings(self, username: str) -> dict:
        row = self._reader_settings.find_one({"_id": username}) or {}
        return {"sync_reading_position": bool(row.get("sync_reading_position", False))}

    def set_reader_settings(self, username: str, settings: dict) -> dict:
        self._reader_settings.update_one(
            {"_id": username}, {"$set": dict(settings)}, upsert=True
        )
        return self.get_reader_settings(username)

    def delete_reading_positions(self, username: str) -> None:
        self._reading_positions.delete_many({"username": username})

    @staticmethod
    def _position_key(username: str, book: str) -> dict:
        return {"username": username, "book": book}

    def get_reading_position(self, username: str, book: str) -> dict | None:
        row = self._reading_positions.find_one(self._position_key(username, book))
        if row is None:
            return None
        return {
            "last": row.get("last"),
            "furthest": row.get("furthest"),
            "updated_at": row.get("updated_at"),
            "rev": row.get("rev", 1),
        }

    def set_reading_position(
        self, username: str, book: str, position: dict, expected_rev: int
    ) -> dict:
        owner = self._position_key(username, book)
        body = {
            "last": position.get("last"),
            "furthest": position.get("furthest"),
            "updated_at": self._now(),
        }
        if expected_rev == 0:
            try:
                self._reading_positions.insert_one({**owner, "rev": 1, **body})
            except DuplicateKeyError as exc:
                raise RevisionConflict(
                    "Reading position changed concurrently."
                ) from exc
        else:
            result = self._reading_positions.update_one(
                {**owner, "rev": expected_rev},
                {"$set": body, "$inc": {"rev": 1}},
            )
            if result.matched_count == 0:
                raise RevisionConflict("Reading position changed concurrently.")
        return body

    # -- publication ---------------------------------------------------------

    def find_publication(self, book: str) -> dict | None:
        try:
            return self._publications.get({"book": book}, ManuscriptNotFound)
        except ManuscriptNotFound:
            return None

    def create_publication(self, book: str, body: dict, author: str) -> dict:
        return self._publications.create({"book": book}, body, author, AlreadyExists)

    def update_publication(
        self, book: str, body: dict, expected_rev: int, author: str
    ) -> dict:
        return self._publications.update(
            {"book": book}, body, expected_rev, author, ManuscriptNotFound
        )

    def get_publication_cover(self, book: str) -> dict | None:
        return self._publication_covers.find_one({"_id": book})

    def has_publication_cover(self, book: str) -> bool:
        return self._publication_covers.find_one({"_id": book}, {"_id": 1}) is not None

    def set_publication_cover(self, book: str, data: bytes, mime: str) -> None:
        self._publication_covers.update_one(
            {"_id": book},
            {"$set": {"data": data, "mime": mime, "updated_at": self._now()}},
            upsert=True,
        )

    def delete_publication_cover(self, book: str) -> None:
        self._publication_covers.delete_one({"_id": book})

    # -- export jobs -----------------------------------------------------------

    def create_export_job(self, book: str, owner: str, at: str) -> str:
        job = self._id_factory()
        self._export_jobs.insert_one(
            {
                "_id": job,
                "book": book,
                "owner": owner,
                "state": "running",
                "started_at": at,
            }
        )
        return job

    def find_export_job(self, book: str, owner: str, job: str) -> dict | None:
        """Scoped to its owner, so a job id is not a handle on someone's book."""
        return self._export_jobs.find_one(
            {"_id": job, "book": book, "owner": owner}
        )

    def finish_export_job(
        self, job: str, *, data: bytes | None = None, error: str | None = None
    ) -> None:
        self._export_jobs.update_one(
            {"_id": job},
            {
                "$set": {
                    "state": "ready" if error is None else "failed",
                    "data": data,
                    "error": error,
                    "finished_at": self._now(),
                }
            },
        )

    def delete_export_job(self, job: str) -> None:
        self._export_jobs.delete_one({"_id": job})

    def expire_export_jobs(self, before: str) -> None:
        """Sweep jobs whose worker died mid-render, and downloads never claimed."""
        self._export_jobs.delete_many({"started_at": {"$lt": before}})

    # -- search projection, maintained on the write path ----------------------

    def reindex_search(self, book: str, rows: list[dict]) -> None:
        """Replace one book's search rows with ``rows``.

        Rows are stamped with a generation and the previous generation is swept
        afterwards, so a reader searching mid-reindex sees the old row or the new
        one but never a gap. Callers pass a snapshot taken *after* their write,
        which is what makes the last writer the winner.
        """
        generation = self._id_factory()
        for row in rows:
            self._search_blocks.replace_one(
                {"book": book, "volume": row["volume"], "section": row["section"]},
                {"book": book, "generation": generation, **row},
                upsert=True,
            )
        self._search_blocks.delete_many(
            {"book": book, "generation": {"$ne": generation}}
        )

    def search_sections(
        self, book: str, terms: list[str], *, offset: int, limit: int
    ) -> tuple[list[dict], int]:
        """One page of matching sections in reading order, and the total."""
        query: dict = {"book": book}
        if terms:
            query["$and"] = [
                {"haystack": {"$regex": re.escape(term), "$options": "i"}}
                for term in terms
            ]
        total = self._search_blocks.count_documents(query)
        page = self._search_blocks.find(query).sort("order", 1).skip(offset).limit(limit)
        return list(page), total

    def has_search_rows(self, book: str) -> bool:
        return self._search_blocks.find_one({"book": book}, {"_id": 1}) is not None

    # -- questions the other services ask -------------------------------------

    def has_content(self, book: str) -> bool:
        return bool(
            self.find_outline(book)
            or self._volumes.count({"book": book})
            or self._sections.count({"book": book})
        )

    def sections_referencing(self, book: str, event: str) -> list[dict]:
        return [
            row
            for row in self.list_sections(book)
            if event in row.get("event_ids", [])
        ]

    def purge_book(self, book: str) -> None:
        """Permanently remove a manuscript, retained history included.

        The only hard delete Logos offers, and it is reachable only through the
        explicit manuscript delete that must precede removing the Chronos book.
        Heads go first: an interruption may orphan revisions, which a later purge
        collects, but can never leave a live head pointing at a missing body.
        """
        for heads_name, revisions_name in (
            (DRAFTS, DRAFT_REVISIONS),
            (SECTIONS, SECTION_REVISIONS),
            (VOLUMES, VOLUME_REVISIONS),
            (OUTLINES, OUTLINE_REVISIONS),
            (PUBLICATIONS, PUBLICATION_REVISIONS),
        ):
            heads = self._database[heads_name]
            revisions = self._database[revisions_name]
            keys = [row["_id"] for row in heads.find({"book": book}, {"_id": 1})]
            heads.delete_many({"book": book})
            if keys:
                revisions.delete_many({"resource_key": {"$in": keys}})
        self._reader_items.delete_many({"book": book})
        self._reading_positions.delete_many({"book": book})
        self._publication_covers.delete_one({"_id": book})
        self._search_blocks.delete_many({"book": book})
        self._export_jobs.delete_many({"book": book})
        self._section_moves.delete_many({"book": book})

    def purge_user(self, username: str) -> None:
        self._reader_items.delete_many({"username": username})
        self._reading_positions.delete_many({"username": username})
        self._reader_settings.delete_one({"_id": username})
        self._export_jobs.delete_many({"owner": username})

    @staticmethod
    def _volume_key(book: str, volume: str) -> dict:
        return {"book": book, "volume": volume}

    @staticmethod
    def _section_key(book: str, volume: str, section: str) -> dict:
        return {"book": book, "volume": volume, "section": section}

    @staticmethod
    def _draft_key(book: str, volume: str, section: str, draft: str) -> dict:
        return {
            "book": book,
            "volume": volume,
            "section": section,
            "draft": draft,
        }

    def _now(self) -> str:
        return self._clock().isoformat()

    @staticmethod
    def _public_reader_item(record: dict) -> dict:
        return {
            key: value
            for key, value in record.items()
            if key not in {"_id", "username"}
        } | {"id": record["_id"]}
