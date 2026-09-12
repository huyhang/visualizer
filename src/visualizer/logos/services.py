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
    InvalidOrder,
    InvalidSection,
    ManuscriptNotFound,
    PrimaryDraftConflict,
    RevisionConflict,
    RevisionNotRetained,
    SectionKindInUse,
    SectionNotFound,
    VolumeNotFound,
)
from .models import Draft, Outline, Section, Volume
from .presenters import (
    present_draft,
    present_draft_revision,
    present_manuscript,
    present_section,
    present_section_revision,
    present_volume,
    section_numbers,
)
from .richtext import article_refs, word_count
from .search import search_projection
from .validation import (
    SINGLETON_SECTION_KINDS,
    validate_draft_payload,
    validate_identifier,
    validate_new_draft,
    validate_order,
    validate_primary_draft,
    validate_section_move,
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
            row["section"]: self._with_primary_document(row)
            for row in self.store.list_sections(book, volume.id)
        }
        return [by_id[key] for key in volume.sections if key in by_id]

    def _with_primary_document(self, record: dict) -> dict:
        """Resolve the live primary while legacy section reads remain compatible."""
        draft_id = record.get("primary_draft_id")
        if not draft_id:
            return record
        draft = self.store.find_draft(
            record["book"], record["volume"], record["section"], draft_id
        )
        return {**record, "document": draft["document"]} if draft else record

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

    # -- the whole manuscript, and the cheap questions asked about it ---------

    def _publication_volumes(self, book: str) -> list[dict]:
        """Every volume with its prose, in reading order. No Chronos round trip."""
        volumes = []
        for number, record in enumerate(self._ordered_volumes(book), 1):
            sections = self._ordered_sections(book, record)
            numbers = section_numbers(sections)
            volumes.append(
                present_volume(
                    book,
                    record,
                    number,
                    [
                        present_section(
                            section,
                            numbers[section["section"]],
                            include_document=True,
                        )
                        for section in sections
                    ],
                )
            )
        return volumes

    def _reading_order(self, book: str) -> list[tuple[str, str]]:
        """Ordered ``(volume, section)`` pairs, read from ordering records only.

        The outline names the volumes, each volume names its sections, and the
        section heads say which of those are still live -- none of which needs a
        section's document. Callers that only have to place a mark in the book
        use this instead of assembling every chapter.
        """
        live = self.store.section_ids(book)
        return [
            (record["volume"], section)
            for record in self._ordered_volumes(book)
            for section in Volume.from_storage(record).sections
            if (record["volume"], section) in live
        ]

    def _reindex_search(self, book: str) -> None:
        """Refresh the search projection from the manuscript as it now stands.

        Called after every write that changes what search can match or how a hit
        is labelled -- prose, titles and ordering all appear in a result row.
        Reads never call this: see the note in ``store.py``.
        """
        outline = self.store.find_outline(book)
        rows = [] if outline is None else search_projection(
            self._publication_volumes(book)
        )
        self.store.reindex_search(book, rows)

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
        result = present_manuscript(book, chronos_book, volumes, outline)
        result["section_aliases"] = self.store.list_section_moves(book)
        result["pending_section_moves"] = self.store.list_pending_section_moves(book)
        return result

    def publication(self, book: str) -> dict:
        """The whole current manuscript, including prose, in reading order.

        This loads every section's document, so only ask for it when the prose
        itself is the point -- an export, or resolving a note's excerpt. To check
        that a book exists use :meth:`require`; to place a mark within it use
        :meth:`reading_order`.
        """
        chronos_book = self._book(book)
        outline = self._require_outline(book)
        return present_manuscript(
            book, chronos_book, self._publication_volumes(book), outline
        )

    def require(self, book: str) -> dict:
        """The Chronos book, or raise. Two indexed lookups and no prose.

        This is the existence check every reader-layer write wants; assembling
        the manuscript to answer it made each keystroke-rate position save read
        the whole series.
        """
        chronos_book = self._book(book)
        self._require_outline(book)
        return chronos_book

    # Quoted: this class defines `list`, which shadows the builtin in the class
    # body, so an unquoted `list[...]` annotation is evaluated against the method.
    def reading_order(self, book: str) -> "list[tuple[str, str]]":
        """Ordered ``(volume, section)`` pairs. Ordering records only."""
        self.require(book)
        return self._reading_order(book)

    def report(self, book: str) -> dict:
        """Progress across a whole book, and every reference that no longer lands."""
        self._book(book)
        volumes = self._ordered_volumes(book)
        sections = [
            self._with_primary_document(row) for row in self.store.list_sections(book)
        ]
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
        self._reindex_search(book)
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

    def scenes(self, book: str, volume_id: str) -> dict:
        """The Chronos scenes each section of this volume says it realises.

        The ids come from the sections themselves, never from the caller, so
        there is no parameter through which a client could widen the result.
        """
        self._book(book)
        records = self._ordered_sections(book, self._require_volume(book, volume_id))
        cards = self._scene_cards(book, records)
        return {
            "book": book,
            "volume": volume_id,
            "sections": [
                {
                    "section": record["section"],
                    "scenes": [cards[event] for event in record.get("event_ids", [])],
                }
                for record in records
            ],
        }

    def _scene_cards(self, book: str, records: list[dict]) -> dict[str, dict]:
        """One gateway round trip for every scene the whole volume names."""
        wanted = [
            event for record in records for event in record.get("event_ids", [])
        ]
        return {card["id"]: card for card in self.chronos.scene_cards(book, wanted)}

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
        # The volume title is part of every search row this volume owns.
        self._reindex_search(book)
        return self._volume_view(book, updated)

    def delete(
        self, book: str, volume_id: str, expected_rev: int, author: str, cascade: bool
    ) -> None:
        self._book(book)
        record = self._require_volume(book, volume_id)
        self._check_rev(record, expected_rev)
        if self.store.has_pending_section_moves(book, volume_id):
            raise RevisionConflict(
                "This volume is part of an unfinished section move. "
                "Finish that move before deleting the volume."
            )
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
            for draft in self.store.list_drafts(
                book, volume_id, section["section"]
            ):
                self.store.delete_draft(
                    book,
                    volume_id,
                    section["section"],
                    draft["draft"],
                    draft["rev"],
                    author,
                )
            self.store.delete_section(
                book, volume_id, section["section"], section["rev"], author
            )
        self.store.delete_volume(book, volume_id, expected_rev, author)
        self._forget_in_outline(book, volume_id, author)
        self._reindex_search(book)

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
        # Reading order decides both the volume number on a hit and the order
        # results come back in.
        self._reindex_search(book)
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
        pending = self.store.find_section_move(book, volume_id, section_id)
        if pending is not None and pending.get("state") == "moving":
            raise AlreadyExists(
                f"Section '{section_id}' is being moved out of volume "
                f"'{volume_id}'. Finish that move before reusing the name."
            )
        # A *completed* move only left an alias here, and an alias never
        # outranks a real section. Reusing the name retires it.
        self.store.release_section_move(book, volume_id, section_id)
        primary = "draft-1"
        section = replace(section, primary_draft_id=primary)
        self._place_in_volume(book, volume_record, section_id, author)
        if self.store.find_draft(book, volume_id, section_id, primary) is None:
            self.store.create_draft(
                book,
                volume_id,
                section_id,
                primary,
                Draft(primary, "Draft 1", section.document).to_storage(),
                author,
            )
        record = self.store.create_section(
            book, volume_id, section_id, section.to_storage(), author
        )
        self._reindex_search(book)
        return self._present_one(book, volume_id, record)

    def _place_in_volume(
        self, book: str, volume_record: dict, section_id: str, author: str
    ) -> None:
        """Append a new section to its volume -- an insert with no anchor."""
        self._insert_into_volume(
            book, volume_record["volume"], section_id, None, author
        )

    def get(self, book: str, volume_id: str, section_id: str) -> dict:
        self._book(book)
        self._require_volume(book, volume_id)
        record = self._with_primary_document(
            self._require_section(book, volume_id, section_id)
        )
        return self._present_one(book, volume_id, record)

    def scenes(self, book: str, volume_id: str, section_id: str) -> dict:
        """Only the Chronos scenes named by the section the reader opened."""
        self._book(book)
        self._require_volume(book, volume_id)
        record = self._require_section(book, volume_id, section_id)
        wanted = list(record.get("event_ids", []))
        cards = {
            card["id"]: card for card in self.chronos.scene_cards(book, wanted)
        }
        return {
            "book": book,
            "volume": volume_id,
            "section": section_id,
            "scenes": [cards[event] for event in wanted],
        }

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
        current = self._require_section(book, volume_id, section_id)
        section = validate_section_payload(section_id, payload)
        section = replace(
            section,
            primary_draft_id=current.get("primary_draft_id") or "draft-1",
        )
        self._check_kind(book, volume_record, section, ignore=section_id)
        self._check_events(book, section.event_ids)
        record = self.store.update_section(
            book, volume_id, section_id, section.to_storage(), expected_rev, author
        )
        primary = section.primary_draft_id
        draft = self.store.find_draft(book, volume_id, section_id, primary)
        if draft is None:
            self.store.create_draft(
                book,
                volume_id,
                section_id,
                primary,
                Draft(primary, "Draft 1", section.document).to_storage(),
                author,
            )
        elif draft["document"] != section.document:
            self.store.update_draft(
                book,
                volume_id,
                section_id,
                primary,
                Draft(primary, draft["name"], section.document).to_storage(),
                draft["rev"],
                author,
            )
        self._reindex_search(book)
        return self._present_one(book, volume_id, record)

    def update_metadata(
        self,
        book: str,
        volume_id: str,
        section_id: str,
        payload,
        expected_rev: int,
        author: str,
    ) -> dict:
        """Edit chapter metadata without touching any draft document."""
        self._book(book)
        volume_record = self._require_volume(book, volume_id)
        current = self._require_section(book, volume_id, section_id)
        if not isinstance(payload, dict):
            raise InvalidSection("A section metadata body must be a JSON object.")
        unexpected = sorted(set(payload) - {"title", "overview", "event_ids"})
        if unexpected:
            raise InvalidSection(
                "A section metadata body contains unsupported fields.",
                evidence={"unexpected": unexpected},
            )
        body = {
            "kind": current["kind"],
            "title": payload.get("title", current.get("title")),
            "overview": payload.get("overview", current.get("overview", "")),
            "event_ids": payload.get("event_ids", current.get("event_ids", [])),
            "document": current["document"],
        }
        incoming = validate_section_payload(section_id, body)
        incoming = replace(
            incoming,
            primary_draft_id=current.get("primary_draft_id") or "draft-1",
        )
        self._check_kind(book, volume_record, incoming, ignore=section_id)
        self._check_events(book, incoming.event_ids)
        record = self.store.update_section(
            book,
            volume_id,
            section_id,
            incoming.to_storage(),
            expected_rev,
            author,
        )
        self._reindex_search(book)
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
        for draft in self.store.list_drafts(book, volume_id, section_id):
            self.store.delete_draft(
                book,
                volume_id,
                section_id,
                draft["draft"],
                draft["rev"],
                author,
            )
        self.store.delete_section(book, volume_id, section_id, expected_rev, author)
        volume = Volume.from_storage(volume_record)
        if section_id in volume.sections:
            volume.sections.remove(section_id)
            self.store.update_volume(
                book, volume_id, volume.to_storage(), volume_record["rev"], author
            )
        self._reindex_search(book)

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
        # Section order renumbers chapters, and the number is in the hit label.
        self._reindex_search(book)
        return self._volume_view(book, updated)

    def move(
        self,
        book: str,
        source_volume: str,
        section_id: str,
        payload,
        expected_rev: int,
        author: str,
    ) -> dict:
        """Move a section and its complete versioned bundle to another volume."""
        self._book(book)
        target_volume, before = validate_section_move(payload)
        if target_volume == source_volume:
            raise InvalidOrder(
                "Use section ordering to move a section within its current volume."
            )
        pending = self._move_intent(
            book,
            source_volume,
            target_volume,
            section_id,
            before,
            expected_rev,
            author,
        )

        if pending.get("state") == "complete":
            return ManuscriptService(self.store, self.chronos, self.articles).get(book)

        self._relocate_bundle(
            book,
            source_volume,
            target_volume,
            section_id,
            pending["section_rev"],
            author,
        )
        target_record = self._require_volume(book, target_volume)
        moved_section = self.store.get_section(book, target_volume, section_id)
        self._check_kind(
            book,
            target_record,
            Section.from_storage(moved_section),
            ignore=section_id,
        )
        self._remove_from_volume(book, source_volume, section_id, author)
        self._insert_into_volume(
            book, target_volume, section_id, pending.get("before"), author
        )
        self.store.move_reader_locations(
            book, source_volume, target_volume, section_id
        )
        self._reindex_search(book)
        self.store.complete_section_move(
            book, source_volume, section_id, target_volume
        )
        return ManuscriptService(self.store, self.chronos, self.articles).get(book)

    def _move_intent(
        self,
        book: str,
        source_volume: str,
        target_volume: str,
        section_id: str,
        before: str | None,
        expected_rev: int,
        author: str,
    ) -> dict:
        pending = self.store.find_section_move(book, source_volume, section_id)
        source = (
            self.store.find_section(book, source_volume, section_id)
            if pending is not None and pending.get("state") == "complete"
            else None
        )
        if pending is None or source is not None:
            pending = self._begin_move(
                book, source_volume, target_volume, section_id, before,
                expected_rev, author, source, restart=pending is not None,
            )
        else:
            # Resuming: the checks ran when the move began, but the anchor is a
            # live section and may have gone in the meantime.
            self._check_anchor(
                book,
                self._require_volume(book, target_volume),
                pending.get("before"),
            )
        if (
            pending["target_volume"] != target_volume
            or pending.get("before") != before
        ):
            raise RevisionConflict(
                "That section has already been moved; reload the manuscript."
            )
        return pending

    def _begin_move(
        self,
        book: str,
        source_volume: str,
        target_volume: str,
        section_id: str,
        before: str | None,
        expected_rev: int,
        author: str,
        source: dict | None,
        *,
        restart: bool,
    ) -> dict:
        """Check everything, then record the intent that makes the move resumable."""
        source = source or self._require_section(book, source_volume, section_id)
        self._check_rev(source, expected_rev)
        self._require_volume(book, source_volume)
        target_record = self._require_volume(book, target_volume)
        self._check_destination_free(
            book, source_volume, target_record, section_id
        )
        self._check_anchor(book, target_record, before)
        self._check_kind(book, target_record, Section.from_storage(source))
        return self.store.begin_section_move(
            book,
            source_volume,
            target_volume,
            section_id,
            before,
            expected_rev,
            author,
            source.get("title"),
            source["kind"],
            restart=restart,
        )

    def _check_destination_free(
        self, book: str, source_volume: str, target_record: dict, section_id: str
    ) -> None:
        """Nothing may hold the destination -- not a section, not its history.

        The drafts checked are the ones travelling *with* the section, so their
        ids are looked up at the source and tested against the destination.
        """
        target_volume = target_record["volume"]
        if section_id in self._section_ids_of(book, target_record):
            raise AlreadyExists(
                f"Volume '{target_volume}' already has a section named "
                f"'{section_id}'."
            )
        travelling = self.store.list_drafts(book, source_volume, section_id)
        taken = self.store.section_identity_exists(
            book, target_volume, section_id
        ) or any(
            self.store.draft_identity_exists(
                book, target_volume, section_id, draft["draft"]
            )
            for draft in travelling
        )
        if taken:
            raise AlreadyExists(
                "That section location is retained by deleted history; "
                "choose a different section id."
            )

    def _check_anchor(
        self, book: str, target_record: dict, before: str | None
    ) -> None:
        """The section a move inserts in front of must still be in the volume."""
        if before is None:
            return
        if before not in self._section_ids_of(book, target_record):
            raise InvalidOrder(
                f"The insertion point '{before}' is not in volume "
                f"'{target_record['volume']}'."
            )

    def _section_ids_of(self, book: str, volume_record: dict) -> list[str]:
        return [
            row["section"] for row in self._ordered_sections(book, volume_record)
        ]

    def _relocate_bundle(
        self,
        book: str,
        source_volume: str,
        target_volume: str,
        section_id: str,
        expected_rev: int,
        author: str,
    ) -> None:
        # Moving the section first prevents any new draft save through its old
        # path. Drafts can then move at their current revisions without a race.
        #
        # The section keeps its revision across the move: filing a chapter is
        # not editing it, so it neither shows up as an edit in the version list
        # nor evicts a real one. See ``VersionedDocuments.relocate``.
        self.store.relocate_section(
            book,
            source_volume,
            target_volume,
            section_id,
            expected_rev,
            author,
        )
        for draft in self.store.list_drafts(book, source_volume, section_id):
            self.store.relocate_draft(
                book,
                source_volume,
                target_volume,
                section_id,
                draft["draft"],
                draft["rev"],
                author,
            )

    def _remove_from_volume(
        self, book: str, volume_id: str, section_id: str, author: str
    ) -> None:
        def remove(volume: Volume) -> Volume:
            return replace(
                volume,
                sections=[item for item in volume.sections if item != section_id],
            )

        self._patch_volume(book, volume_id, remove, author)

    def _insert_into_volume(
        self,
        book: str,
        volume_id: str,
        section_id: str,
        before: str | None,
        author: str,
    ) -> None:
        def insert(volume: Volume) -> Volume:
            if section_id in volume.sections:
                return volume
            sections = list(volume.sections)
            at = sections.index(before) if before in sections else len(sections)
            sections.insert(at, section_id)
            return replace(volume, sections=sections)

        self._patch_volume(book, volume_id, insert, author)

    def _patch_volume(self, book: str, volume_id: str, change, author: str) -> None:
        for _attempt in range(3):
            record = self._require_volume(book, volume_id)
            current = Volume.from_storage(record)
            updated = change(current)
            if updated.sections == current.sections:
                return
            try:
                self.store.update_volume(
                    book, volume_id, updated.to_storage(), record["rev"], author
                )
                return
            except RevisionConflict:
                continue
        raise RevisionConflict("The volume order kept changing; retry the move.")

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
        current = self._require_section(book, volume_id, section_id)
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
            book,
            volume_id,
            section_id,
            revision,
            expected_rev,
            author,
            current.get("primary_draft_id") or "draft-1",
        )
        primary = record.get("primary_draft_id") or "draft-1"
        draft = self.store.find_draft(book, volume_id, section_id, primary)
        if draft is None:
            self.store.create_draft(
                book,
                volume_id,
                section_id,
                primary,
                Draft(primary, "Draft 1", record["document"]).to_storage(),
                author,
            )
        elif draft["document"] != record["document"]:
            self.store.update_draft(
                book,
                volume_id,
                section_id,
                primary,
                Draft(primary, draft["name"], record["document"]).to_storage(),
                draft["rev"],
                author,
            )
        self._reindex_search(book)
        return self._present_one(book, volume_id, record)

    # -- guards ---------------------------------------------------------------

    def _present_one(self, book: str, volume_id: str, record: dict) -> dict:
        record = self._with_primary_document(record)
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


