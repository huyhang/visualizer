"""Who may do what to an Akasha resource, asked of the current user.

Grants decide everything: reading, writing and deleting content, and -- as
ownership, which is holding ``delete`` -- managing who else may. Shared by the
route modules, which is why it lives outside any one of them.
"""

from flask_login import current_user

from visualizer import sharing
from visualizer.auth import (
    ALL_PERMS,
    DELETE,
    AuthStore,
    Forbidden,
    is_allowed,
    perm_for_method,
)

from .routing import reject_reserved
from .share_kinds import AKASHA_ARTICLE, AKASHA_COLLECTION


def claim_unowned_world(auth_store: AuthStore, username: str, database: str) -> None:
    """Whoever brings a world into being owns it, the same as a collection.

    A world exists once something is created in it, so its first collection is
    the moment there is anything to own. Only the *first*: a writer adding a
    category to somebody else's world takes only that category, which is why
    this looks for an existing owner before claiming anything.

    Without this nobody would hold world scope, and the ``world`` kind would be
    a resource with no owner entitled to share it -- which is exactly why the
    kind did not exist before. Prithvi reads maps against this grant, so it is
    also what lets a writer put a map in a world they made.
    """
    already_owned = any(
        DELETE in (grant.get("perms") or ())
        for grant in auth_store.grants_on(database, None, None)
    )
    if not already_owned:
        auth_store.grant_owner(username, database, None, None, list(ALL_PERMS))


def require_owner(auth_store: AuthStore, database, collection, doc_id=None) -> None:
    """Only a resource's owner may manage who else can access it.

    Ownership is holding ``delete`` at the resource's scope -- which the creator
    gets automatically, and which a collection owner also holds over the
    documents beneath it. The admin role does *not* confer this: content access
    (and who may share it) follows ownership, not the admin console.
    """
    sharing.require_owner(
        auth_store, kind_for(collection, doc_id),
        scope_for(database, collection, doc_id), current_user.username,
    )


def authorize(auth_store: AuthStore, method: str, database, collection, doc_id=None) -> None:
    """Raise ``Forbidden`` unless the current user may perform ``method`` here.

    Everyone -- including admins -- must hold the matching permission
    (read/write/delete) at some scope covering the resource. The admin role
    governs *account and access management* (the ``/admin`` console), not content
    access: an admin sees another user's content only where explicitly granted.
    """
    reject_reserved(database)
    perm = perm_for_method(method)
    grants = auth_store.grants_for(current_user.username)
    if not is_allowed(grants, perm, database, collection, doc_id):
        raise Forbidden(
            f"You do not have '{perm}' permission on this resource."
        )


def revoke_scope(auth_store: AuthStore, database, collection) -> None:
    """Drop every grant naming exactly this collection.

    Called when the collection itself goes, so a namespace that no longer exists
    stops being offered for sharing on its owners' account pages.
    """
    for grant in auth_store.grants_on(database, collection, None):
        auth_store.delete_grant(grant["id"])


def filter_readable(auth_store: AuthStore, database, collection, results):
    """Drop search results the current user is not allowed to read."""
    grants = auth_store.grants_for(current_user.username)
    return [
        r
        for r in results
        if is_allowed(grants, "read", database, collection, r["id"])
    ]


def is_owner(auth_store: AuthStore, database, collection, doc_id=None) -> bool:
    """Whether the current user owns (holds ``delete`` on) this resource."""
    grants = auth_store.grants_for(current_user.username)
    return is_allowed(grants, DELETE, database, collection, doc_id)


def kind_for(collection, doc_id):
    """Which shareable kind a collection/document scope names."""
    return AKASHA_ARTICLE if doc_id is not None else AKASHA_COLLECTION


def scope_for(database, collection, doc_id):
    return {"database": database, "collection": collection, "doc_id": doc_id}
