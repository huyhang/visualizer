"""Flask application factory for the Logos manuscript API.

Routes are thin: authorise, hand the parsed request to a service, shape the
response. Every I/O boundary -- the store, the Chronos gateway, the Akasha
gateway, the auth store -- is injected, so the whole service runs against
in-memory fakes with no network.
"""

from flask import Flask, jsonify, request
from flask_login import current_user, login_required
from flask_wtf.csrf import CSRFProtect

from visualizer.auth import (
    AuthError,
    build_limiter,
    init_login,
    is_allowed,
    register_auth_routes,
    register_service_links,
)
from visualizer.observability import Observability
from visualizer.shared_assets import register_shared_assets

from .errors import Forbidden, InvalidRevision, LogosError, PreconditionRequired
from .gateways import ArticleGateway, ChronosGateway
from .services import ManuscriptService, SectionService, VolumeService
from .store import LogosStore

# Logos reads the Chronos book grant directly -- one resource kind, one grant,
# no second sharing model and no migration for books that already exist.
BOOK_RESOURCE = "book"

_BOOK = "/books/<book>"
_VOLUME = _BOOK + "/volumes/<volume>"
_SECTION = _VOLUME + "/sections/<section>"

_TRUTHY = frozenset({"1", "true", "yes", "on"})


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
    observability: Observability | None = None,
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
    # Logos has no browser UI yet, but it shares the login pages, so those pages
    # still need the sibling-service links and a human name for this service.
    register_auth_routes(app, auth_store, csrf, limiter, home_endpoint="list_books")
    register_service_links(
        app,
        akasha_url,
        chronos_url,
        current="logos",
        prithvi_url=prithvi_url,
        home_endpoint="list_books",
    )
    register_shared_assets(app)

    manuscripts = ManuscriptService(store, chronos, articles)
    volumes = VolumeService(store, chronos, articles)
    sections = SectionService(store, chronos, articles)
    _register_routes(app, csrf, auth_store, manuscripts, volumes, sections)
    if observability is not None:
        observability.install(app, "logos")
    _register_error_handlers(app)
    return app


def _register_routes(app, csrf, auth_store, manuscripts, volumes, sections):
    @app.get("/health")
    @csrf.exempt
    def health():
        return jsonify({"status": "ok", "service": "logos"})

    @app.get("/books")
    @csrf.exempt
    @login_required
    def list_books():
        rows = [
            row
            for row in manuscripts.list()
            if _allowed(auth_store, "read", row["book"])
        ]
        return jsonify({"books": rows})

    @app.get(_BOOK)
    @csrf.exempt
    @login_required
    def get_manuscript(book):
        _authorize(auth_store, "read", book)
        return _resource(_with_permissions(manuscripts.get(book), auth_store, book))

    @app.get(_BOOK + "/report")
    @csrf.exempt
    @login_required
    def book_report(book):
        _authorize(auth_store, "read", book)
        return jsonify(manuscripts.report(book))

    @app.delete(_BOOK)
    @csrf.exempt
    @login_required
    def delete_manuscript(book):
        _authorize(auth_store, "delete", book)
        manuscripts.delete(
            book,
            _expected_rev(),
            current_user.username,
            cascade=_truthy(request.args.get("cascade")),
        )
        return "", 204

    @app.put(_BOOK + "/volume-order")
    @csrf.exempt
    @login_required
    def reorder_volumes(book):
        _authorize(auth_store, "write", book)
        result = volumes.reorder(
            book, _json_body(), _expected_rev(), current_user.username
        )
        return _resource(_with_permissions(result, auth_store, book))

    @app.post(_VOLUME)
    @csrf.exempt
    @login_required
    def create_volume(book, volume):
        _authorize(auth_store, "write", book)
        result = volumes.create(book, volume, _json_body(), current_user.username)
        return _resource(_with_permissions(result, auth_store, book), 201)

    @app.get(_VOLUME)
    @csrf.exempt
    @login_required
    def get_volume(book, volume):
        _authorize(auth_store, "read", book)
        result = volumes.get(book, volume)
        return _resource(_with_permissions(result, auth_store, book))

    @app.put(_VOLUME)
    @csrf.exempt
    @login_required
    def update_volume(book, volume):
        _authorize(auth_store, "write", book)
        result = volumes.update(
            book, volume, _json_body(), _expected_rev(), current_user.username
        )
        return _resource(_with_permissions(result, auth_store, book))

    @app.delete(_VOLUME)
    @csrf.exempt
    @login_required
    def delete_volume(book, volume):
        _authorize(auth_store, "delete", book)
        volumes.delete(
            book,
            volume,
            _expected_rev(),
            current_user.username,
            cascade=_truthy(request.args.get("cascade")),
        )
        return "", 204

    @app.get(_VOLUME + "/manuscript")
    @csrf.exempt
    @login_required
    def get_volume_manuscript(book, volume):
        _authorize(auth_store, "read", book)
        result = volumes.manuscript(book, volume)
        return _resource(_with_permissions(result, auth_store, book))

    @app.put(_VOLUME + "/section-order")
    @csrf.exempt
    @login_required
    def reorder_sections(book, volume):
        _authorize(auth_store, "write", book)
        result = sections.reorder(
            book, volume, _json_body(), _expected_rev(), current_user.username
        )
        return _resource(_with_permissions(result, auth_store, book))

    @app.post(_SECTION)
    @csrf.exempt
    @login_required
    def create_section(book, volume, section):
        _authorize(auth_store, "write", book)
        result = sections.create(
            book, volume, section, _json_body(), current_user.username
        )
        return _resource(_with_permissions(result, auth_store, book), 201)

    @app.get(_SECTION)
    @csrf.exempt
    @login_required
    def get_section(book, volume, section):
        _authorize(auth_store, "read", book)
        result = sections.get(book, volume, section)
        return _resource(_with_permissions(result, auth_store, book))

    @app.put(_SECTION)
    @csrf.exempt
    @login_required
    def update_section(book, volume, section):
        _authorize(auth_store, "write", book)
        result = sections.update(
            book, volume, section, _json_body(), _expected_rev(), current_user.username
        )
        return _resource(_with_permissions(result, auth_store, book))

    @app.delete(_SECTION)
    @csrf.exempt
    @login_required
    def delete_section(book, volume, section):
        _authorize(auth_store, "delete", book)
        sections.delete(
            book, volume, section, _expected_rev(), current_user.username
        )
        return "", 204

    @app.get(_SECTION + "/versions")
    @csrf.exempt
    @login_required
    def section_versions(book, volume, section):
        _authorize(auth_store, "read", book)
        return jsonify(sections.history(book, volume, section))

    @app.get(_SECTION + "/versions/<int:rev>")
    @csrf.exempt
    @login_required
    def section_version(book, volume, section, rev):
        _authorize(auth_store, "read", book)
        return jsonify(sections.revision(book, volume, section, rev))

    @app.post(_SECTION + "/restore/<int:rev>")
    @csrf.exempt
    @login_required
    def restore_section(book, volume, section, rev):
        _authorize(auth_store, "write", book)
        result = sections.restore(
            book, volume, section, rev, _expected_rev(), current_user.username
        )
        return _resource(_with_permissions(result, auth_store, book))


