"""Revision history and alternates: a section's versions and restore,
named drafts, the primary draft, and each draft's own versions."""

from flask import jsonify
from flask_login import current_user, login_required

from .routing import (
    DRAFT,
    DRAFT_VERSIONS,
    DRAFTS,
    SECTION,
    RouteDeps,
    authorize,
    expected_rev,
    json_body,
    resource,
    with_permissions,
)


def register_draft_routes(app, csrf, deps: RouteDeps):
    auth_store = deps.auth_store
    sections = deps.sections
    drafts = deps.drafts

    @app.get(SECTION + "/versions")
    @csrf.exempt
    @login_required
    def section_versions(book, volume, section):
        authorize(auth_store, "read", book)
        return jsonify(sections.history(book, volume, section))

    @app.get(SECTION + "/versions/<int:rev>")
    @csrf.exempt
    @login_required
    def section_version(book, volume, section, rev):
        authorize(auth_store, "read", book)
        return jsonify(sections.revision(book, volume, section, rev))

    @app.post(SECTION + "/restore/<int:rev>")
    @csrf.exempt
    @login_required
    def restore_section(book, volume, section, rev):
        authorize(auth_store, "write", book)
        result = sections.restore(
            book, volume, section, rev, expected_rev(), current_user.username
        )
        return resource(with_permissions(result, auth_store, book))

    @app.get(DRAFTS)
    @csrf.exempt
    @login_required
    def list_drafts(book, volume, section):
        authorize(auth_store, "write", book)
        return jsonify(
            drafts.list(book, volume, section, current_user.username)
        )

    @app.post(DRAFTS)
    @csrf.exempt
    @login_required
    def create_draft(book, volume, section):
        authorize(auth_store, "write", book)
        return resource(
            drafts.create(
                book, volume, section, json_body(), current_user.username
            ),
            201,
        )

    @app.get(DRAFT)
    @csrf.exempt
    @login_required
    def get_draft(book, volume, section, draft):
        authorize(auth_store, "write", book)
        return resource(
            drafts.get(book, volume, section, draft, current_user.username)
        )

    @app.put(DRAFT)
    @csrf.exempt
    @login_required
    def update_draft(book, volume, section, draft):
        authorize(auth_store, "write", book)
        return resource(
            drafts.update(
                book,
                volume,
                section,
                draft,
                json_body(),
                expected_rev(),
                current_user.username,
            )
        )

    @app.delete(DRAFT)
    @csrf.exempt
    @login_required
    def delete_draft(book, volume, section, draft):
        authorize(auth_store, "delete", book)
        drafts.delete(
            book,
            volume,
            section,
            draft,
            expected_rev(),
            current_user.username,
        )
        return "", 204

    @app.put(SECTION + "/primary-draft")
    @csrf.exempt
    @login_required
    def make_primary_draft(book, volume, section):
        authorize(auth_store, "write", book)
        return jsonify(
            drafts.make_primary(
                book,
                volume,
                section,
                json_body(),
                expected_rev(),
                current_user.username,
            )
        )

    @app.get(DRAFT_VERSIONS)
    @csrf.exempt
    @login_required
    def draft_versions(book, volume, section, draft):
        authorize(auth_store, "write", book)
        return jsonify(
            drafts.history(book, volume, section, draft, current_user.username)
        )

    @app.get(DRAFT_VERSIONS + "/<int:rev>")
    @csrf.exempt
    @login_required
    def draft_version(book, volume, section, draft, rev):
        authorize(auth_store, "write", book)
        return jsonify(
            drafts.revision(
                book, volume, section, draft, rev, current_user.username
            )
        )

    @app.post(DRAFT_VERSIONS + "/<int:rev>/restore")
    @csrf.exempt
    @login_required
    def restore_draft(book, volume, section, draft, rev):
        authorize(auth_store, "write", book)
        return resource(
            drafts.restore(
                book,
                volume,
                section,
                draft,
                rev,
                expected_rev(),
                current_user.username,
            )
        )
