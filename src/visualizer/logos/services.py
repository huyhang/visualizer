"""Application services: load, validate purely, persist, present.

**Why there is no rollback here.** Order lives in one place -- the outline lists
volumes, a volume lists its sections -- while existence is decided by the record
itself. Writes are ordered so that the only state a half-finished operation can
leave is an order entry naming a record that is not there, and every read filters
those out. A retry then completes the operation and a reorder rewrites the list
from what is actually live, so the inconsistency heals instead of needing a
compensating write that could itself fail silently.
"""

from dataclasses import replace

from .errors import (
    AlreadyExists,
    BookNotFound,
    CascadeRequired,
    ChronosEventNotFound,
    ManuscriptNotFound,
    RevisionConflict,
    RevisionNotRetained,
    SectionKindInUse,
    SectionNotFound,
    VolumeNotFound,
)
from .models import Outline, Section, Volume
from .presenters import (
    present_manuscript,
    present_section,
    present_section_revision,
    present_volume,
    section_numbers,
)
from .richtext import article_refs, word_count
from .validation import (
    SINGLETON_SECTION_KINDS,
    validate_identifier,
    validate_order,
    validate_section_payload,
    validate_volume_payload,
)


def _ref_key(ref: dict) -> tuple[str, str, str]:
    return (ref["database"], ref["collection"], ref["id"])


class _Service:
    def __init__(self, store, chronos, articles):
        self.store = store
        self.chronos = chronos
        self.articles = articles

    # -- lookups --------------------------------------------------------------

    def _book(self, book: str) -> dict:
        found = self.chronos.get_book(book)
        if found is None:
            raise BookNotFound(f"Chronos book '{book}' was not found.")
        return found

    def _outline(self, book: str) -> tuple[Outline, dict | None]:
        record = self.store.find_outline(book)
        return (Outline.from_storage(record) if record else Outline(book)), record

    def _require_outline(self, book: str) -> dict:
        record = self.store.find_outline(book)
        if record is None:
            raise ManuscriptNotFound(f"Manuscript for '{book}' was not found.")
        return record

    def _require_volume(self, book: str, volume_id: str) -> dict:
        validate_identifier(volume_id, "volume")
        record = self.store.find_volume(book, volume_id)
        if record is None:
            raise VolumeNotFound(f"Volume '{volume_id}' was not found in '{book}'.")
        return record

    def _require_section(self, book: str, volume_id: str, section_id: str) -> dict:
        validate_identifier(section_id, "section")
        record = self.store.find_section(book, volume_id, section_id)
        if record is None:
            raise SectionNotFound(
                f"Section '{section_id}' was not found in volume '{volume_id}'."
            )
        return record

    # -- ordering -------------------------------------------------------------

    def _ordered_volumes(self, book: str) -> list[dict]:
        """Live volume records in outline order; unknown ids are skipped."""
        outline, _ = self._outline(book)
        by_id = {row["volume"]: row for row in self.store.list_volumes(book)}
        return [by_id[key] for key in outline.volumes if key in by_id]

    def _ordered_sections(self, book: str, volume_record: dict) -> list[dict]:
        volume = Volume.from_storage(volume_record)
        by_id = {
            row["section"]: row
            for row in self.store.list_sections(book, volume.id)
        }
        return [by_id[key] for key in volume.sections if key in by_id]

    def _volume_number(self, book: str, volume_id: str) -> int:
        ordered = [row["volume"] for row in self._ordered_volumes(book)]
        return ordered.index(volume_id) + 1 if volume_id in ordered else 0

    def _section_number(self, book: str, volume_record: dict, section_id: str):
        records = self._ordered_sections(book, volume_record)
        return section_numbers(records).get(section_id)

    # -- presentation ---------------------------------------------------------

    def _present_sections(
        self, book: str, volume_record: dict, *, include_documents: bool
    ) -> list[dict]:
        records = self._ordered_sections(book, volume_record)
        numbers = section_numbers(records)
        refs_per_section = [article_refs(row["document"]) for row in records]
        missing = self._missing_refs(
            [ref for refs in refs_per_section for ref in refs]
        )
        return [
            present_section(
                row,
                numbers[row["section"]],
                [ref for ref in refs if _ref_key(ref) in missing],
                include_document=include_documents,
            )
            for row, refs in zip(records, refs_per_section, strict=True)
        ]

    def _volume_view(
        self, book: str, record: dict, *, include_documents: bool = False
    ) -> dict:
        return present_volume(
            book,
            record,
            self._volume_number(book, record["volume"]),
            self._present_sections(
                book, record, include_documents=include_documents
            ),
        )

    def _missing_refs(self, refs: list[dict]) -> set[tuple[str, str, str]]:
        """One gateway round trip for every reference in a view."""
        if not refs:
            return set()
        unique = {_ref_key(ref): ref for ref in refs}
        return {
            _ref_key(ref)
            for ref in self.articles.missing_articles(list(unique.values()))
        }

    # -- shared guards --------------------------------------------------------

    @staticmethod
    def _check_rev(record: dict, expected_rev: int) -> None:
        if record["rev"] != expected_rev:
            raise RevisionConflict(
                f"Modified since revision {expected_rev}; reload and retry.",
                evidence={"expected": expected_rev, "actual": record["rev"]},
            )


