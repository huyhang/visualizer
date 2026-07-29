"""Pure, DB-free access-control logic.

Authorization is expressed as a set of *grants*. A grant scopes a user to a
resource in the document hierarchy (database -> collection -> document) and
lists the permissions they hold there. This module answers a single question,
with no dependency on Flask or MongoDB so it can be unit tested in isolation:

    given a user's grants, may they perform ``method`` on
    ``database/collection/doc_id``?

Grant shape (a plain mapping; ``None`` in a scope field means "any"/wildcard)::

    {"database": "middle-earth" | None,
     "collection": "lord-of-the-rings" | None,
     "doc_id": "aragorn" | None,
     "perms": ["read", "write", "delete"]}

Resolution is **allow-only** with most-specific-wins:

- A grant *matches* a request when every non-null scope field equals the
  request's corresponding field. A null field matches anything.
- *Specificity* is the number of non-null scope fields (document = 3 beats
  collection = 2 beats database = 1). Among the matching grants, only those at
  the highest specificity contribute; their permissions are unioned. This lets a
  narrow grant override a broad one (either widening or narrowing access at a
  finer scope).
- There are no deny rules: anything not granted is denied.
"""

from typing import Iterable, Mapping

# Canonical permission names.
READ = "read"
WRITE = "write"
DELETE = "delete"

ALL_PERMS = (READ, WRITE, DELETE)

# HTTP method -> the permission required to perform it on a document resource.
_METHOD_PERMS = {
    "GET": READ,
    "POST": WRITE,
    "PUT": WRITE,
    "DELETE": DELETE,
}


def perm_for_method(method: str) -> str:
    """Return the permission a given HTTP method requires on a document.

    Raises ``KeyError`` for methods the document routes never use, which would
    be a programming error rather than a client error.
    """
    return _METHOD_PERMS[method.upper()]


def _matches(grant: Mapping, database: str, collection: str | None, doc_id: str | None) -> bool:
    """Whether ``grant`` applies to the requested resource."""
    for field, value in (
        ("database", database),
        ("collection", collection),
        ("doc_id", doc_id),
    ):
        scope = grant.get(field)
        if scope is not None and scope != value:
            return False
    return True


def _specificity(grant: Mapping) -> int:
    """Number of non-null scope fields (higher = more specific)."""
    return sum(
        1 for field in ("database", "collection", "doc_id") if grant.get(field) is not None
    )


def effective_perms(
    grants: Iterable[Mapping],
    database: str,
    collection: str | None = None,
    doc_id: str | None = None,
) -> set[str]:
    """Return the permissions a user holds on a specific resource.

    Only the most-specific matching grants contribute; their perms are unioned.
    Returns an empty set when nothing matches (i.e. access is denied).
    """
    matching = [g for g in grants if _matches(g, database, collection, doc_id)]
    if not matching:
        return set()
    top = max(_specificity(g) for g in matching)
    perms: set[str] = set()
    for g in matching:
        if _specificity(g) == top:
            perms.update(g.get("perms", ()))
    return perms


def is_allowed(
    grants: Iterable[Mapping],
    perm: str,
    database: str,
    collection: str | None = None,
    doc_id: str | None = None,
) -> bool:
    """Whether the user's ``grants`` permit ``perm`` on the resource."""
    return perm in effective_perms(grants, database, collection, doc_id)