# -- helpers -----------------------------------------------------------------


def _allowed(auth_store, permission: str, book: str) -> bool:
    return is_allowed(
        auth_store.grants_for(current_user.username),
        permission,
        book,
        resource_type=BOOK_RESOURCE,
    )


def _authorize(auth_store, permission: str, book: str) -> None:
    if not _allowed(auth_store, permission, book):
        raise Forbidden(
            f"You lack '{permission}' permission on Chronos book '{book}'."
        )


def _with_permissions(result: dict, auth_store, book: str) -> dict:
    return {
        **result,
        "permissions": {
            "write": _allowed(auth_store, "write", book),
            "delete": _allowed(auth_store, "delete", book),
        },
    }


def _json_body():
    return request.get_json(silent=True)


def _expected_rev() -> int:
    """The revision the caller says they read. Required for every mutation.

    Prose is the one thing in this stack a lost update destroys irrecoverably,
    so Logos refuses an unconditional write rather than accepting it the way
    Chronos and Prithvi do. See ``docs/logos/README.md``.
    """
    raw = request.headers.get("If-Match")
    if raw is None:
        raise PreconditionRequired(
            "This request must carry an If-Match header naming the revision read."
        )
    candidate = raw.strip().strip('"')
    if not candidate or candidate == "*":
        raise InvalidRevision("If-Match must name a concrete revision number.")
    try:
        revision = int(candidate)
    except ValueError as exc:
        raise InvalidRevision(f"If-Match is not a revision number: {raw!r}.") from exc
    if revision < 1:
        raise InvalidRevision("A revision number starts at 1.")
    return revision


def _truthy(value) -> bool:
    return value is not None and str(value).strip().lower() in _TRUTHY


def _resource(result: dict, status: int = 200):
    """A JSON body, with an ETag whenever the resource actually has a revision.

    A manuscript that has no outline yet reads as revision 0 and gets no ETag:
    there is no revision to quote back, and offering ``"0"`` would only hand the
    caller a precondition the API must then reject.
    """
    response = jsonify(result)
    response.status_code = status
    if result.get("rev"):
        response.headers["ETag"] = f'"{result["rev"]}"'
    return response


def _register_error_handlers(app):
    @app.errorhandler(LogosError)
    def handle_logos(err: LogosError):
        return jsonify(err.to_dict()), err.status_code

    @app.errorhandler(AuthError)
    def handle_auth(err: AuthError):
        return jsonify({"error": err.message}), err.status_code
