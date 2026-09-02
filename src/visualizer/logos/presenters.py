"""Pure response shaping and the counts derived from a manuscript.

Everything a caller reads about ordering, size or linkage is computed here from
the records as they stand, never read out of a stored field. That is what makes
reordering safe: there is no second copy of a number to forget to update.
"""

from .models import Section, Volume
from .richtext import blocks_of, word_count

AUDIT_FIELDS = ("rev", "created_by", "updated_by", "updated_at")


def audit(record: dict) -> dict:
    return {field: record.get(field) for field in AUDIT_FIELDS}


def empty_audit() -> dict:
    """The audit block for a manuscript that has no outline record yet."""
    return {"rev": 0, "created_by": None, "updated_by": None, "updated_at": None}


def section_numbers(records: list[dict]) -> dict[str, int | None]:
    """Chapter numbers follow chapter order; other kinds are unnumbered."""
    numbers: dict[str, int | None] = {}
    chapter = 0
    for record in records:
        if record["kind"] == "chapter":
            chapter += 1
            numbers[record["section"]] = chapter
        else:
            numbers[record["section"]] = None
    return numbers


def present_section(
    record: dict,
    number: int | None,
    missing_refs: list[dict] | None = None,
    *,
    include_document: bool = True,
) -> dict:
    section = Section.from_storage(record)
    path = section_path(record["book"], record["volume"], section.id)
    result = {
        "book": record["book"],
        "volume": record["volume"],
        "id": section.id,
        "kind": section.kind,
        "number": number,
        "title": section.title,
        "overview": section.overview,
        "event_ids": section.event_ids,
        "paragraph_count": len(blocks_of(section.document, kind="paragraph")),
        "word_count": word_count(section.document),
        "missing_refs": list(missing_refs or []),
        "_links": {"self": path, "versions": path + "/versions"},
        **audit(record),
    }
    if include_document:
        result["document"] = section.document
    return result


def present_section_revision(record: dict, number: int | None) -> dict:
    """One retained revision: its metadata, plus its prose unless it is a delete."""
    result = {
        "book": record["book"],
        "volume": record["volume"],
        "id": record["section"],
        "number": number,
        "rev": record["rev"],
        "op": record["op"],
        "author": record.get("author"),
        "timestamp": record["timestamp"],
        "deleted": record["deleted"],
    }
    if record["deleted"]:
        return result
    section = Section.from_storage(record)
    result.update(
        kind=section.kind,
        title=section.title,
        overview=section.overview,
        event_ids=section.event_ids,
        paragraph_count=len(blocks_of(section.document, kind="paragraph")),
        word_count=word_count(section.document),
        document=section.document,
    )
    return result


def present_volume(
    book: str, record: dict, number: int, sections: list[dict]
) -> dict:
    volume = Volume.from_storage(record)
    path = volume_path(book, volume.id)
    return {
        "book": book,
        "id": volume.id,
        "number": number,
        "title": volume.title,
        "overview": volume.overview,
        "sections": sections,
        "section_count": len(sections),
        "word_count": sum(section["word_count"] for section in sections),
        "_links": {
            "self": path,
            "manuscript": path + "/manuscript",
            "section_order": path + "/section-order",
        },
        **audit(record),
    }


def present_manuscript(book: str, chronos_book: dict, volumes: list[dict],
                       outline: dict | None) -> dict:
    return {
        "book": book,
        "title": chronos_book.get("title"),
        "overview": chronos_book.get("overview", ""),
        "world": chronos_book.get("world"),
        "volumes": volumes,
        "volume_count": len(volumes),
        "word_count": sum(volume["word_count"] for volume in volumes),
        "_links": {
            "self": book_path(book),
            "volume_order": book_path(book) + "/volume-order",
            "report": book_path(book) + "/report",
        },
        **(audit(outline) if outline else empty_audit()),
    }


def book_path(book: str) -> str:
    return f"/books/{book}"


def volume_path(book: str, volume: str) -> str:
    return f"{book_path(book)}/volumes/{volume}"


def section_path(book: str, volume: str, section: str) -> str:
    return f"{volume_path(book, volume)}/sections/{section}"
