"""Flask application factory for the Logos manuscript API.

Routes are thin: authorise, hand the parsed request to a service, shape the
response. Every I/O boundary -- the store, the Chronos gateway, the Akasha
gateway, the auth store -- is injected, so the whole service runs against
in-memory fakes with no network.

This module only wires the app together. The routes live one module per area,
each a plain ``register_*_routes(app, csrf, deps)`` called from ``create_app``:
``reader_routes``, ``review_routes``, ``publication_routes``,
``structure_routes`` and ``draft_routes``. What they share -- URL templates,
the book-grant guards, request parsing and the ``RouteDeps`` bundle of services
-- is in ``routing``.
"""

from flask import Flask, jsonify
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

from .draft_routes import register_draft_routes
from .errors import LogosError
from .gateways import ArticleGateway, ChronosGateway
from .publication import ExportJobs, PublicationService
from .publication_routes import register_publication_routes
from .reader import ReaderService
from .reader_routes import register_reader_routes
from .review_routes import register_review_routes
from .routing import BOOK_RESOURCE, RouteDeps
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
    register_draft_routes(app, csrf, deps)
    if observability is not None:
        observability.install(app, "logos")
    _register_error_handlers(app)
    return app


def _register_error_handlers(app):
    @app.errorhandler(LogosError)
    def handle_logos(err: LogosError):
        return jsonify(err.to_dict()), err.status_code

    @app.errorhandler(AuthError)
    def handle_auth(err: AuthError):
        return jsonify({"error": err.message}), err.status_code
