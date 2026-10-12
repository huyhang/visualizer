"""Grant-filtered browsing: listings, recent edits and link suggestions."""

from flask import Flask, jsonify, request
from flask_login import current_user, login_required

from visualizer.auth import READ, WRITE, AuthStore, is_allowed

from .browsing import (
    DEFAULT_PER_PAGE,
    browse_articles,
    can_delete_collection,
    can_write_in_collection,
    most_recent,
    rank_suggestions,
    visible_collections,
    visible_databases,
)
from .labels import derive_title
from .routing import COLLECTION_ROUTE, int_arg, reject_reserved
from .store import DocumentStore

_SUGGEST_LIMIT = 12
_RECENT_DEFAULT = 8
_RECENT_MAX = 50


def register_browse_routes(app: Flask, store: DocumentStore, auth_store: AuthStore, csrf) -> None:
    """Grant-filtered listing of databases, collections and documents, the
    "recently edited" strip the home view opens with, and the link-suggestion
    type-ahead used by the editor.

    Each level answers with enough to *render a page* rather than just names: how
    much is inside, and whether the caller may add to it -- so the browser can
    show counts and hide buttons that would only earn a 403.
    """

    @app.get("/databases")
    @csrf.exempt
    @login_required
    def list_databases():
        grants = auth_store.grants_for(current_user.username)
        databases = visible_databases(grants, store.list_databases())
        return jsonify(
            {"databases": [_database_summary(store, grants, db) for db in databases]}
        )

    @app.get("/databases/<database>/collections")
    @csrf.exempt
    @login_required
    def list_collections(database):
        reject_reserved(database)
        grants = auth_store.grants_for(current_user.username)
        present = store.list_collections(database)
        collections = visible_collections(grants, database, present)
        return jsonify(
            {
                "database": database,
                "title": derive_title(database),
                "collections": [
                    _collection_summary(store, grants, database, collection)
                    for collection in collections
                ],
                # Whether the database is *actually* empty, not merely empty as
                # far as this caller can see. Seeing no collections usually means
                # you may not read the ones that are there, and offering to
                # delete a database in that state would be a lie.
                "empty": not present,
            }
        )

    @app.get("/databases/<database>/collections/<collection>/documents")
    @csrf.exempt
    @login_required
    def list_documents(database, collection):
        """One filtered, ordered page of the articles the caller may read.

        Filtering reaches the whole article, not just its title, so the box on a
        collection page is the full-text search the API always had and the
        browser never offered.
        """
        reject_reserved(database)
        grants = auth_store.grants_for(current_user.username)
        rows = _readable_rows(store, grants, database, collection)
        page = browse_articles(
            rows,
            request.args.get("filter", ""),
            int_arg("page", 1),
            int_arg("per_page", DEFAULT_PER_PAGE),
            # `match=name` narrows the filter to what an article is *called*.
            # The sidebar asks for it: it has no room to show why a body match
            # matched, and "king" hitting half the world is not a shortlist.
            names_only=request.args.get("match") == "name",
        )
        can_delete = can_delete_collection(grants, database, collection)
        can_write = can_write_in_collection(grants, database, collection)
        return jsonify(
            {
                "database": database,
                "collection": collection,
                "database_title": derive_title(database),
                "collection_title": derive_title(collection),
                "can_write": can_write,
                "can_delete": can_delete,
                # How many tombstones are here: what deleting the collection
                # would cost, and how many articles could be brought back.
                # Counted only for someone who could act on either.
                "deleted": (
                    store.count_deleted(database, collection)
                    if (can_write or can_delete) else 0
                ),
                **page,
            }
        )

    @app.get(COLLECTION_ROUTE + "/deleted")
    @csrf.exempt
    @login_required
    def list_deleted_documents(database, collection):
        """The articles deleted from this collection, and what would come back.

        Deletes are soft, so a tombstone still holds the history that makes it
        recoverable -- but nothing lists it, which until now meant a deleted
        article could only be found by already knowing its slug. Grant-filtered
        per article like every other listing, and each row says whether *this*
        caller may restore it, so the button is only drawn when it would work.
        """
        reject_reserved(database)
        grants = auth_store.grants_for(current_user.username)
        rows = [
            {
                **row,
                "database": database,
                "collection": collection,
                "can_restore": (
                    row["restore_rev"] is not None
                    and is_allowed(grants, WRITE, database, collection, row["id"])
                ),
            }
            for row in store.list_deleted(database, collection)
            if is_allowed(grants, READ, database, collection, row["id"])
        ]
        return jsonify(
            {"database": database, "collection": collection, "documents": rows}
        )

    @app.get("/recent")
    @csrf.exempt
    @login_required
    def recent_documents():
        """The articles written to most recently, newest first.

        Scans every readable namespace, the same reach ``/suggest`` has -- but
        once per visit to the home view rather than once per keystroke, which is
        what makes it affordable at the scale this runs.
        """
        limit = max(1, min(int_arg("limit", _RECENT_DEFAULT), _RECENT_MAX))
        grants = auth_store.grants_for(current_user.username)
        rows = [
            row
            for database, collection in _visible_namespaces(store, grants)
            for row in _readable_rows(store, grants, database, collection)
        ]
        return jsonify({"documents": most_recent(rows, limit)})

    @app.get("/suggest")
    @csrf.exempt
    @login_required
    def suggest():
        query = (request.args.get("q") or "").strip()
        if not query:
            return jsonify({"suggestions": []})
        current_db = request.args.get("db") or None
        current_col = request.args.get("col") or None
        grants = auth_store.grants_for(current_user.username)
        matches = _gather_suggestions(store, grants, query)
        ranked = rank_suggestions(matches, current_db, current_col)
        return jsonify({"suggestions": ranked[:_SUGGEST_LIMIT]})


