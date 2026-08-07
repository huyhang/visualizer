"""Pure, DB-free helpers for the plotline browser and the scene picker.

The visualiser's landing page lists a book's plotlines in a table that is
ordered by name, narrowed by a word filter, and paginated; the plotline editor
picks scenes to add from the same shape of list, ordered by time instead. Those
operations are plain data transforms with no Flask or Mongo in sight, so they
live here and are unit tested in isolation -- the same pattern as
``akasha.browsing`` and the rest of Chronos's pure logic modules.

A *row* is a plain mapping describing one plotline for the table::

    {"id": ..., "book": ..., "name": ..., "goals": [...], "event_titles": [...]}

``name`` is the plotline's display name (its title, or its id when untitled).
``event_titles`` feeds the filter only -- so a writer can find a thread by a
word from any of its scenes -- and is dropped from the presented rows.
"""

from collections import Counter
from collections.abc import Iterable, Mapping

# Bounds for the page size, so a client cannot ask for an unbounded page.
DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100


def searchable_text(row: Mapping) -> str:
    """The lowercased text a filter word is matched against for one row.

    Combines the row's name with whatever else should surface it: a plotline's
    goals and its events' titles, or a scene's place and cast (``keywords``).
    """
    parts = [row.get("name") or row.get("id") or ""]
    parts.extend(row.get("goals", []))
    parts.extend(row.get("event_titles", []))
    parts.extend(row.get("keywords", []))
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


def _browse(rows, query, sort_key, present, page, per_page, key) -> dict:
    """Filter, order, paginate -- the shape every browse endpoint returns.

    ``page`` is 1-indexed and clamped into range so an out-of-bounds request
    yields the last page rather than an error.
    """
    per_page = clamp_per_page(per_page)
    matched = [dict(r) for r in rows if matches_all_words(r, query)]
    matched.sort(key=sort_key)

    total = len(matched)
    pages = max(1, -(-total // per_page))  # ceil division
    page = max(1, min(page, pages))
    start = (page - 1) * per_page

    return {
        key: [present(r) for r in matched[start : start + per_page]],
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
    }


def browse_plotlines(
    rows: Iterable[Mapping],
    query: str = "",
    page: int = 1,
    per_page: int = DEFAULT_PER_PAGE,
) -> dict:
    """Filter by ``query``, order by name, and return one page of plotlines."""
    return _browse(rows, query, _sort_key, _present_row, page, per_page, "plotlines")


def _present_row(row: Mapping) -> dict:
    """Trim a matched row to the fields the table renders (drop filter-only text)."""
    return {
        "id": row.get("id"),
        "book": row.get("book"),
        "name": row.get("name") or row.get("id"),
        "goals": list(row.get("goals", [])),
        # How many problems this thread has, so the table can flag it without
        # the writer opening every thread to find out.
        "conflicts": int(row.get("conflicts", 0)),
    }


# -- scenes (the editor's "add a scene" picker) ------------------------------


def _event_sort_key(row: Mapping):
    """Story order: scheduled scenes by time, then the undated ones by name.

    A writer picking the next scene thinks chronologically, so this list is
    ordered by *time* rather than by name -- but an unscheduled scene has no
    place on that clock, so it sorts to the end instead of to tick zero.
    """
    name = (row.get("name") or row.get("id") or "").lower()
    if row.get("scheduled"):
        return (0, row.get("start_tick") or 0, name)
    return (1, 0, name)


def browse_events(
    rows: Iterable[Mapping],
    query: str = "",
    page: int = 1,
    per_page: int = DEFAULT_PER_PAGE,
) -> dict:
    """Filter by ``query``, order by time, and return one page of scenes."""
    return _browse(rows, query, _event_sort_key, _present_event_row, page, per_page, "events")


def _present_event_row(row: Mapping) -> dict:
    return {
        "id": row.get("id"),
        "book": row.get("book"),
        "title": row.get("name") or row.get("id"),
        "when": row.get("when"),
        "scheduled": bool(row.get("scheduled")),
        "start_tick": row.get("start_tick"),
        "end_tick": row.get("end_tick"),
        "location": row.get("location"),
        "plotlines": list(row.get("plotlines", [])),
    }


# -- entity scope ------------------------------------------------------------


def dominant_database(names: Iterable[str], fallback: str) -> str:
    """The Akasha database a book's references mostly live in.

    Chronos does not dictate where a book's articles are kept -- an ``EntityRef``
    names its own database -- so the article picker has to guess a default. The
    honest guess is "wherever this book's existing scenes point"; a book with no
    scenes yet falls back to its own id, which is the convention the seed script
    and the docs use.
    """
    counted = Counter(n for n in names if n)
    if not counted:
        return fallback
    # most_common is insertion-ordered on ties; pick the first by name so the
    # answer is total and does not depend on which scene was written first.
    top = max(counted.values())
    return min(n for n, c in counted.items() if c == top)
