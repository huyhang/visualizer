"""Owner-driven sharing of one collection or document.

The resource-shaped routes. The account page reaches the same operations
through ``visualizer.sharing.register_account_sharing_routes``.
"""

from flask import Flask, jsonify, request
from flask_login import current_user, login_required

from visualizer import sharing
from visualizer.auth import AuthStore

from .access import kind_for, require_owner, scope_for
from .routing import COLLECTION_ROUTE, DOC_ROUTE, reject_reserved


def _collaborators(auth_store: AuthStore, database, collection, doc_id) -> list[dict]:
    return sharing.collaborators(
        auth_store, kind_for(collection, doc_id), scope_for(database, collection, doc_id)
    )


def _share(auth_store: AuthStore, database, collection, doc_id, username):
    """Grant ``username`` a role on a resource the current user owns.

    The resource-shaped spelling of the same operation the account page reaches
    through ``/account/sharing/...``; both run ``visualizer.sharing.share``.
    """
    kind = kind_for(collection, doc_id)
    role = (request.get_json(silent=True) or {}).get("role", kind.default_role)
    return jsonify(sharing.share(
        auth_store, kind, scope_for(database, collection, doc_id), username, role,
        me=current_user.username,
    ))


def _unshare(auth_store: AuthStore, database, collection, doc_id, username):
    """Revoke ``username``'s access to a resource the current user owns."""
    sharing.unshare(
        auth_store, kind_for(collection, doc_id), scope_for(database, collection, doc_id),
        username, me=current_user.username,
    )
    return "", 204


def register_collaborator_routes(app: Flask, auth_store: AuthStore, csrf) -> None:
    """Owner-driven sharing: a resource's owner grants others reader/editor/owner
    access to a collection or a single document -- without needing an admin.
    Mirrors the collaborator model chronos already uses for books."""

    _COLLAB = "/collaborators"

    @app.get(COLLECTION_ROUTE + _COLLAB)
    @csrf.exempt
    @login_required
    def list_collection_collaborators(database, collection):
        reject_reserved(database)
        require_owner(auth_store, database, collection, None)
        return jsonify(
            {"collaborators": _collaborators(auth_store, database, collection, None)}
        )

    @app.put(COLLECTION_ROUTE + _COLLAB + "/<username>")
    @csrf.exempt
    @login_required
    def add_collection_collaborator(database, collection, username):
        return _share(auth_store, database, collection, None, username)

    @app.delete(COLLECTION_ROUTE + _COLLAB + "/<username>")
    @csrf.exempt
    @login_required
    def remove_collection_collaborator(database, collection, username):
        return _unshare(auth_store, database, collection, None, username)

    @app.get(DOC_ROUTE + _COLLAB)
    @csrf.exempt
    @login_required
    def list_document_collaborators(database, collection, doc_id):
        reject_reserved(database)
        require_owner(auth_store, database, collection, doc_id)
        return jsonify(
            {"collaborators": _collaborators(auth_store, database, collection, doc_id)}
        )

    @app.put(DOC_ROUTE + _COLLAB + "/<username>")
    @csrf.exempt
    @login_required
    def add_document_collaborator(database, collection, doc_id, username):
        return _share(auth_store, database, collection, doc_id, username)

    @app.delete(DOC_ROUTE + _COLLAB + "/<username>")
    @csrf.exempt
    @login_required
    def remove_document_collaborator(database, collection, doc_id, username):
        return _unshare(auth_store, database, collection, doc_id, username)