def _field_values(body: dict) -> list[str]:
    """Every scalar the article holds, flattened -- the filter's haystack."""
    values: list[str] = []
    for value in body.values():
        if isinstance(value, list):
            values.extend(str(v) for v in value)
        elif value is not None:
            values.append(str(value))
    return values


def _article_row(database, collection, doc: dict) -> dict:
    """A browse row: what the list renders, plus the text the filter reads."""
    body = doc.get("document", {})
    return {
        "id": doc["id"],
        "title": body.get("title"),
        "database": database,
        "collection": collection,
        "database_title": derive_title(database),
        "collection_title": derive_title(collection),
        "rev": doc.get("rev"),
        "updated": doc.get("updated"),
        "author": doc.get("author"),
        "fields": _field_values(body),
    }


def _readable_rows(store: DocumentStore, grants, database, collection) -> list[dict]:
    """Browse rows for every article in a collection the user may read."""
    return [
        _article_row(database, collection, doc)
        for doc in store.list_documents(database, collection)
        if is_allowed(grants, READ, database, collection, doc["id"])
    ]


def _readable_count(store: DocumentStore, grants, database, collection) -> int:
    """How many articles the user can see in a collection.

    The ordinary case -- a grant covering the whole collection -- is a single
    count. Only someone holding document-scoped grants pays for a per-id check,
    and then we read ids alone rather than whole documents.
    """
    if is_allowed(grants, READ, database, collection, None):
        return store.count_documents(database, collection)
    return sum(
        1
        for doc_id in store.document_ids(database, collection)
        if is_allowed(grants, READ, database, collection, doc_id)
    )


def _collection_summary(store: DocumentStore, grants, database, collection) -> dict:
    return {
        "name": collection,
        "title": derive_title(collection),
        "articles": _readable_count(store, grants, database, collection),
        "can_write": can_write_in_collection(grants, database, collection),
        "can_delete": can_delete_collection(grants, database, collection),
    }


def _database_summary(store: DocumentStore, grants, database) -> dict:
    collections = visible_collections(
        grants, database, store.list_collections(database)
    )
    return {
        "name": database,
        "title": derive_title(database),
        "collections": len(collections),
        "articles": sum(
            _readable_count(store, grants, database, collection)
            for collection in collections
        ),
    }


def _visible_namespaces(store: DocumentStore, grants):
    """Yield (database, collection) pairs the user may read within."""
    for database in visible_databases(grants, store.list_databases()):
        for collection in visible_collections(
            grants, database, store.list_collections(database)
        ):
            yield database, collection


def _gather_suggestions(store: DocumentStore, grants, query: str) -> list[dict]:
    """Find readable articles whose slug or title matches ``query``."""
    needle = query.lower()
    matches: list[dict] = []
    for database, collection in _visible_namespaces(store, grants):
        for doc in store.search(database, collection, text=query):
            if not is_allowed(grants, READ, database, collection, doc["id"]):
                continue
            title = doc["document"].get("title")
            if needle in doc["id"].lower() or (title and needle in title.lower()):
                matches.append(
                    {
                        "slug": doc["id"],
                        "title": title,
                        "database": database,
                        "collection": collection,
                        "database_title": derive_title(database),
                        "collection_title": derive_title(collection),
                    }
                )
    return matches
