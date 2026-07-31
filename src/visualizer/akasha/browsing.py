"""Pure, DB-free browse/suggest helpers.

Browsing is grant-filtered just like search: a user only sees the databases and
collections in which they can ``read`` *something*. These helpers answer that
from a user's grants and a raw listing, with no dependency on Flask or MongoDB,
so they are unit tested in isolation. (Per-document read checks reuse
``authz.is_allowed``; admins bypass all of this in the route layer.)

Grant shape is the same as ``authz`` (``None`` in a scope field means "any").
"""

from typing import Iterable, Mapping

from .authz import READ


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
