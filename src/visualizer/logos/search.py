"""Book-wide search over the projection the write path keeps up to date.

Searching is a pure read. It matches and pages inside the database and never
touches the manuscript records, so a reader with nothing but ``read`` causes no
writes and cannot perturb what another reader sees. ``services.py`` refreshes
the projection after each manuscript write; ``search_projection`` below is the
one place that decides what a row contains.
"""

import re
from typing import Any

from .errors import InvalidSearch
from .presenters import section_numbers
from .richtext import block_text

MAX_QUERY_LENGTH = 200
MAX_RESULTS = 50


class SearchService:
    def __init__(self, store, manuscripts):
        self.store = store
        self.manuscripts = manuscripts

    def search(
        self, book: str, query: Any, *, offset: Any = 0, limit: Any = 20
    ) -> dict:
        wanted = validate_query(query)
        start = _whole_number(offset, "offset", minimum=0, maximum=1_000_000)
        size = _whole_number(limit, "limit", minimum=1, maximum=MAX_RESULTS)
        self.manuscripts.require(book)
        rows, total = self.store.search_sections(
            book, wanted, offset=start, limit=size
        )
        next_offset = start + len(rows)
        return {
            "book": book,
            "query": query.strip(),
            "results": [_result(row, wanted) for row in rows],
            "total": total,
            "next_offset": next_offset if next_offset < total else None,
        }


def validate_query(value: Any) -> list[str]:
    if not isinstance(value, str) or not value.strip():
        raise InvalidSearch("Search query 'q' must not be empty.")
    query = value.strip()
    if len(query) > MAX_QUERY_LENGTH:
        raise InvalidSearch(
            f"Search query 'q' must be at most {MAX_QUERY_LENGTH} characters."
        )
    return [term.casefold() for term in query.split()]


def search_projection(volumes: list[dict]) -> list[dict]:
    """One row per section: what search matches on, and what a hit displays."""
    rows = []
    order = 0
    for volume in volumes:
        numbers = section_numbers(
            [
                {"section": section["id"], "kind": section["kind"]}
                for section in volume["sections"]
            ]
        )
        for section in volume["sections"]:
            number = numbers[section["id"]]
            label = (
                f"Chapter {number}"
                if section["kind"] == "chapter"
                else section["kind"].title()
            )
            blocks = [
                {"id": block["id"], "text": block_text(block).strip()}
                for block in section["document"].get("content", [])
            ]
            title = section.get("title") or label
            text = " ".join(block["text"] for block in blocks)
            rows.append(
                {
                    "volume": volume["id"],
                    "volume_number": volume["number"],
                    "volume_title": volume["title"],
                    "section": section["id"],
                    "section_title": title,
                    "section_label": label,
                    "block": None,
                    "blocks": blocks,
                    "haystack": " ".join(
                        (volume["title"], title, label, text)
                    ).casefold(),
                    "order": order,
                }
            )
            order += 1
    return rows


def _result(row: dict, terms: list[str]) -> dict:
    blocks = row.get("blocks", [])
    matched = next(
        (
            block
            for block in blocks
            if any(term in block["text"].casefold() for term in terms)
        ),
        blocks[0] if blocks else {"id": None, "text": ""},
    )
    return {
        "volume": row["volume"],
        "volume_number": row["volume_number"],
        "volume_title": row["volume_title"],
        "section": row["section"],
        "section_title": row["section_title"],
        "section_label": row["section_label"],
        "block": matched["id"],
        "snippet": _snippet(matched["text"], terms),
    }


def _snippet(text: str, terms: list[str], radius: int = 90) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return ""
    folded = clean.casefold()
    starts = [folded.find(term) for term in terms]
    starts = [start for start in starts if start >= 0]
    at = min(starts) if starts else 0
    left = max(0, at - radius)
    right = min(len(clean), at + radius)
    return (
        ("…" if left else "") + clean[left:right] + ("…" if right < len(clean) else "")
    )


def _whole_number(value: Any, field: str, *, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidSearch(f"'{field}' must be a whole number.") from exc
    if number < minimum or number > maximum:
        raise InvalidSearch(f"'{field}' must be between {minimum} and {maximum}.")
    return number
