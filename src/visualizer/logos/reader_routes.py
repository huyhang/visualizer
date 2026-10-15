"""The reading side: the shell, the book list, a book's text and search,
and each reader's own settings, notes and place in the book."""

from flask import jsonify, render_template, request
from flask_login import current_user, login_required

from .routing import (
    BOOK,
    RouteDeps,
    allowed,
    authorize,
    expected_rev,
    json_body,
    resource,
    with_permissions,
)
from .writer_page import is_writer_request, render_writer


def register_reader_routes(app, csrf, deps: RouteDeps):
    auth_store = deps.auth_store
    manuscripts = deps.manuscripts
    readers = deps.readers
    search = deps.search

    @app.get("/")
    @login_required
    def index():
        """The reader shell, or the writing page's for ``?mode=write``.
        Manuscript data itself arrives as JSON."""
        if is_writer_request():
            return render_writer(deps.writer_assets())
        return render_template("reader.html")

    @app.get("/health")
    @csrf.exempt
    def health():
        return jsonify({"status": "ok", "service": "logos"})

    @app.get("/books")
    @csrf.exempt
    @login_required
    def list_books():
        rows = [
            with_permissions(row, auth_store, row["book"])
            for row in manuscripts.list()
            if allowed(auth_store, "read", row["book"])
        ]
        return jsonify({"books": rows})

    @app.get("/me/reader-settings")
    @csrf.exempt
    @login_required
    def get_reader_settings():
        return jsonify(readers.get_settings(current_user.username))

    @app.put("/me/reader-settings")
    @csrf.exempt
    @login_required
    def update_reader_settings():
        return jsonify(readers.set_settings(current_user.username, json_body()))

    @app.get(BOOK)
    @csrf.exempt
    @login_required
    def get_manuscript(book):
        authorize(auth_store, "read", book)
        return resource(with_permissions(manuscripts.get(book), auth_store, book))

    @app.get(BOOK + "/report")
    @csrf.exempt
    @login_required
    def book_report(book):
        authorize(auth_store, "read", book)
        return jsonify(manuscripts.report(book))

    @app.get(BOOK + "/search")
    @csrf.exempt
    @login_required
    def search_manuscript(book):
        authorize(auth_store, "read", book)
        return jsonify(
            search.search(
                book,
                request.args.get("q"),
                offset=request.args.get("offset", 0),
                limit=request.args.get("limit", 20),
            )
        )

    @app.get(BOOK + "/me/items")
    @csrf.exempt
    @login_required
    def list_reader_items(book):
        authorize(auth_store, "read", book)
        return jsonify(
            readers.list_items(
                current_user.username,
                book,
                include_alternates=allowed(auth_store, "write", book),
            )
        )

    @app.post(BOOK + "/me/items")
    @csrf.exempt
    @login_required
    def create_reader_item(book):
        authorize(auth_store, "read", book)
        body = json_body()
        if isinstance(body, dict) and body.get("draft") is not None:
            authorize(auth_store, "write", book)
        return resource(
            readers.create_item(current_user.username, book, body), 201
        )

    @app.put(BOOK + "/me/items/<item>")
    @csrf.exempt
    @login_required
    def update_reader_item(book, item):
        authorize(auth_store, "read", book)
        return resource(
            readers.update_item(
                current_user.username, book, item, json_body(), expected_rev()
            )
        )

    @app.delete(BOOK + "/me/items/<item>")
    @csrf.exempt
    @login_required
    def delete_reader_item(book, item):
        authorize(auth_store, "read", book)
        readers.delete_item(current_user.username, book, item, expected_rev())
        return "", 204

    @app.get(BOOK + "/me/position")
    @csrf.exempt
    @login_required
    def get_reading_position(book):
        authorize(auth_store, "read", book)
        return jsonify(readers.get_position(current_user.username, book))

    @app.put(BOOK + "/me/position")
    @csrf.exempt
    @login_required
    def update_reading_position(book):
        authorize(auth_store, "read", book)
        return jsonify(
            readers.set_position(current_user.username, book, json_body())
        )
