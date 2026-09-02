"""MongoDB persistence for Logos outlines, volumes and versioned sections.

All three sit on the shared ``VersionedDocuments`` engine in a reserved
``_logos`` database. Sections get real retained history because prose is the one
thing here nobody can reconstruct; the outline and volume records hold only
ordering and a title, so one revision of each is enough to give them the same
optimistic-concurrency guarantees without paying for history nobody would read.

``find_*`` answers "is this here?" with ``None`` rather than an exception, so the
services can ask without using exceptions for control flow. ``get_*`` raises.
"""

from collections.abc import Callable
from datetime import datetime

from visualizer.documents import VersionedDocuments

from .errors import (
    AlreadyExists,
    ManuscriptNotFound,
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

OUTLINE_IDENTITY = ("book",)
VOLUME_IDENTITY = ("book", "volume")
SECTION_IDENTITY = ("book", "volume", "section")

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
    ) -> dict:
        return self._sections.restore(
            self._section_key(book, volume, section),
            rev,
            expected_rev,
            author,
            SectionNotFound,
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
            (SECTIONS, SECTION_REVISIONS),
            (VOLUMES, VOLUME_REVISIONS),
            (OUTLINES, OUTLINE_REVISIONS),
        ):
            heads = self._database[heads_name]
            revisions = self._database[revisions_name]
            keys = [row["_id"] for row in heads.find({"book": book}, {"_id": 1})]
            heads.delete_many({"book": book})
            if keys:
                revisions.delete_many({"resource_key": {"$in": keys}})

    @staticmethod
    def _volume_key(book: str, volume: str) -> dict:
        return {"book": book, "volume": volume}

    @staticmethod
    def _section_key(book: str, volume: str, section: str) -> dict:
        return {"book": book, "volume": volume, "section": section}
