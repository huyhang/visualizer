"""Owner-driven sharing, in one place, for every kind of thing that can be shared.

Sharing is the same operation everywhere: *drop this person's grant at exactly
this scope, add one carrying the chosen role, and only let an owner do it*. It
was written three times -- once in akasha for collections and articles, twice in
chronos for books and calendars -- differing only in which resource kind and
which scope fields each named. This module holds it once.

A **kind** is the descriptor that tells the shared code those differences: its
grant namespace, and which of the three scope fields (``database`` ->
``collection`` -> ``doc_id``) a single resource of that kind fills in. That is
genuinely all that varies:

    world        database=<db>    collection=None    doc_id=None
    collection   database=<db>    collection=<col>   doc_id=None
    article      database=<db>    collection=<col>   doc_id=<id>
    book         database=<book>  collection=None    doc_id=None
    calendar     database=<owner> collection=None    doc_id=<calendar>

Everything here is pure grant logic plus a thin Flask registrar. It touches no
document store and no service layer, which is what lets akasha's account page
share a *book* without importing chronos: a grant is a grant, and both services
already share one ``_auth`` store.

Ownership is not a column anywhere -- it is holding ``delete`` at the resource's
scope. The admin role does not confer it: content access, and who may pass it
on, follows ownership rather than the admin console.
"""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from flask import jsonify, request
from flask_login import current_user, login_required

from .auth.authz import (
    DATABASE_RESOURCE,
    DELETE,
    READ,
    ROLE_PERMS,
    is_allowed,
    role_for_perms,
)
from .auth.errors import Forbidden, UserNotFound
from .auth.store import AuthStore

# The three scope fields, coarse to fine. Named once so a kind describes itself
# by naming them rather than by positional convention.
SCOPE_FIELDS = ("database", "collection", "doc_id")


@dataclass(frozen=True)
class ResourceKind:
    """One shareable kind of thing, described by the shape of its grants.

    ``fills`` are the scope fields a single resource of this kind sets; the rest
    must be null. Both halves matter: a *collection* grant and an *article*
    grant are both akasha grants naming a database and a collection, and only
    ``doc_id`` being null or set tells them apart.
    """

    name: str                                  # url segment + display key
    label: str                                 # "Book"
    plural: str                                # "Books"
    fills: tuple[str, ...]                     # scope fields a resource sets
    resource_type: str = DATABASE_RESOURCE     # grant namespace
    default_role: str = "editor"
    # What this kind calls its scope fields in a URL, positionally against
    # ``fills``. The grant store keeps every kind in the same three columns, but
    # ``/account/sharing/book/<database>`` would publish that storage detail as
    # a public path; a book's scope field is a *book*.
    path_as: tuple[str, ...] | None = None
    # Refuse a scope outright before any grant is touched -- akasha uses it to
    # keep the reserved `_auth` / `_chronos` databases unshareable.
    guard: Callable[[dict], None] | None = None
    # Something else to share whenever one of these is shared, run after the
    # grant lands. It hangs off the *kind* rather than off a route because a
    # book has two collaborator routes -- its own, and the account page's -- and
    # a rule that only one of them applied would be a rule nobody could rely on.
    after_share: Callable[[AuthStore, dict, str, str], dict | None] | None = None

    @property
    def blanks(self) -> tuple[str, ...]:
        return tuple(f for f in SCOPE_FIELDS if f not in self.fills)

    @property
    def path_fields(self) -> tuple[str, ...]:
        return self.path_as or self.fills

    def scope_from_path(self, values: Mapping) -> dict:
        """A scope from URL variables named the way *this kind* names them."""
        return self.scope(dict(zip(self.fills, (values[p] for p in self.path_fields))))

    def matches(self, grant: Mapping) -> bool:
        """Whether ``grant`` is scoped to exactly one resource of this kind."""
        if (grant.get("resource_type") or DATABASE_RESOURCE) != self.resource_type:
            return False
        return all(grant.get(f) is not None for f in self.fills) and all(
            grant.get(f) is None for f in self.blanks
        )

    def scope(self, values: Mapping) -> dict:
        """A full three-field scope from this kind's filled-in fields."""
        return {f: values.get(f) if f in self.fills else None for f in SCOPE_FIELDS}

    def describe(self, scope: Mapping) -> str:
        """The resource's own name -- the finest scope field it fills.

        Grants know ids, not titles, and deliberately so: resolving a book's
        title here would couple the account page to chronos's story store and
        cost a query per row. The coarser fields are shown beside this by the
        caller as context.
        """
        return next(scope.get(f) for f in reversed(self.fills) if scope.get(f))


