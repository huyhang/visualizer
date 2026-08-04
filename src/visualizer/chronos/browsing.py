"""Pure, DB-free helpers for the read-only plotline browser.

The visualiser's landing page lists a book's plotlines in a table that is
ordered by name, narrowed by a word filter, and paginated. Those three
operations are plain data transforms with no Flask or Mongo in sight, so they
live here and are unit tested in isolation -- the same pattern as
``akasha.browsing`` and the rest of Chronos's pure logic modules.

A *row* is a plain mapping describing one plotline for the table::

    {"id": ..., "book": ..., "name": ..., "goals": [...], "event_titles": [...]}

``name`` is the plotline's display name (its title, or its id when untitled).
``event_titles`` feeds the filter only -- so a writer can find a thread by a
word from any of its scenes -- and is dropped from the presented rows.
"""

from collections.abc import Iterable, Mapping

# Bounds for the page size, so a client cannot ask for an unbounded page.
DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100


def searchable_text(row: Mapping) -> str:
    """The lowercased text a filter word is matched against for one row.

    Combines the plotline's name, its goals, and its events' titles, so any
    of them can surface the thread.
    """
    parts = [row.get("name") or row.get("id") or ""]
    parts.extend(row.get("goals", []))
    parts.extend(row.get("event_titles", []))
    return " ".join(str(p) for p in parts).lower()


def matches_all_words(row: Mapping, query: str) -> bool:
    """Whether every whitespace-separated word in ``query`` appears in the row.

    An empty/blank query matches everything. Matching is case-insensitive and
    substring-based -- ``"emb"`` matches ``"Emberport"``.
    """
    words = query.lower().split()
    if not words:
        return True
    text = searchable_text(row)
    return all(word in text for word in words)


def _sort_key(row: Mapping):
    # Order by display name, then id, so the ordering is stable and total even
    # when two plotlines share a name.
    name = (row.get("name") or row.get("id") or "").lower()
    return (name, row.get("id") or "")


def clamp_per_page(per_page: int | None) -> int:
    if not per_page or per_page < 1:
        return DEFAULT_PER_PAGE
    return min(per_page, MAX_PER_PAGE)


def browse_plotlines(
    rows: Iterable[Mapping],
    query: str = "",
    page: int = 1,
    per_page: int = DEFAULT_PER_PAGE,
) -> dict:
    """Filter by ``query``, order by name, and return one page.

    Returns a dict with the page's ``plotlines`` and the pagination facts the
    table needs (``page``, ``per_page``, ``total`` matching rows, ``pages``).
    ``page`` is 1-indexed and clamped into range so an out-of-bounds request
    yields an empty page rather than an error.
    """
    per_page = clamp_per_page(per_page)
    matched = [dict(r) for r in rows if matches_all_words(r, query)]
    matched.sort(key=_sort_key)

    total = len(matched)
    pages = max(1, -(-total // per_page))  # ceil division
    page = max(1, min(page, pages))
    start = (page - 1) * per_page
    window = matched[start : start + per_page]

    return {
        "plotlines": [_present_row(r) for r in window],
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
    }


def _present_row(row: Mapping) -> dict:
    """Trim a matched row to the fields the table renders (drop filter-only text)."""
    return {
        "id": row.get("id"),
        "book": row.get("book"),
        "name": row.get("name") or row.get("id"),
        "goals": list(row.get("goals", [])),
    }