class ManuscriptService(_Service):
    def list(self) -> list[dict]:
        """One row per Chronos book. Two queries, whatever the shelf size."""
        outlines = self.store.outlines_by_book()
        volumes = self.store.volumes_by_book()
        rows = []
        for book in self.chronos.list_books():
            book_id = book["id"]
            outline = outlines.get(book_id)
            live = {row["volume"] for row in volumes.get(book_id, [])}
            ordered = list(outline["volumes"]) if outline else []
            rows.append(
                {
                    "book": book_id,
                    "title": book.get("title"),
                    "has_manuscript": outline is not None,
                    "volume_count": len([v for v in ordered if v in live]),
                    "_links": {"self": f"/books/{book_id}"},
                }
            )
        return rows

    def get(self, book: str) -> dict:
        chronos_book = self._book(book)
        _, outline = self._outline(book)
        volumes = [
            self._volume_view(book, record)
            for record in self._ordered_volumes(book)
        ]
        return present_manuscript(book, chronos_book, volumes, outline)

    def report(self, book: str) -> dict:
        """Progress across a whole book, and every reference that no longer lands."""
        self._book(book)
        volumes = self._ordered_volumes(book)
        sections = self.store.list_sections(book)
        by_id = {row["section"]: row for row in sections}
        missing = self._missing_refs(
            [ref for row in sections for ref in article_refs(row["document"])]
        )
        dangling = []
        totals = {"words": 0, "sections": 0}
        for volume in volumes:
            for section_id in Volume.from_storage(volume).sections:
                row = by_id.get(section_id)
                if row is None:
                    continue
                totals["sections"] += 1
                totals["words"] += word_count(row["document"])
                unresolved = [
                    ref
                    for ref in article_refs(row["document"])
                    if _ref_key(ref) in missing
                ]
                if unresolved:
                    dangling.append(
                        {
                            "volume": volume["volume"],
                            "section": section_id,
                            "missing_refs": unresolved,
                        }
                    )
        return {
            "book": book,
            "volume_count": len(volumes),
            "section_count": totals["sections"],
            "word_count": totals["words"],
            "sections_with_missing_refs": dangling,
        }

    def delete(self, book: str, expected_rev: int, author: str, cascade: bool) -> None:
        self._book(book)
        outline = self._require_outline(book)
        self._check_rev(outline, expected_rev)
        volumes = self.store.list_volumes(book)
        sections = self.store.list_sections(book)
        if (volumes or sections) and not cascade:
            raise CascadeRequired(
                "Deleting a manuscript that still holds prose requires "
                "'cascade=true'.",
                evidence={"volumes": len(volumes), "sections": len(sections)},
            )
        self.store.purge_book(book)


