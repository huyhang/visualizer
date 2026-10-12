"""Publishing a series: its publication record, its cover, and the EPUB
and PDF exports made from it."""

from flask import Response, jsonify, request
from flask_login import current_user, login_required

from .errors import PublicationCoverNotFound
from .publication import export_filename
from .routing import BOOK, RouteDeps, authorize, expected_rev, json_body, resource


def register_publication_routes(app, csrf, deps: RouteDeps):
    auth_store = deps.auth_store
    publications = deps.publications
    export_jobs = deps.export_jobs

    @app.get(BOOK + "/publication")
    @csrf.exempt
    @login_required
    def get_publication(book):
        authorize(auth_store, "read", book)
        return resource(publications.get(book))

    @app.post(BOOK + "/publication")
    @csrf.exempt
    @login_required
    def create_publication(book):
        authorize(auth_store, "write", book)
        return resource(
            publications.create(book, json_body(), current_user.username), 201
        )

    @app.put(BOOK + "/publication")
    @csrf.exempt
    @login_required
    def update_publication(book):
        authorize(auth_store, "write", book)
        return resource(
            publications.update(
                book, json_body(), expected_rev(), current_user.username
            )
        )

    @app.get(BOOK + "/publication/cover")
    @csrf.exempt
    @login_required
    def get_publication_cover(book):
        authorize(auth_store, "read", book)
        cover = publications.cover(book)
        if cover is None:
            raise PublicationCoverNotFound("This series has no publication cover.")
        return Response(bytes(cover["data"]), mimetype=cover["mime"])

    @app.put(BOOK + "/publication/cover")
    @csrf.exempt
    @login_required
    def set_publication_cover(book):
        authorize(auth_store, "write", book)
        return jsonify(publications.set_cover(book, request.get_data(cache=False)))

    @app.delete(BOOK + "/publication/cover")
    @csrf.exempt
    @login_required
    def delete_publication_cover(book):
        authorize(auth_store, "write", book)
        publications.delete_cover(book)
        return "", 204

    def _download(book, exported):
        title = publications.get(book)["title"]
        return Response(
            exported.data,
            mimetype=exported.mimetype,
            headers={
                "Content-Disposition": (
                    'attachment; '
                    f'filename="{export_filename(title, exported.extension)}"'
                )
            },
        )

    # EPUB is a stdlib zip of XHTML: cheap enough to hand back on the request
    # that asked for it. PDF is laid out page by page and takes minutes on a
    # long series, so it is started, polled and collected instead.
    @app.get(BOOK + "/exports/epub")
    @csrf.exempt
    @login_required
    def export_epub(book):
        authorize(auth_store, "read", book)
        return _download(book, publications.export(book, "epub"))

    @app.post(BOOK + "/exports/pdf")
    @csrf.exempt
    @login_required
    def start_pdf_export(book):
        authorize(auth_store, "read", book)
        return jsonify(export_jobs.start(book, current_user.username)), 202

    @app.get(BOOK + "/exports/pdf/<job>")
    @csrf.exempt
    @login_required
    def collect_pdf_export(book, job):
        authorize(auth_store, "read", book)
        exported = export_jobs.collect(book, current_user.username, job)
        if exported is None:
            return jsonify(export_jobs.status(book, current_user.username, job)), 202
        return _download(book, exported)
