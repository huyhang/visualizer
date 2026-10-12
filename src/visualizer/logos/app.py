"""Flask application factory for the Logos manuscript API.

Routes are thin: authorise, hand the parsed request to a service, shape the
response. Every I/O boundary -- the store, the Chronos gateway, the Akasha
gateway, the auth store -- is injected, so the whole service runs against
in-memory fakes with no network.
"""

from flask import Flask, jsonify
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
    LogosError,
)
from .gateways import ArticleGateway, ChronosGateway
from .publication import ExportJobs, PublicationService
from .publication_routes import register_publication_routes
from .reader import ReaderService
from .reader_routes import register_reader_routes
from .review_routes import register_review_routes
from .routing import (
    BOOK_RESOURCE,
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
from .search import SearchService
from .services import DraftService, ManuscriptService, SectionService, VolumeService
from .store import LogosStore
from .structure_routes import register_structure_routes
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
    register_review_routes(app, csrf, deps)
    register_publication_routes(app, csrf, deps)
    register_structure_routes(app, csrf, deps)
    _register_routes(app, csrf, deps)
    if observability is not None:
        observability.install(app, "logos")
    _register_error_handlers(app)
    return app


def _register_routes(app, csrf, deps: RouteDeps):
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


def _register_error_handlers(app):
    @app.errorhandler(LogosError)
    def handle_logos(err: LogosError):
        return jsonify(err.to_dict()), err.status_code

    @app.errorhandler(AuthError)
    def handle_auth(err: AuthError):
        return jsonify({"error": err.message}), err.status_code