# The five kinds the stack actually has. They live together because a kind is
# nothing but a description of a grant's shape, and grants already share one
# store -- ``authz`` names chronos's "book" in its own doc-comment for the same
# reason. Labels and guards are neutral here; a service tightens its own with
# ``dataclasses.replace`` (akasha gives its akasha-side ones the reserved-
# namespace guard and the writer-facing words from ``terms.py``).
#
# ``WORLD`` was the missing one, and for a while it was missing for a good
# reason: nothing granted ownership of a whole akasha database, so nobody would
# have been entitled to share one. Creating a world's first collection now
# claims the world too, which supplies the owner the operation needs -- and
# Prithvi needs the kind, because a map's permissions *are* its world's.
WORLD = ResourceKind(
    name="world", label="World", plural="Worlds",
    fills=("database",), path_as=("world",),
    # A world is a whole canon. It is handed out to be read unless someone
    # deliberately says otherwise; a collection or a book is handed out to be
    # worked on.
    default_role="reader",
)
COLLECTION = ResourceKind(
    name="collection", label="Collection", plural="Collections",
    fills=("database", "collection"),
)
ARTICLE = ResourceKind(
    name="article", label="Article", plural="Articles",
    fills=("database", "collection", "doc_id"),
)
BOOK = ResourceKind(
    name="book", label="Book", plural="Books",
    fills=("database",), path_as=("book",), resource_type="book",
)
CALENDAR = ResourceKind(
    name="calendar", label="Calendar", plural="Calendars",
    # Owner-qualified, because ``(owner, id)`` *is* a library calendar's
    # identity -- two writers may each keep an "imperial".
    fills=("database", "doc_id"), path_as=("owner", "calendar"),
    resource_type="calendar",
    # A calendar is usually handed out to be *read*; a book to be worked on.
    default_role="reader",
)


# -- pure: what a user owns, and what has been shared with them ---------------


def _perms(grant: Mapping) -> set:
    return set(grant.get("perms", ()))


def owned_resources(grants: Iterable[Mapping], kinds: Iterable[ResourceKind]) -> list[dict]:
    """Every single resource the user owns, across ``kinds``.

    A scope is "owned" when the user holds ``delete`` on a grant naming exactly
    one resource of a known kind -- which is precisely the set they are allowed
    to share with others. A whole akasha database is now such a kind (a
    ``world``); what remains excluded is the instance-wide wildcard, which names
    no resource at all and is access-management territory rather than a
    shareable thing. Duplicates are collapsed and the result sorted for a stable
    display order.
    """
    kinds = list(kinds)
    seen: set[tuple] = set()
    owned: list[dict] = []
    for grant in grants:
        if DELETE not in _perms(grant):
            continue
        kind = next((k for k in kinds if k.matches(grant)), None)
        if kind is None:
            continue
        scope = kind.scope(grant)
        key = (kind.name, *(scope[f] for f in SCOPE_FIELDS))
        if key in seen:
            continue
        seen.add(key)
        owned.append({"kind": kind.name, **scope})
    return sorted(owned, key=_scope_key)


def resources_shared_with(
    grants: Iterable[Mapping], me: str, kinds: Iterable[ResourceKind]
) -> list[dict]:
    """The resources *someone else* has given ``me`` access to, across ``kinds``.

    The mirror image of ``owned_resources``: it keeps only grants ``me`` did not
    create (``granted_by != me``) *and* does not own (no ``delete`` -- anything
    ``me`` can delete is an owned resource and belongs there instead). What
    remains is genuinely "shared with me" as a reader or an editor.

    Unlike ``owned_resources`` this keeps grants that name no kind at all -- the
    instance-wide wildcard an administrator holds is a real thing to be told
    about even though it is not a thing you can re-share. Those carry a null
    ``kind``; the caller decides how to name them.
    """
    kinds = list(kinds)
    shared = []
    for grant in grants:
        if grant.get("granted_by") == me or DELETE in _perms(grant):
            continue
        kind = next((k for k in kinds if k.matches(grant)), None)
        shared.append(
            {
                "kind": kind.name if kind else None,
                **{f: grant.get(f) for f in SCOPE_FIELDS},
                "resource_type": grant.get("resource_type") or DATABASE_RESOURCE,
                "role": role_for_perms(grant.get("perms", [])),
                "granted_by": grant.get("granted_by"),
            }
        )
    return sorted(shared, key=_scope_key)


