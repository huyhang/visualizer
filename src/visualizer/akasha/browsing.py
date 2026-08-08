"""Pure, DB-free browse/suggest helpers.

Browsing is grant-filtered just like search: a user only sees the databases and
collections in which they can ``read`` *something*. These helpers answer that
from a user's grants and a raw listing, with no dependency on Flask or MongoDB,
so they are unit tested in isolation. (Per-document read checks reuse
``authz.is_allowed``. Everyone, admins included, is filtered by their grants;
the admin role governs account/access management, not content visibility.)

Grant shape is the same as ``authz`` (``None`` in a scope field means "any").

The second half of the module is the *article list* a collection page renders:
filter by words, order by title, cut into pages. That is a plain data transform
with no Flask or Mongo in it either, so it lives here beside the grant filtering
and is unit tested the same way (the shape mirrors ``chronos.browsing``).
"""

import re
from collections.abc import Iterable, Mapping

from visualizer.auth.authz import DELETE, READ, WRITE, is_allowed

# Bounds on the page size, so a client cannot ask for an unbounded page.
DEFAULT_PER_PAGE = 25
MAX_PER_PAGE = 100


def _has_read(grant: Mapping) -> bool:
    return READ in grant.get("perms", ())


def _touches_database(grant: Mapping, database: str) -> bool:
    return grant.get("database") in (None, database)


def _touches_collection(grant: Mapping, database: str, collection: str) -> bool:
    return _touches_database(grant, database) and grant.get("collection") in (
        None,
        collection,
    )


def can_read_in_database(grants: Iterable[Mapping], database: str) -> bool:
    """Whether the user can read anything at all under ``database``."""
    return any(_has_read(g) and _touches_database(g, database) for g in grants)


def can_read_in_collection(
    grants: Iterable[Mapping], database: str, collection: str
) -> bool:
    """Whether the user can read anything under ``database/collection``."""
    return any(_has_read(g) and _touches_collection(g, database, collection) for g in grants)


def visible_databases(grants: Iterable[Mapping], databases: Iterable[str]) -> list[str]:
    """Databases from ``databases`` the user can read something in."""
    grants = list(grants)
    return [db for db in databases if can_read_in_database(grants, db)]


def visible_collections(
    grants: Iterable[Mapping], database: str, collections: Iterable[str]
) -> list[str]:
    """Collections under ``database`` the user can read something in."""
    grants = list(grants)
    return [c for c in collections if can_read_in_collection(grants, database, c)]


def can_write_in_collection(
    grants: Iterable[Mapping], database: str, collection: str
) -> bool:
    """Whether the user may create a *new* article anywhere in this collection.

    Asked with no document id, so a grant naming one specific document does not
    qualify -- being allowed to edit ``aragorn`` is not permission to invent
    ``frodo``. This is what hides the "New article" button rather than letting a
    reader press it and collect a 403.
    """
    return is_allowed(grants, WRITE, database, collection, None)


def can_delete_collection(
    grants: Iterable[Mapping], database: str, collection: str
) -> bool:
    """Whether the user owns this collection (and so may drop it once empty)."""
    return is_allowed(grants, DELETE, database, collection, None)


# -- the article list a collection page shows --------------------------------
#
# A *row* is a preview of one article plus the text the filter searches::
#
#     {"id", "title", "database", "collection", "rev", "updated", "author",
#      "fields": ["Man", "Heir of Isildur", ...]}
#
# ``fields`` feeds the filter only -- so a writer can find a character by a word
# from their body, not just by their name -- and is dropped before presenting.


def searchable_text(row: Mapping, names_only: bool = False) -> str:
    """The lowercased text a filter word is matched against for one row.

    ``names_only`` narrows it to what the article is *called*. The browse page
    wants the whole article -- finding a character by a word from their body is
    the point of it. A narrow sidebar wants the opposite: it has no room to show
    *why* something matched, so a body hit reads as a mystery, and "king"
    matching half the world is not a shortlist.
    """
    parts = [row.get("id") or "", row.get("title") or ""]
    if not names_only:
        parts.extend(row.get("fields", []))
    return " ".join(str(p) for p in parts).lower()


def matches_all_words(row: Mapping, query: str, names_only: bool = False) -> bool:
    """Whether every whitespace-separated word in ``query`` appears in the row.

    An empty/blank query matches everything. Matching is case-insensitive and
    substring-based -- ``"arag"`` matches ``"Aragorn"``.
    """
    words = query.lower().split()
    if not words:
        return True
    text = searchable_text(row, names_only)
    return all(word in text for word in words)


