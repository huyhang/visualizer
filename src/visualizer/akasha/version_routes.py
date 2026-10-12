"""A document's version history, diffs between versions, and restore."""

from flask import Flask, jsonify, request
from flask_login import current_user, login_required

from visualizer.auth import AuthStore

from .access import authorize
from .diff import diff_documents
from .errors import DocumentNotFound, InvalidRevision, VersionNotFound
from .history import find_snapshot, history_meta
from .routing import DOC_ROUTE, document_response
from .store import DocumentStore


def register_version_routes(app: Flask, store: DocumentStore, auth_store: AuthStore, csrf) -> None:
    """Read-only version history + diff, and restore (a new revision)."""

    @app.get(DOC_ROUTE + "/versions")
    @csrf.exempt
    @login_required
    def list_versions(database, collection, doc_id):
        authorize(auth_store, "GET", database, collection, doc_id)
        history = store.history(database, collection, doc_id)
        return jsonify({"id": doc_id, "versions": history_meta(history)})

    @app.get(DOC_ROUTE + "/versions/<int:rev>")
    @csrf.exempt
    @login_required
    def get_version(database, collection, doc_id, rev):
        authorize(auth_store, "GET", database, collection, doc_id)
        snapshot = _require_snapshot(store, database, collection, doc_id, rev)
        return jsonify(snapshot)

    @app.get(DOC_ROUTE + "/diff")
    @csrf.exempt
    @login_required
    def diff_versions(database, collection, doc_id):
        authorize(auth_store, "GET", database, collection, doc_id)
        from_rev, to_rev = _parse_diff_revs(request.args)
        older = _require_snapshot(store, database, collection, doc_id, from_rev)
        newer = _require_snapshot(store, database, collection, doc_id, to_rev)
        return jsonify(
            {
                "id": doc_id,
                "from": _snapshot_meta(older),
                "to": _snapshot_meta(newer),
                "diff": diff_documents(older["document"] or {}, newer["document"] or {}),
            }
        )

    @app.post(DOC_ROUTE + "/restore/<int:rev>")
    @csrf.exempt
    @login_required
    def restore_version(database, collection, doc_id, rev):
        authorize(auth_store, "PUT", database, collection, doc_id)
        snapshot = _require_snapshot(store, database, collection, doc_id, rev)
        if snapshot["document"] is None:
            raise VersionNotFound(
                f"Version {rev} of '{doc_id}' is a deletion and cannot be restored."
            )
        result = _restore_body(store, database, collection, doc_id, snapshot["document"])
        return document_response(result)


def _require_snapshot(store: DocumentStore, database, collection, doc_id, rev) -> dict:
    snapshot = find_snapshot(store.history(database, collection, doc_id), rev)
    if snapshot is None:
        raise VersionNotFound(
            f"Version {rev} of '{doc_id}' is not retained."
        )
    return snapshot


def _snapshot_meta(snapshot: dict) -> dict:
    return {k: snapshot.get(k) for k in ("rev", "op", "author", "timestamp")}


def _parse_diff_revs(args) -> tuple[int, int]:
    try:
        return int(args["from"]), int(args["to"])
    except (KeyError, ValueError, TypeError):
        raise InvalidRevision("Diff requires integer 'from' and 'to' revisions.")


def _restore_body(store: DocumentStore, database, collection, doc_id, body: dict) -> dict:
    """Re-apply an old body as a new revision (update if live, else revive)."""
    try:
        current = store.get(database, collection, doc_id)
        return store.update(
            database,
            collection,
            doc_id,
            body,
            expected_rev=current["rev"],
            author=current_user.username,
        )
    except DocumentNotFound:
        return store.create(
            database, collection, doc_id, body, author=current_user.username
        )