def _scope_key(row: Mapping) -> tuple:
    return (row.get("kind") or "", *((row.get(f) or "") for f in SCOPE_FIELDS))


# -- the operation itself (still no Flask routing) ----------------------------


def require_owner(auth_store: AuthStore, kind: ResourceKind, scope: Mapping, username: str) -> None:
    """Only a resource's owner may manage who else can access it.

    Ownership is holding ``delete`` at the resource's scope -- which the creator
    gets automatically. The admin role does *not* confer it: content access, and
    who may pass it on, follows ownership rather than the admin console.
    """
    owns = is_allowed(
        auth_store.grants_for(username),
        DELETE,
        scope["database"],
        scope["collection"],
        scope["doc_id"],
        resource_type=kind.resource_type,
    )
    if not owns:
        raise Forbidden(
            f"Only an owner may manage sharing for this {kind.label.lower()}."
        )


def collaborators(auth_store: AuthStore, kind: ResourceKind, scope: Mapping) -> list[dict]:
    """Everyone granted access to this exact scope, as ``{username, role}``.

    Sorted by username for a stable display order. Includes the owner's own
    grant; callers rendering "who else can see this" filter themselves out.
    """
    people = [
        {"username": g["username"], "role": role_for_perms(g["perms"])}
        for g in auth_store.grants_on(
            scope["database"], scope["collection"], scope["doc_id"],
            resource_type=kind.resource_type,
        )
    ]
    return sorted(people, key=lambda p: p["username"])


def _replace_scope_grant(
    auth_store: AuthStore, kind: ResourceKind, scope: Mapping, username: str
) -> None:
    """Drop ``username``'s grant at *exactly* this scope, under this kind only.

    Matched on the exact scope tuple and namespaced by resource kind, so
    re-sharing merely replaces the role -- it never touches the same person's
    access to a different resource, or to a same-named one in the other service.
    """
    for grant in auth_store.grants_on(
        scope["database"], scope["collection"], scope["doc_id"],
        resource_type=kind.resource_type,
    ):
        if grant["username"] == username:
            auth_store.delete_grant(grant["id"])


def share(
    auth_store: AuthStore, kind: ResourceKind, scope: Mapping, username: str, role: str, *, me: str
) -> dict:
    """Grant ``username`` a role on a resource ``me`` owns. Idempotent."""
    if kind.guard:
        kind.guard(scope)
    require_owner(auth_store, kind, scope, me)
    if auth_store.get_user(username) is None:
        raise UserNotFound(f"User '{username}' does not exist.")
    if username == me:
        # You already own it; sharing with yourself could only *reduce* your own
        # access, so refuse rather than risk locking an owner out.
        raise Forbidden("You already own this resource.")
    perms = ROLE_PERMS.get(role)
    if perms is None:
        raise Forbidden(f"Unknown role '{role}'.")
    _replace_scope_grant(auth_store, kind, scope, username)
    auth_store.add_grant(
        username, scope["database"], scope["collection"], scope["doc_id"],
        list(perms), granted_by=me, resource_type=kind.resource_type,
    )
    result = {"kind": kind.name, **dict(scope), "user": username, "role": role}
    if kind.after_share:
        result["also"] = kind.after_share(auth_store, scope, username, me)
    return result