_WORD_BREAK = re.compile(r"[\s\-_/]+")

# How well a row answers the query, lowest first. Truncating matches
# alphabetically is the worst available cut -- twenty A-names out of three
# hundred -- so when there is a query the order is by how likely the reader
# meant it, and only then by title.
_EXACT, _PREFIX, _WORD_START, _CONTAINS, _ELSEWHERE = range(5)


def match_rank(row: Mapping, query: str) -> int:
    """Rank one row against ``query``: exact name, then prefix, then inside it.

    ``_ELSEWHERE`` means the row matched on something other than its name -- a
    field value -- which is a real match and a poor guess at what was wanted.
    """
    needle = query.lower().strip()
    if not needle:
        return _ELSEWHERE
    slug = (row.get("id") or "").lower()
    title = (row.get("title") or "").lower()
    names = [n for n in (title, slug) if n]
    if needle in names:
        return _EXACT
    if any(n.startswith(needle) for n in names):
        return _PREFIX
    if any(word.startswith(needle) for n in names for word in _WORD_BREAK.split(n)):
        return _WORD_START
    if any(needle in n for n in names):
        return _CONTAINS
    return _ELSEWHERE


def clamp_per_page(per_page: int | None) -> int:
    if not per_page or per_page < 1:
        return DEFAULT_PER_PAGE
    return min(per_page, MAX_PER_PAGE)


def _title_key(row: Mapping):
    # Order by what the reader sees, then by id, so the ordering is stable and
    # total even when two articles share a title.
    return ((row.get("title") or row.get("id") or "").lower(), row.get("id") or "")


def _ranked_key(query: str):
    """Best match first when there is a query; plain alphabetical when there is
    not. Title always breaks the tie, so the order is total either way."""
    if not query.strip():
        return _title_key
    return lambda row: (match_rank(row, query), *_title_key(row))


def present_article(row: Mapping) -> dict:
    """Trim a matched row to the fields the list renders (drop filter-only text)."""
    return {k: v for k, v in row.items() if k != "fields"}


def browse_articles(
    rows: Iterable[Mapping],
    query: str = "",
    page: int = 1,
    per_page: int = DEFAULT_PER_PAGE,
    names_only: bool = False,
) -> dict:
    """Filter, order, and return one page of articles.

    Ordered by title, or by how well each row answers ``query`` when there is
    one -- which is what makes a truncated result useful rather than merely
    short. ``page`` is 1-indexed and clamped into range, so an out-of-bounds
    request yields the last page rather than an error, which is what happens
    when the filter narrows the list under someone who was on page 4.
    """
    per_page = clamp_per_page(per_page)
    matched = [dict(r) for r in rows if matches_all_words(r, query, names_only)]
    matched.sort(key=_ranked_key(query))

    total = len(matched)
    pages = max(1, -(-total // per_page))  # ceil division
    page = max(1, min(page, pages))
    start = (page - 1) * per_page

    return {
        "documents": [present_article(r) for r in matched[start : start + per_page]],
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
    }


def most_recent(rows: Iterable[Mapping], limit: int) -> list[dict]:
    """The ``limit`` most recently written rows, newest first.

    Timestamps are ISO-8601 strings from the version history, which sort
    lexicographically in time order. A row with no history (nothing has been
    written since versioning arrived) sorts last rather than first.
    """
    ordered = sorted(
        (dict(r) for r in rows),
        key=lambda r: (r.get("updated") or "", r.get("id") or ""),
        reverse=True,
    )
    return [present_article(r) for r in ordered[:limit]]


def _scope_rank(item: Mapping, current_db: str | None, current_col: str | None) -> int:
    """0 = same collection, 1 = same database, 2 = elsewhere (nearest first)."""
    if current_db and item.get("database") == current_db:
        if current_col and item.get("collection") == current_col:
            return 0
        return 1
    return 2


def rank_suggestions(
    items: Iterable[Mapping],
    current_db: str | None = None,
    current_col: str | None = None,
) -> list[dict]:
    """Order link suggestions nearest-scope-first, then by title/slug.

    ``items`` are ``{slug, title, database, collection}`` mappings that the
    caller has already filtered to readable results. Sorting is stable and pure.
    """
    def sort_key(item: Mapping):
        title = (item.get("title") or item.get("slug") or "").lower()
        return (_scope_rank(item, current_db, current_col), title)

    return sorted((dict(i) for i in items), key=sort_key)