class DraftService(_Service):
    """Named, versioned alternatives beneath a section.

    The section keeps a materialized copy of the primary document. That leaves
    the established reader and publication API unchanged while draft identity
    and history live independently here.
    """

    DEFAULT_ID = "draft-1"

    def _section(self, book: str, volume: str, section: str) -> dict:
        self._book(book)
        self._require_volume(book, volume)
        return self._require_section(book, volume, section)

    @staticmethod
    def _primary(record: dict) -> str:
        return record.get("primary_draft_id") or DraftService.DEFAULT_ID

    def _materialize(self, book: str, volume: str, section: str, author: str) -> None:
        """Create the initial draft for a manuscript written before drafts existed."""
        if self.store.list_drafts(book, volume, section):
            return
        current = self._section(book, volume, section)
        draft_id = self._primary(current)
        self.store.create_draft(
            book,
            volume,
            section,
            draft_id,
            Draft(draft_id, "Draft 1", current["document"]).to_storage(),
            author,
        )

    def list(
        self, book: str, volume: str, section: str, author: str
    ) -> dict:
        current = self._section(book, volume, section)
        self._materialize(book, volume, section, author)
        primary = self._primary(current)
        rows = sorted(
            self.store.list_drafts(book, volume, section),
            key=lambda row: (row["name"].lower(), row["draft"]),
        )
        return {
            "book": book,
            "volume": volume,
            "section": section,
            "primary_draft_id": primary,
            "section_rev": current["rev"],
            "drafts": [
                present_draft(row, primary, include_document=False) for row in rows
            ],
        }

    def get(
        self, book: str, volume: str, section: str, draft: str, author: str
    ) -> dict:
        current = self._section(book, volume, section)
        self._materialize(book, volume, section, author)
        validate_identifier(draft, "draft")
        return present_draft(
            self.store.get_draft(book, volume, section, draft),
            self._primary(current),
        )

    def create(
        self, book: str, volume: str, section: str, payload, author: str
    ) -> dict:
        current = self._section(book, volume, section)
        self._materialize(book, volume, section, author)
        name, source_id = validate_new_draft(payload)
        source_id = source_id or self._primary(current)
        source = self.store.get_draft(book, volume, section, source_id)
        draft_id = self.store.new_draft_id()
        record = self.store.create_draft(
            book,
            volume,
            section,
            draft_id,
            Draft(draft_id, name, source["document"]).to_storage(),
            author,
        )
        return present_draft(record, self._primary(current))

    def update(
        self,
        book: str,
        volume: str,
        section: str,
        draft: str,
        payload,
        expected_rev: int,
        author: str,
    ) -> dict:
        current = self._section(book, volume, section)
        self._materialize(book, volume, section, author)
        incoming = validate_draft_payload(draft, payload)
        updated = self.store.update_draft(
            book,
            volume,
            section,
            draft,
            incoming.to_storage(),
            expected_rev,
            author,
        )
        section_rev = current["rev"]
        if draft == self._primary(current):
            refreshed = self._require_section(book, volume, section)
            primary_section = replace(
                Section.from_storage(refreshed), document=incoming.document
            )
            projected = self.store.update_section(
                book,
                volume,
                section,
                primary_section.to_storage(),
                refreshed["rev"],
                author,
            )
            section_rev = projected["rev"]
            self._reindex_search(book)
        return {
            **present_draft(updated, self._primary(current)),
            "section_rev": section_rev,
        }

    def make_primary(
        self,
        book: str,
        volume: str,
        section: str,
        payload,
        expected_rev: int,
        author: str,
    ) -> dict:
        current = self._section(book, volume, section)
        self._check_rev(current, expected_rev)
        self._materialize(book, volume, section, author)
        draft_id = validate_primary_draft(payload)
        draft = self.store.get_draft(book, volume, section, draft_id)
        updated_section = replace(
            Section.from_storage(current),
            document=draft["document"],
            primary_draft_id=draft_id,
        )
        stored = self.store.update_section(
            book,
            volume,
            section,
            updated_section.to_storage(),
            expected_rev,
            author,
        )
        self._reindex_search(book)
        return {
            "book": book,
            "volume": volume,
            "section": section,
            "primary_draft_id": draft_id,
            "section_rev": stored["rev"],
        }

    def delete(
        self,
        book: str,
        volume: str,
        section: str,
        draft: str,
        expected_rev: int,
        author: str,
    ) -> None:
        current = self._section(book, volume, section)
        self._materialize(book, volume, section, author)
        if draft == self._primary(current):
            raise PrimaryDraftConflict(
                "Choose another primary draft before deleting this one."
            )
        self.store.delete_draft(
            book, volume, section, draft, expected_rev, author
        )

    def history(
        self, book: str, volume: str, section: str, draft: str, author: str
    ) -> dict:
        self._section(book, volume, section)
        self._materialize(book, volume, section, author)
        validate_identifier(draft, "draft")
        return {
            "book": book,
            "volume": volume,
            "section": section,
            "draft": draft,
            "versions": self.store.draft_history(book, volume, section, draft),
        }

    def revision(
        self,
        book: str,
        volume: str,
        section: str,
        draft: str,
        revision: int,
        author: str,
    ) -> dict:
        self._section(book, volume, section)
        self._materialize(book, volume, section, author)
        return present_draft_revision(
            self.store.draft_revision(book, volume, section, draft, revision)
        )

    def restore(
        self,
        book: str,
        volume: str,
        section: str,
        draft: str,
        revision: int,
        expected_rev: int,
        author: str,
    ) -> dict:
        current_section = self._section(book, volume, section)
        self._materialize(book, volume, section, author)
        target = self.store.draft_revision(
            book, volume, section, draft, revision
        )
        if target["deleted"]:
            raise RevisionNotRetained(
                f"Revision {revision} is a deletion and has no document."
            )
        restored = validate_draft_payload(
            draft, {"name": target["name"], "document": target["document"]}
        )
        record = self.store.restore_draft(
            book, volume, section, draft, revision, expected_rev, author
        )
        section_rev = current_section["rev"]
        if draft == self._primary(current_section):
            refreshed = self._require_section(book, volume, section)
            projected = replace(
                Section.from_storage(refreshed), document=restored.document
            )
            stored = self.store.update_section(
                book,
                volume,
                section,
                projected.to_storage(),
                refreshed["rev"],
                author,
            )
            section_rev = stored["rev"]
            self._reindex_search(book)
        return {
            **present_draft(record, self._primary(current_section)),
            "section_rev": section_rev,
        }
