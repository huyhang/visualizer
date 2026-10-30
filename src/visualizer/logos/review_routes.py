"""Writer-only aids: Akasha entity lookup, the scenes beside the prose, and
private writing review."""

from flask import jsonify, request
from flask_login import current_user, login_required

from .errors import InvalidSearch
from .richtext import validate_document
from .routing import (
    BOOK,
    VOLUME,
    RouteDeps,
    authorize,
    json_body,
    truthy,
    writing_dialect,
)
from .validation import validate_identifier


def register_review_routes(app, csrf, deps: RouteDeps):
    auth_store = deps.auth_store
    manuscripts = deps.manuscripts
    articles = deps.articles
    volumes = deps.volumes
    writing_advisor = deps.writing_advisor
    series_review = deps.series_review

    @app.get(BOOK + "/ui/entities")
    @csrf.exempt
    @login_required
    def lookup_entities(book):
        authorize(auth_store, "write", book)
        query = (request.args.get("q") or "").strip()
        if not query or len(query) > 200:
            raise InvalidSearch("An entity lookup must contain 1-200 characters.")
        chronos_book = manuscripts.require(book)
        grants = auth_store.grants_for(current_user.username)
        return jsonify(
            {
                "query": query,
                "entities": articles.lookup_entities(
                    query, grants, chronos_book.get("world")
                ),
            }
        )

    @app.get(VOLUME + "/ui/scene-cards")
    @csrf.exempt
    @login_required
    def writer_scene_cards(book, volume):
        """The scene cards above the writing page, for the whole volume.

        Write access, unlike the reader's ``/ui/scenes``: these carry each
        scene's place, cast and description, which a reader of the prose has
        not been offered. Names come from Akasha under the writer's own grants.
        """
        authorize(auth_store, "write", book)
        grants = auth_store.grants_for(current_user.username)
        return jsonify(volumes.scene_details(book, volume, grants))

    @app.get(BOOK + "/ui/scene-choices")
    @csrf.exempt
    @login_required
    def writer_scene_choices(book):
        """Every scene in the book, for choosing the ones a section tells."""
        authorize(auth_store, "write", book)
        return jsonify(volumes.scene_choices(book))

    @app.post(BOOK + "/ui/writing-review")
    @csrf.exempt
    @login_required
    def review_writing(book):
        authorize(auth_store, "write", book)
        manuscripts.require(book)
        body = json_body()
        if not isinstance(body, dict) or set(body) - {"document", "dialect"}:
            raise InvalidSearch("A writing review requires a document and dialect.")
        dialect = writing_dialect(body.get("dialect", "en-US"))
        document = validate_document(body.get("document"))
        return jsonify(
            {
                "dialect": dialect,
                "issues": writing_advisor.review(document, dialect),
                "private": bool(getattr(writing_advisor, "private", False)),
            }
        )

    @app.get(BOOK + "/ui/writing-review")
    @csrf.exempt
    @login_required
    def review_series_writing(book):
        authorize(auth_store, "write", book)
        dialect = writing_dialect(request.args.get("dialect", "en-US"))
        volume = request.args.get("volume")
        return jsonify(
            series_review.review(
                book,
                dialect,
                include_alternates=truthy(request.args.get("include_alternates")),
                volume=validate_identifier(volume, "volume") if volume else None,
            )
        )
