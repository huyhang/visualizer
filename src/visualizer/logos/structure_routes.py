"""A manuscript's shape: volumes and sections, their order and placement,
the prose each section holds, and deleting a whole book."""

from flask import jsonify, request
from flask_login import current_user, login_required

from .routing import (
    BOOK,
    SECTION,
    VOLUME,
    RouteDeps,
    authorize,
    expected_rev,
    json_body,
    resource,
    truthy,
    with_permissions,
)


def register_structure_routes(app, csrf, deps: RouteDeps):
    auth_store = deps.auth_store
    manuscripts = deps.manuscripts
    volumes = deps.volumes
    sections = deps.sections

    @app.delete(BOOK)
    @csrf.exempt
    @login_required
    def delete_manuscript(book):
        authorize(auth_store, "delete", book)
        manuscripts.delete(
            book,
            expected_rev(),
            current_user.username,
            cascade=truthy(request.args.get("cascade")),
        )
        return "", 204

    @app.put(BOOK + "/volume-order")
    @csrf.exempt
    @login_required
    def reorder_volumes(book):
        authorize(auth_store, "write", book)
        result = volumes.reorder(
            book, json_body(), expected_rev(), current_user.username
        )
        return resource(with_permissions(result, auth_store, book))

    @app.post(VOLUME)
    @csrf.exempt
    @login_required
    def create_volume(book, volume):
        authorize(auth_store, "write", book)
        result = volumes.create(book, volume, json_body(), current_user.username)
        return resource(with_permissions(result, auth_store, book), 201)

    @app.get(VOLUME)
    @csrf.exempt
    @login_required
    def get_volume(book, volume):
        authorize(auth_store, "read", book)
        result = volumes.get(book, volume)
        return resource(with_permissions(result, auth_store, book))

    @app.put(VOLUME)
    @csrf.exempt
    @login_required
    def update_volume(book, volume):
        authorize(auth_store, "write", book)
        result = volumes.update(
            book, volume, json_body(), expected_rev(), current_user.username
        )
        return resource(with_permissions(result, auth_store, book))

    @app.delete(VOLUME)
    @csrf.exempt
    @login_required
    def delete_volume(book, volume):
        authorize(auth_store, "delete", book)
        volumes.delete(
            book,
            volume,
            expected_rev(),
            current_user.username,
            cascade=truthy(request.args.get("cascade")),
        )
        return "", 204

    @app.get(VOLUME + "/manuscript")
    @csrf.exempt
    @login_required
    def get_volume_manuscript(book, volume):
        authorize(auth_store, "read", book)
        result = volumes.manuscript(book, volume)
        return resource(with_permissions(result, auth_store, book))

    @app.get(VOLUME + "/ui/scenes")
    @csrf.exempt
    @login_required
    def ui_volume_scenes(book, volume):
        """The original volume projection, retained for API compatibility.

        Separate from the volume manuscript rather than folded into it, so
        clients can read prose without implicitly reading Chronos.
        """
        authorize(auth_store, "read", book)
        return jsonify(volumes.scenes(book, volume))

    @app.put(VOLUME + "/section-order")
    @csrf.exempt
    @login_required
    def reorder_sections(book, volume):
        authorize(auth_store, "write", book)
        result = sections.reorder(
            book, volume, json_body(), expected_rev(), current_user.username
        )
        return resource(with_permissions(result, auth_store, book))

    @app.put(SECTION + "/placement")
    @csrf.exempt
    @login_required
    def move_section(book, volume, section):
        authorize(auth_store, "write", book)
        result = sections.move(
            book,
            volume,
            section,
            json_body(),
            expected_rev(),
            current_user.username,
        )
        return resource(with_permissions(result, auth_store, book))

    @app.post(SECTION)
    @csrf.exempt
    @login_required
    def create_section(book, volume, section):
        authorize(auth_store, "write", book)
        result = sections.create(
            book, volume, section, json_body(), current_user.username
        )
        return resource(with_permissions(result, auth_store, book), 201)

    @app.get(SECTION)
    @csrf.exempt
    @login_required
    def get_section(book, volume, section):
        authorize(auth_store, "read", book)
        result = sections.get(book, volume, section)
        return resource(with_permissions(result, auth_store, book))

    @app.get(SECTION + "/ui/scenes")
    @csrf.exempt
    @login_required
    def ui_section_scenes(book, volume, section):
        """The reader's Full View projection for the one open section."""
        authorize(auth_store, "read", book)
        return jsonify(sections.scenes(book, volume, section))

    @app.put(SECTION)
    @csrf.exempt
    @login_required
    def update_section(book, volume, section):
        authorize(auth_store, "write", book)
        result = sections.update(
            book, volume, section, json_body(), expected_rev(), current_user.username
        )
        return resource(with_permissions(result, auth_store, book))

    @app.put(SECTION + "/metadata")
    @csrf.exempt
    @login_required
    def update_section_metadata(book, volume, section):
        authorize(auth_store, "write", book)
        result = sections.update_metadata(
            book,
            volume,
            section,
            json_body(),
            expected_rev(),
            current_user.username,
        )
        return resource(with_permissions(result, auth_store, book))

    @app.delete(SECTION)
    @csrf.exempt
    @login_required
    def delete_section(book, volume, section):
        authorize(auth_store, "delete", book)
        sections.delete(
            book, volume, section, expected_rev(), current_user.username
        )
        return "", 204