class VolumeService(_Service):
    def create(self, book: str, volume_id: str, payload, author: str) -> dict:
        self._book(book)
        volume = validate_volume_payload(volume_id, payload)
        if self.store.find_volume(book, volume_id) is not None:
            raise AlreadyExists(f"Volume '{volume_id}' already exists in '{book}'.")
        self._place_in_outline(book, volume_id, author)
        record = self.store.create_volume(book, volume_id, volume.to_storage(), author)
        return self._volume_view(book, record)

    def _place_in_outline(self, book: str, volume_id: str, author: str) -> None:
        """Name the volume in the order before its record exists.

        A crash between the two leaves an order entry pointing at nothing, which
        every read skips and a retry of this same call completes.
        """
        outline, record = self._outline(book)
        if record is None:
            outline.volumes.append(volume_id)
            self.store.create_outline(book, outline.to_storage(), author)
            return
        if volume_id not in outline.volumes:
            outline.volumes.append(volume_id)
            self.store.update_outline(
                book, outline.to_storage(), record["rev"], author
            )

    def get(self, book: str, volume_id: str) -> dict:
        self._book(book)
        return self._volume_view(book, self._require_volume(book, volume_id))

    def manuscript(self, book: str, volume_id: str) -> dict:
        self._book(book)
        return self._volume_view(
            book, self._require_volume(book, volume_id), include_documents=True
        )

    def update(
        self, book: str, volume_id: str, payload, expected_rev: int, author: str
    ) -> dict:
        self._book(book)
        current = self._require_volume(book, volume_id)
        incoming = validate_volume_payload(volume_id, payload)
        # Section order belongs to the volume, not to the caller's body: a title
        # edit must not be able to rearrange or drop prose.
        held = Volume.from_storage(current)
        incoming = replace(incoming, sections=held.sections)
        updated = self.store.update_volume(
            book, volume_id, incoming.to_storage(), expected_rev, author
        )
        return self._volume_view(book, updated)

    def delete(
        self, book: str, volume_id: str, expected_rev: int, author: str, cascade: bool
    ) -> None:
        self._book(book)
        record = self._require_volume(book, volume_id)
        self._check_rev(record, expected_rev)
        sections = self.store.list_sections(book, volume_id)
        if sections and not cascade:
            raise CascadeRequired(
                "Deleting a volume that still holds sections requires "
                "'cascade=true'.",
                evidence={"sections": len(sections)},
            )
        # Prose first, then the volume, then its place in the order. Stopping
        # part-way always leaves the volume reachable so the delete can be retried.
        for section in sections:
            self.store.delete_section(
                book, volume_id, section["section"], section["rev"], author
            )
        self.store.delete_volume(book, volume_id, expected_rev, author)
        self._forget_in_outline(book, volume_id, author)

    def _forget_in_outline(self, book: str, volume_id: str, author: str) -> None:
        outline, record = self._outline(book)
        if record is None or volume_id not in outline.volumes:
            return
        outline.volumes.remove(volume_id)
        self.store.update_outline(book, outline.to_storage(), record["rev"], author)

    def reorder(self, book: str, payload, expected_rev: int, author: str) -> dict:
        self._book(book)
        self._require_outline(book)
        live = [row["volume"] for row in self._ordered_volumes(book)]
        outline = Outline(book, validate_order(payload, "volumes", live))
        self.store.update_outline(book, outline.to_storage(), expected_rev, author)
        return ManuscriptService(self.store, self.chronos, self.articles).get(book)


