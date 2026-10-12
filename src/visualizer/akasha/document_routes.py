"""Health, the editor shell, and the core document API.

Create and drop namespaces, create/read/update/delete one document, and
search a collection -- every call checked against the caller's grants.
"""

from flask import Flask, jsonify, render_template, request
from flask_login import current_user, login_required

from visualizer.auth import ALL_PERMS, AuthStore

from .access import (
    authorize,
    claim_unowned_world,
    filter_readable,
    require_owner,
    revoke_scope,
)
from .routing import (
    COLLECTION_ROUTE,
    DOC_ROUTE,
    SEARCH_ROUTE,
    document_response,
    expected_rev,
    flag_arg,
    reject_reserved,
)
from .store import DocumentStore
from .validation import validate_document, validate_search_terms


def register_document_routes(app: Flask, store: DocumentStore, auth_store: AuthStore, csrf) -> None:
    @app.get("/health")
    @csrf.exempt
    def health():
        return jsonify({"status": "ok"})

    @app.get("/")
    @login_required
    def index():
        # The single-page article editor replaces the old server-rendered home.
        return render_template("editor.html")

    @app.post(COLLECTION_ROUTE)
    @csrf.exempt
    @login_required
    def create_collection(database, collection):
        # Any authenticated user may create a namespace and owns what they make.
        reject_reserved(database)
        result = store.create_collection(database, collection)
        auth_store.grant_owner(
            current_user.username, database, collection, None, list(ALL_PERMS)
        )
        claim_unowned_world(auth_store, current_user.username, database)
        return jsonify(result), 201

    @app.delete(COLLECTION_ROUTE)
    @csrf.exempt
    @login_required
    def delete_collection(database, collection):
        """Drop an empty collection you own -- and its database, if it was the
        last one in it.

        Owner-only, and only while no live article is inside: this exists so a
        namespace made by mistake can be tidied away, not as a bulk delete.
        ``?purge=1`` additionally discards the version history of articles that
        were deleted from it, which is the only way a collection that has ever
        held something can go. Its grants go with it, so a namespace that no
        longer exists stops haunting its owners' account pages.
        """
        reject_reserved(database)
        require_owner(auth_store, database, collection, None)
        result = store.delete_collection(
            database, collection, purge_history=flag_arg("purge")
        )
        revoke_scope(auth_store, database, collection)
        return jsonify({"database": database, "collection": collection, **result})

    @app.delete("/databases/<database>")
    @csrf.exempt
    @login_required
    def delete_database(database):
        """Drop a database that has no collections left.

        Gated on nothing but being logged in, exactly like *creating* a
        namespace: an empty database holds nothing to protect, and emptying it
        was already an owner-only act. This clears shells left behind by older
        versions, which created the namespace before the article was written.
        """
        reject_reserved(database)
        store.delete_database(database)
        return "", 204

    @app.post(DOC_ROUTE)
    @csrf.exempt
    @login_required
    def create(database, collection, doc_id):
        authorize(auth_store, "POST", database, collection, doc_id)
        document = validate_document(request.get_json(silent=True))
        result = store.create(
            database, collection, doc_id, document, author=current_user.username
        )
        # The creator owns the new document outright.
        auth_store.grant_owner(
            current_user.username, database, collection, doc_id, list(ALL_PERMS)
        )
        return document_response(result, 201)

    @app.get(DOC_ROUTE)
    @csrf.exempt
    @login_required
    def get(database, collection, doc_id):
        authorize(auth_store, "GET", database, collection, doc_id)
        return document_response(store.get(database, collection, doc_id))

    @app.put(DOC_ROUTE)
    @csrf.exempt
    @login_required
    def update(database, collection, doc_id):
        authorize(auth_store, "PUT", database, collection, doc_id)
        document = validate_document(request.get_json(silent=True))
        result = store.update(
            database,
            collection,
            doc_id,
            document,
            expected_rev=expected_rev(),
            author=current_user.username,
        )
        return document_response(result)

    @app.delete(DOC_ROUTE)
    @csrf.exempt
    @login_required
    def delete(database, collection, doc_id):
        authorize(auth_store, "DELETE", database, collection, doc_id)
        store.delete(
            database,
            collection,
            doc_id,
            expected_rev=expected_rev(),
            author=current_user.username,
        )
        return "", 204

    @app.get(SEARCH_ROUTE)
    @csrf.exempt
    @login_required
    def search(database, collection):
        reject_reserved(database)
        key, text = validate_search_terms(
            request.args.get("key"), request.args.get("text")
        )
        results = store.search(database, collection, key=key, text=text)
        results = filter_readable(auth_store, database, collection, results)
        return jsonify({"results": results, "count": len(results)})
