"""Flask application factory.

``create_app`` receives its ``DocumentStore`` and ``AuthStore`` by injection so
the same routing code runs against an in-memory Mongo in tests and a real Mongo
in production.

Every document route is authenticated (Flask-Login) and authorized against the
caller's fine-grained grants (see ``authz``). The resource hierarchy is
``database -> collection -> document`` and grants may be scoped at any level:

    POST   /databases/<db>/collections/<col>                  create collection
    POST   /databases/<db>/collections/<col>/documents/<id>   create document
    GET    /databases/<db>/collections/<col>/documents/<id>   get
    PUT    /databases/<db>/collections/<col>/documents/<id>   update (replace)
    DELETE /databases/<db>/collections/<col>/documents/<id>   delete
    GET    /databases/<db>/collections/<col>/search?key=&text=  search

Browser GUI (server-rendered): ``/login``, ``/register``, ``/`` (home) and
``/admin`` (user + grant management, admins only).

This module only wires the app together. The routes live one module per area,
each a plain ``register_*_routes(app, ...)`` called from ``create_app``:
``document_routes`` (the API above), ``browse_routes``, ``version_routes``,
``media_routes``, ``research_routes``, ``studio_routes`` (the research
studio's page), ``collaborator_routes``,
``account_routes`` and ``admin_routes``. What they share is in ``access``
(grant checks), ``routing`` (URL templates and request parsing) and
``share_kinds``.
"""

from collections.abc import Callable

from flask import Flask, jsonify
from flask_wtf.csrf import CSRFProtect

from visualizer import sharing
from visualizer.auth import (
    AuthError,
    AuthStore,
    build_limiter,
    init_login,
    register_auth_routes,
    register_service_links,
)
from visualizer.observability import Observability
from visualizer.observability.page import register_observability_page
from visualizer.shared_assets import register_shared_assets

from .account_routes import register_account_routes
from .admin_routes import register_admin_routes
from .browse_routes import register_browse_routes
from .collaborator_routes import register_collaborator_routes
from .document_routes import register_document_routes
from .errors import AkashaError, MediaInUse
from .labels import derive_title
from .media_routes import register_media_routes
from .media_service import MediaService
from .research import Researcher, UnavailableResearcher
from .research_jobs import ResearchJobStore
from .research_routes import register_research_routes
from .research_service import ResearchService
from .share_kinds import account_kinds
from .store import DocumentStore
from .studio_routes import StudioAssets, register_studio_routes
from .terms import TERMS
from .version_routes import register_version_routes


def create_app(
    store: DocumentStore,
    auth_store: AuthStore,
    secret_key: str,
    secure_cookies: bool = False,
    rate_limit_storage_uri: str = "memory://",
    akasha_url: str = "http://localhost:5002",
    chronos_url: str = "http://localhost:5003",
    prithvi_url: str = "http://localhost:5004",
    logos_url: str = "http://localhost:5005",
    observability: Observability | None = None,
    # Resolves a Chronos book id to the world it is set in. Injected, because
    # sharing a book also shares its world and *this* app serves one of the two
    # routes that can do it -- while deliberately not importing Chronos. Left
    # out, the account page shares the book alone; the wiring modules supply it.
    book_world: Callable[[str], str | None] | None = None,
    user_cleanup: Callable[[str], None] | None = None,
    media_service: MediaService | None = None,
    # Research delegated to the GPU box, and where its jobs are recorded. Left
    # out, research is simply off -- the NAS-only stack and the tests are
    # unchanged.
    researcher: Researcher | None = None,
    research_jobs: ResearchJobStore | None = None,
    # Where the research studio's compiled bundle is. Left out, it is read from
    # the Vite manifest under static/studio; tests hand in what they need.
    studio_assets: StudioAssets | None = None,
) -> Flask:
    app = Flask(__name__)
    # A secret key is required to sign session cookies. It must be supplied
    # explicitly (production from the environment, tests with a fixed value) --
    # there is deliberately no insecure fallback.
    if not secret_key:
        raise ValueError("create_app requires a non-empty secret_key.")
    app.secret_key = secret_key
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # Only sent over HTTPS when enabled (e.g. behind a reverse proxy).
        SESSION_COOKIE_SECURE=secure_cookies,
    )

    csrf = CSRFProtect(app)
    limiter = build_limiter(app, rate_limit_storage_uri)
    init_login(app, auth_store)
    register_auth_routes(app, auth_store, csrf, limiter)
    register_service_links(
        app,
        akasha_url,
        chronos_url,
        current="akasha",
        prithvi_url=prithvi_url,
        logos_url=logos_url,
    )
    register_shared_assets(app)

    # Every template can say "world"/"category" without hard-coding it; see
    # ``terms.py`` for why the API keeps the MongoDB names regardless. The same
    # goes for ``| title_of``, which prints a slug readably.
    app.context_processor(lambda: {"terms": TERMS})
    app.add_template_filter(derive_title, "title_of")

    register_document_routes(app, store, auth_store, csrf)
    register_browse_routes(app, store, auth_store, csrf)
    register_version_routes(app, store, auth_store, csrf)
    if media_service is not None:
        register_media_routes(app, media_service, auth_store, csrf)
    researcher = researcher or UnavailableResearcher()
    register_research_routes(
        app, researcher,
        ResearchService(store, auth_store, researcher, research_jobs, media_service),
        auth_store, csrf,
    )
    register_studio_routes(app, studio_assets)
    register_collaborator_routes(app, auth_store, csrf)
    # The account page lists things from both services, so it reaches them all
    # through one uniform family on this origin. See ``visualizer.sharing``.
    sharing.register_account_sharing_routes(
        app, auth_store, csrf, account_kinds(book_world)
    )
    register_account_routes(app, auth_store, csrf, limiter)
    register_admin_routes(
        app, auth_store, user_cleanup or (lambda _user: None)
    )
    if observability is not None:
        observability.install(app, "akasha")
        # Only this service renders the console, so only it needs the store.
        if observability.store is not None:
            register_observability_page(app, observability)
    _register_error_handlers(app)
    return app


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(AkashaError)
    def handle_domain_error(err: AkashaError):
        payload = {"error": err.message}
        if isinstance(err, MediaInUse):
            payload["references"] = err.references
        response = jsonify(payload)
        if getattr(err, "retry_after", None):
            response.headers["Retry-After"] = str(err.retry_after)
        return response, err.status_code

    @app.errorhandler(AuthError)
    def handle_auth_error(err: AuthError):
        # Auth/access-control errors (login, grants, admin actions) now come from
        # the shared ``visualizer.auth`` package with their own base class.
        return jsonify({"error": err.message}), err.status_code
