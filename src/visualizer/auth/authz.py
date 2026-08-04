"""Pure, DB-free access-control logic.

Authorization is expressed as a set of *grants*. A grant scopes a user to a
resource in the document hierarchy (database -> collection -> document) and
lists the permissions they hold there. This module answers a single question,
with no dependency on Flask or MongoDB so it can be unit tested in isolation:

    given a user's grants, may they perform ``method`` on
    ``database/collection/doc_id``?

Grant shape (a plain mapping; ``None`` in a scope field means "any"/wildcard)::

    {"resource_type": "database",          # or e.g. "book" (chronos)
     "database": "middle-earth" | None,
     "collection": "lord-of-the-rings" | None,
     "doc_id": "aragorn" | None,
     "perms": ["read", "write", "delete"]}

``resource_type`` namespaces the scope. Services share one grant store, so a
grant only ever matches a request of the *same* resource type -- a chronos book
called ``x`` must never confer access to a akasha database called
``x``. A grant with no ``resource_type`` predates the field and is treated as
``"database"`` (akasha), which is also the default when asking.

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

from collections.abc import Iterable, Mapping

# Canonical permission names.
READ = "read"
WRITE = "write"
DELETE = "delete"

ALL_PERMS = (READ, WRITE, DELETE)

# Named permission bundles, from least to most privileged. These let the sharing
# API speak in friendly roles ("editor") while the store keeps raw permissions.
# ``owner`` is exactly the ownership set, so a resource's creator is an owner.
ROLE_PERMS = {
    "reader": [READ],
    "editor": [READ, WRITE],
    "owner": [READ, WRITE, DELETE],
}

# Default resource kind: akasha's database -> collection -> document.
DATABASE_RESOURCE = "database"

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


def _grant_type(grant: Mapping) -> str:
    """A grant's resource kind; absent means a legacy akasha grant."""
    return grant.get("resource_type") or DATABASE_RESOURCE


def _matches(
    grant: Mapping,
    database: str,
    collection: str | None,
    doc_id: str | None,
    resource_type: str = DATABASE_RESOURCE,
) -> bool:
    """Whether ``grant`` applies to the requested resource.

    The resource kind must match exactly -- unlike the scope fields it is never
    a wildcard, so one service's grants cannot satisfy another's requests.
    """
    if _grant_type(grant) != resource_type:
        return False
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
    resource_type: str = DATABASE_RESOURCE,
) -> set[str]:
    """Return the permissions a user holds on a specific resource.

    Only the most-specific matching grants contribute; their perms are unioned.
    Returns an empty set when nothing matches (i.e. access is denied).
    """
    matching = [
        g for g in grants if _matches(g, database, collection, doc_id, resource_type)
    ]
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
    resource_type: str = DATABASE_RESOURCE,
) -> bool:
    """Whether the user's ``grants`` permit ``perm`` on the resource."""
    return perm in effective_perms(grants, database, collection, doc_id, resource_type)


def role_for_perms(perms: Iterable[str]) -> str:
    """Name the role matching a permission set, or ``"custom"`` if none fits.

    The inverse of ``ROLE_PERMS``: used to describe an existing grant to a human
    (e.g. in the sharing UI) without leaking the raw permission list.
    """
    have = set(perms)
    for role, role_perms in ROLE_PERMS.items():
        if set(role_perms) == have:
            return role
    return "custom"


def owned_resources(grants: Iterable[Mapping]) -> list[dict]:
    """The akasha collection/document scopes the user fully owns (holds delete).

    A scope is "owned" when the user holds ``delete`` on a grant naming a
    specific collection (and optionally a specific document) -- exactly the
    resources they are allowed to share with others. Database-wide and
    instance-wide grants are excluded: they are access-management territory
    (the admin console), not a single shareable resource. Duplicates are
    collapsed and the result is sorted for a stable display order.
    """
    seen: set[tuple] = set()
    owned: list[dict] = []
    for grant in grants:
        if _grant_type(grant) != DATABASE_RESOURCE:
            continue
        if DELETE not in grant.get("perms", ()):
            continue
        database = grant.get("database")
        collection = grant.get("collection")
        if database is None or collection is None:
            continue
        doc_id = grant.get("doc_id")
        key = (database, collection, doc_id)
        if key in seen:
            continue
        seen.add(key)
        owned.append({"database": database, "collection": collection, "doc_id": doc_id})
    return sorted(owned, key=lambda r: (r["database"], r["collection"], r["doc_id"] or ""))


def resources_shared_with(grants: Iterable[Mapping], me: str) -> list[dict]:
    """The akasha resources *someone else* has granted ``me`` access to.

    The mirror image of ``owned_resources``: it keeps only grants ``me`` did not
    create (``granted_by != me``) *and* does not own (no ``delete`` -- anything
    ``me`` can delete is an owned resource and belongs under ``owned_resources``,
    not here). What remains is genuinely "shared with me" as a reader or editor.
    Each entry carries its scope, the role it amounts to, and who granted it.
    Sorted for a stable display order.
    """
    shared = []
    for grant in grants:
        if _grant_type(grant) != DATABASE_RESOURCE:
            continue
        if grant.get("granted_by") == me:
            continue
        if DELETE in grant.get("perms", ()):
            continue
        shared.append(
            {
                "database": grant.get("database"),
                "collection": grant.get("collection"),
                "doc_id": grant.get("doc_id"),
                "role": role_for_perms(grant.get("perms", [])),
                "granted_by": grant.get("granted_by"),
            }
        )
    return sorted(
        shared,
        key=lambda r: (r["database"] or "", r["collection"] or "", r["doc_id"] or ""),
    )
