"""Flask application factory for the Logos manuscript API.

Routes are thin: authorise, hand the parsed request to a service, shape the
response. Every I/O boundary -- the store, the Chronos gateway, the Akasha
gateway, the auth store -- is injected, so the whole service runs against
in-memory fakes with no network.
"""

from flask import Flask, Response, jsonify, request
from flask_login import current_user, login_required
from flask_wtf.csrf import CSRFProtect

from visualizer.auth import (
    AuthError,
    build_limiter,
    init_login,
    register_auth_routes,
    register_service_links,
)
from visualizer.observability import Observability
from visualizer.shared_assets import register_shared_assets

from .errors import (
    InvalidSearch,
    LogosError,
    PublicationCoverNotFound,
)
from .gateways import ArticleGateway, ChronosGateway
from .publication import ExportJobs, PublicationService, export_filename
from .reader import ReaderService
from .reader_routes import register_reader_routes
from .richtext import validate_document
from .routing import (
    BOOK,
    BOOK_RESOURCE,
    DRAFT,
    DRAFT_VERSIONS,
    DRAFTS,
    SECTION,
    VOLUME,
    RouteDeps,
    authorize,
    expected_rev,
    json_body,
    resource,
    truthy,
    with_permissions,
    writing_dialect,
)
from .search import SearchService
from .services import DraftService, ManuscriptService, SectionService, VolumeService
from .store import LogosStore
from .validation import validate_identifier
from .writing import RuleBasedWritingAdvisor, SeriesWritingReview, WritingAdvisor

# BOOK_RESOURCE is defined beside the guards that use it, and re-exported here
# because this is where callers (tests, smoke scripts) have always found it.
__all__ = ["BOOK_RESOURCE", "create_app"]


def create_app(
    store: LogosStore,
    chronos: ChronosGateway,
    articles: ArticleGateway,
    auth_store,
    secret_key: str,
    *,
    secure_cookies: bool = False,
    rate_limit_storage_uri: str = "memory://",
    akasha_url: str = "http://localhost:5002",
    chronos_url: str = "http://localhost:5003",
    prithvi_url: str = "http://localhost:5004",
    logos_url: str = "http://localhost:5005",
    observability: Observability | None = None,
    pdf_renderer=None,
    export_runner=None,
    writing_advisor: WritingAdvisor | None = None,
) -> Flask:
    if not secret_key:
        raise ValueError("create_app requires a non-empty secret_key.")
    app = Flask(__name__)
    app.secret_key = secret_key
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=secure_cookies,
    )
    csrf = CSRFProtect(app)
    limiter = build_limiter(app, rate_limit_storage_uri)
    init_login(app, auth_store)
    # The reader is this app's own HTML, so a browser login lands there.
    register_auth_routes(app, auth_store, csrf, limiter, home_endpoint="index")
    register_service_links(
        app,
        akasha_url,
        chronos_url,
        current="logos",
        prithvi_url=prithvi_url,
        logos_url=logos_url,
    )
    register_shared_assets(app)

    manuscripts = ManuscriptService(store, chronos, articles)
    volumes = VolumeService(store, chronos, articles)
    sections = SectionService(store, chronos, articles)
    drafts = DraftService(store, chronos, articles)
    readers = ReaderService(store, manuscripts)
    search = SearchService(store, manuscripts)
    publications = PublicationService(store, manuscripts, pdf_renderer)
    advisor = writing_advisor or RuleBasedWritingAdvisor()
    series_review = SeriesWritingReview(store, manuscripts, advisor)
    jobs = ExportJobs(
        store, publications, **({} if export_runner is None else
                                {"runner": export_runner})
    )
    deps = RouteDeps(
        auth_store=auth_store,
        manuscripts=manuscripts,
        volumes=volumes,
        sections=sections,
        drafts=drafts,
        readers=readers,
        search=search,
        publications=publications,
        export_jobs=jobs,
        articles=articles,
        writing_advisor=advisor,
        series_review=series_review,
    )
    register_reader_routes(app, csrf, deps)
    _register_routes(app, csrf, deps)
    if observability is not None:
        observability.install(app, "logos")
    _register_error_handlers(app)
    return app


def _register_routes(app, csrf, deps: RouteDeps):
    auth_store = deps.auth_store
    manuscripts = deps.manuscripts
    volumes = deps.volumes
    sections = deps.sections
    drafts = deps.drafts
    publications = deps.publications
    export_jobs = deps.export_jobs
    articles = deps.articles
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


def _register_error_handlers(app):
    @app.errorhandler(LogosError)
    def handle_logos(err: LogosError):
        return jsonify(err.to_dict()), err.status_code

    @app.errorhandler(AuthError)
    def handle_auth(err: AuthError):
        return jsonify({"error": err.message}), err.status_code