def world_reader_cascade(world_of: Callable[[str], str | None]):
    """An ``after_share`` hook: hand over a book's world as a reader too.

    A timeline is references -- this scene happens at *Highkeep* -- so a book
    without its world is a list of names the reader cannot open. ``world_of``
    resolves a book id to the world it is set in, and is injected because that
    answer lives in a Chronos document and this module knows nothing about
    Chronos.

    Three things make it decline rather than act:

    - **The book names no world.** Optional field, nothing to cascade to.
    - **The sharer does not own the world.** You cannot pass on what you do not
      hold, and owning a book confers nothing over the canon it points at. It
      stays quiet rather than failing the invite: the book was the thing being
      given, and it was given.
    - **They can already read it.** ``share`` *replaces* the grant at a scope,
      so cascading over an existing editor would quietly demote them. A cascade
      may add access; it may never reduce it.

    Read only, always. Sharing a book is not a way to hand over write access to
    an entire canon; a co-author who needs that gets a deliberate share of the
    world itself.
    """

    def cascade(auth_store: AuthStore, scope: Mapping, username: str, me: str):
        world = world_of(scope["database"])
        if not world:
            return None
        if not is_allowed(auth_store.grants_for(me), DELETE, world):
            return None
        if is_allowed(auth_store.grants_for(username), READ, world):
            return None
        return share(
            auth_store, WORLD, WORLD.scope({"database": world}),
            username, "reader", me=me,
        )

    return cascade


def unshare(
    auth_store: AuthStore, kind: ResourceKind, scope: Mapping, username: str, *, me: str
) -> None:
    """Revoke ``username``'s access to a resource ``me`` owns."""
    if kind.guard:
        kind.guard(scope)
    require_owner(auth_store, kind, scope, me)
    _replace_scope_grant(auth_store, kind, scope, username)


def revoke_all(auth_store: AuthStore, kind: ResourceKind, scope: Mapping) -> None:
    """Drop every grant on a resource once it is gone.

    Ids may be reused, so a grant left behind is a grant on a *name*: the next
    thing created under it would silently arrive pre-shared.
    """
    auth_store.delete_grants_on(
        scope["database"], scope["collection"], scope["doc_id"],
        resource_type=kind.resource_type,
    )


# -- the uniform route family the account page talks to -----------------------

_ACCOUNT_SHARING = "/account/sharing"


def account_sharing_url(kind: ResourceKind, scope: Mapping) -> str:
    """The collaborators URL for one resource -- the page appends ``/<user>``."""
    tail = "/".join(str(scope[f]) for f in kind.fills)
    return f"{_ACCOUNT_SHARING}/{kind.name}/{tail}/collaborators"


def register_account_sharing_routes(app, auth_store: AuthStore, csrf, kinds) -> None:
    """One GET/PUT/DELETE trio per kind, all on *this* app's own origin.

    The account page lists things from both services, so it needs to reach a
    book's collaborators from the app serving the page. It can, because the
    operation is pure grant work on the shared store -- no cross-origin fetch,
    no service-to-service call, and it still works when the two services are
    run standalone on separate ports.

    These sit alongside each service's own resource-shaped collaborator routes
    (``/books/<book>/collaborators``, and akasha's collection and document
    equivalents) rather than replacing them: those are the public API and what
    the editors call. Both spellings run the same code below.
    """
    for kind in kinds:
        _register_one(app, auth_store, csrf, kind)


def _register_one(app, auth_store: AuthStore, csrf, kind: ResourceKind) -> None:
    path = f"{_ACCOUNT_SHARING}/{kind.name}" + "".join(f"/<{f}>" for f in kind.path_fields)
    scope_of = kind.scope_from_path

    @app.get(path + "/collaborators", endpoint=f"account_share_list_{kind.name}")
    @csrf.exempt
    @login_required
    def list_people(**values):
        scope = scope_of(values)
        if kind.guard:
            kind.guard(scope)
        require_owner(auth_store, kind, scope, current_user.username)
        return jsonify({"collaborators": collaborators(auth_store, kind, scope)})

    @app.put(path + "/collaborators/<username>", endpoint=f"account_share_add_{kind.name}")
    @csrf.exempt
    @login_required
    def add_person(username, **values):
        role = (request.get_json(silent=True) or {}).get("role", kind.default_role)
        return jsonify(share(
            auth_store, kind, scope_of(values), username, role,
            me=current_user.username,
        ))

    @app.delete(path + "/collaborators/<username>", endpoint=f"account_share_del_{kind.name}")
    @csrf.exempt
    @login_required
    def remove_person(username, **values):
        unshare(auth_store, kind, scope_of(values), username, me=current_user.username)
        return "", 204