class SectionService(_Service):
    def create(
        self, book: str, volume_id: str, section_id: str, payload, author: str
    ) -> dict:
        self._book(book)
        volume_record = self._require_volume(book, volume_id)
        section = validate_section_payload(section_id, payload)
        self._check_kind(book, volume_record, section)
        self._check_events(book, section.event_ids)
        if self.store.find_section(book, volume_id, section_id) is not None:
            raise AlreadyExists(
                f"Section '{section_id}' already exists in volume '{volume_id}'."
            )
        self._place_in_volume(book, volume_record, section_id, author)
        record = self.store.create_section(
            book, volume_id, section_id, section.to_storage(), author
        )
        return self._present_one(book, volume_id, record)

    def _place_in_volume(
        self, book: str, volume_record: dict, section_id: str, author: str
    ) -> None:
        volume = Volume.from_storage(volume_record)
        if section_id in volume.sections:
            return
        volume.sections.append(section_id)
        self.store.update_volume(
            book, volume.id, volume.to_storage(), volume_record["rev"], author
        )

    def get(self, book: str, volume_id: str, section_id: str) -> dict:
        self._book(book)
        self._require_volume(book, volume_id)
        record = self._require_section(book, volume_id, section_id)
        return self._present_one(book, volume_id, record)

    def update(
        self,
        book: str,
        volume_id: str,
        section_id: str,
        payload,
        expected_rev: int,
        author: str,
    ) -> dict:
        self._book(book)
        volume_record = self._require_volume(book, volume_id)
        self._require_section(book, volume_id, section_id)
        section = validate_section_payload(section_id, payload)
        self._check_kind(book, volume_record, section, ignore=section_id)
        self._check_events(book, section.event_ids)
        record = self.store.update_section(
            book, volume_id, section_id, section.to_storage(), expected_rev, author
        )
        return self._present_one(book, volume_id, record)

    def delete(
        self,
        book: str,
        volume_id: str,
        section_id: str,
        expected_rev: int,
        author: str,
    ) -> None:
        self._book(book)
        volume_record = self._require_volume(book, volume_id)
        record = self._require_section(book, volume_id, section_id)
        self._check_rev(record, expected_rev)
        self.store.delete_section(book, volume_id, section_id, expected_rev, author)
        volume = Volume.from_storage(volume_record)
        if section_id in volume.sections:
            volume.sections.remove(section_id)
            self.store.update_volume(
                book, volume_id, volume.to_storage(), volume_record["rev"], author
            )

    def reorder(
        self, book: str, volume_id: str, payload, expected_rev: int, author: str
    ) -> dict:
        self._book(book)
        record = self._require_volume(book, volume_id)
        live = [row["section"] for row in self._ordered_sections(book, record)]
        volume = replace(
            Volume.from_storage(record),
            sections=validate_order(payload, "sections", live),
        )
        updated = self.store.update_volume(
            book, volume_id, volume.to_storage(), expected_rev, author
        )
        return self._volume_view(book, updated)

    def history(self, book: str, volume_id: str, section_id: str) -> dict:
        self._book(book)
        self._require_volume(book, volume_id)
        self._require_section(book, volume_id, section_id)
        return {
            "book": book,
            "volume": volume_id,
            "section": section_id,
            "versions": self.store.section_history(book, volume_id, section_id),
        }

    def revision(
        self, book: str, volume_id: str, section_id: str, revision: int
    ) -> dict:
        self._book(book)
        volume_record = self._require_volume(book, volume_id)
        self._require_section(book, volume_id, section_id)
        record = self.store.section_revision(book, volume_id, section_id, revision)
        return present_section_revision(
            record, self._section_number(book, volume_record, section_id)
        )

    def restore(
        self,
        book: str,
        volume_id: str,
        section_id: str,
        revision: int,
        expected_rev: int,
        author: str,
    ) -> dict:
        self._book(book)
        volume_record = self._require_volume(book, volume_id)
        self._require_section(book, volume_id, section_id)
        target = self.store.section_revision(book, volume_id, section_id, revision)
        if target["deleted"]:
            raise RevisionNotRetained(
                f"Revision {revision} is a deletion and has no document."
            )
        # An old revision is revalidated, not trusted: the events it names may
        # have been deleted from Chronos since it was written.
        section = validate_section_payload(
            section_id,
            {key: target.get(key) for key in
             ("kind", "title", "overview", "event_ids", "document")},
        )
        self._check_kind(book, volume_record, section, ignore=section_id)
        self._check_events(book, section.event_ids)
        record = self.store.restore_section(
            book, volume_id, section_id, revision, expected_rev, author
        )
        return self._present_one(book, volume_id, record)

    # -- guards ---------------------------------------------------------------

    def _present_one(self, book: str, volume_id: str, record: dict) -> dict:
        volume_record = self.store.get_volume(book, volume_id)
        missing = self._missing_refs(article_refs(record["document"]))
        return present_section(
            record,
            self._section_number(book, volume_record, record["section"]),
            [
                ref
                for ref in article_refs(record["document"])
                if _ref_key(ref) in missing
            ],
        )

    def _check_events(self, book: str, event_ids: list[str]) -> None:
        missing = self.chronos.missing_events(book, event_ids)
        if missing:
            raise ChronosEventNotFound(
                "One or more referenced Chronos events do not exist in this book.",
                evidence={"events": missing},
            )

    def _check_kind(
        self,
        book: str,
        volume_record: dict,
        section: Section,
        *,
        ignore: str | None = None,
    ) -> None:
        if section.kind not in SINGLETON_SECTION_KINDS:
            return
        for sibling in self._ordered_sections(book, volume_record):
            if sibling["section"] != ignore and sibling["kind"] == section.kind:
                raise SectionKindInUse(
                    f"Volume '{volume_record['volume']}' already has a "
                    f"{section.kind}.",
                    evidence={"kind": section.kind, "section": sibling["section"]},
                )
