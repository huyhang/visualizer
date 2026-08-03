"""Flask application factory for Chronos (design §6.4).

``create_app`` receives its seams by injection -- the ``StoryStore`` and
``EntityGate`` plus the shared ``AuthStore`` -- so the same routing runs against
an in-memory Mongo in tests and a real one in production. Authentication and the
grant model are reused from ``akasha`` unchanged (one identity, one
login -- design decision in §12); Chronos authorizes at **book scope** using the
same allow-only, most-specific-wins ``is_allowed`` logic.
"""

from flask import Flask, jsonify, request
from flask_login import current_user, login_required
from flask_wtf.csrf import CSRFProtect

from visualizer.akasha.auth import build_limiter, init_login, register_auth_routes
from visualizer.akasha.authz import ALL_PERMS, is_allowed, perm_for_method
from visualizer.akasha.errors import AkashaError

from .entity_gate import EntityGate
from .errors import ChronosError, Forbidden, InvalidRevision
from .services import BookService, EventService, PlotlineService
from .store import StoryStore

_BOOK = "/books/<book>"
_PLOTLINE = "/books/<book>/plotlines/<plotline>"
_EVENT = "/books/<book>/events/<event>"

# Chronos grants are namespaced by this resource kind in the shared `_auth`
# store, so a book named "x" never confers access to a akasha database
# named "x" (and vice versa). See akasha.authz.
BOOK_RESOURCE = "book"

_ROLE_PERMS = {
    "reader": ["read"],
    "editor": ["read", "write"],
    "owner": ["read", "write", "delete"],
}


def create_app(
    story_store: StoryStore,
    entity_gate: EntityGate,
    auth_store,
    secret_key: str,
    secure_cookies: bool = False,
    rate_limit_storage_uri: str = "memory://",
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
    register_auth_routes(app, auth_store, csrf, limiter)

    books = BookService(story_store, entity_gate)
    plotlines = PlotlineService(story_store, entity_gate)
    events = EventService(story_store, entity_gate)

    _register_routes(app, csrf, auth_store, books, plotlines, events)
    _register_error_handler(app)
    return app


# -- helpers -----------------------------------------------------------------


def _book_allowed(auth_store, perm: str, book: str) -> bool:
    """Whether the current user holds ``perm`` on this *book* resource."""
    grants = auth_store.grants_for(current_user.username)
    return is_allowed(grants, perm, book, resource_type=BOOK_RESOURCE)


def _authorize(auth_store, method: str, book: str) -> None:
    """Raise Forbidden unless the user may perform ``method`` on the book.

    Everyone -- including admins -- is subject to grants; the admin role governs
    account/access management (in akasha's console), not content access.
    """
    perm = perm_for_method(method)
    if not _book_allowed(auth_store, perm, book):
        raise Forbidden(f"You lack '{perm}' permission on book '{book}'.")


def _can_read(auth_store, book: str) -> bool:
    return _book_allowed(auth_store, "read", book)


def _is_owner(auth_store, book: str) -> bool:
    return _book_allowed(auth_store, "delete", book)


def _expected_rev():
    raw = request.headers.get("If-Match") or request.args.get("_rev")
    if raw is None:
        return None
    raw = raw.strip().strip('"')
    if raw in ("", "*"):
        return None
    try:
        return int(raw)
    except ValueError:
        raise InvalidRevision(f"Invalid If-Match/_rev precondition: {raw!r}.")


def _resp(result: dict, status: int = 200):
    response = jsonify(result)
    response.status_code = status
    if "rev" in result:
        response.headers["ETag"] = f'"{result["rev"]}"'
    return response


def _truthy(value) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


# -- routes ------------------------------------------------------------------


def _register_routes(app, csrf, auth_store, books, plotlines, events):
    @app.get("/health")
    @csrf.exempt
    def health():
        return jsonify({"status": "ok", "service": "chronos"})

    # -- books ---------------------------------------------------------------

    @app.post(_BOOK)
    @csrf.exempt
    @login_required
    def create_book(book):
        # Any authenticated user may create a book and owns it outright.
        result = books.create(book, request.get_json(silent=True) or {}, author=current_user.username)
        auth_store.grant_owner(
            current_user.username, book, None, None, list(ALL_PERMS),
            resource_type=BOOK_RESOURCE,
        )
        return _resp(result, 201)

    @app.get("/books")
    @csrf.exempt
    @login_required
    def list_books():
        visible = [b for b in books.list() if _can_read(auth_store, b["id"])]
        return jsonify({"books": visible})

    @app.get(_BOOK)
    @csrf.exempt
    @login_required
    def get_book(book):
        _authorize(auth_store, "GET", book)
        return _resp(books.get(book))

    @app.put(_BOOK)
    @csrf.exempt
    @login_required
    def update_book(book):
        _authorize(auth_store, "PUT", book)
        result = books.update(
            book, request.get_json(silent=True) or {}, _expected_rev(), current_user.username
        )
        return _resp(result)

    @app.delete(_BOOK)
    @csrf.exempt
    @login_required
    def delete_book(book):
        _authorize(auth_store, "DELETE", book)
        books.delete(book, _expected_rev(), current_user.username)
        return "", 204

    @app.post(_BOOK + "/terminus/<event>")
    @csrf.exempt
    @login_required
    def set_terminus(book, event):
        _authorize(auth_store, "PUT", book)
        return _resp(books.set_terminus(book, event, current_user.username))

    @app.get(_BOOK + "/validate")
    @csrf.exempt
    @login_required
    def validate_book(book):
        _authorize(auth_store, "GET", book)
        return jsonify(books.validate(book))

    @app.get(_BOOK + "/graph")
    @csrf.exempt
    @login_required
    def book_graph(book):
        _authorize(auth_store, "GET", book)
        return jsonify(books.graph(book))

    # -- plotlines -----------------------------------------------------------

    @app.post(_PLOTLINE)
    @csrf.exempt
    @login_required
    def create_plotline(book, plotline):
        _authorize(auth_store, "POST", book)
        result = plotlines.create(
            book, plotline, request.get_json(silent=True) or {}, current_user.username
        )
        return _resp(result, 201)

    @app.get(_PLOTLINE)
    @csrf.exempt
    @login_required
    def get_plotline(book, plotline):
        _authorize(auth_store, "GET", book)
        expand = request.args.get("expand") == "events"
        return _resp(plotlines.get(book, plotline, expand=expand))

    @app.put(_PLOTLINE)
    @csrf.exempt
    @login_required
    def update_plotline(book, plotline):
        _authorize(auth_store, "PUT", book)
        result = plotlines.update(
            book, plotline, request.get_json(silent=True) or {}, _expected_rev(),
            current_user.username,
        )
        return _resp(result)

    @app.post(_PLOTLINE + "/inline")
    @csrf.exempt
    @login_required
    def inline_plotline(book, plotline):
        _authorize(auth_store, "PUT", book)
        return _resp(plotlines.inline(book, plotline, _expected_rev(), current_user.username))

    @app.delete(_PLOTLINE)
    @csrf.exempt
    @login_required
    def delete_plotline(book, plotline):
        _authorize(auth_store, "DELETE", book)
        plotlines.delete(
            book, plotline, _expected_rev(), current_user.username,
            inline_dependents=_truthy(request.args.get("inline")),
        )
        return "", 204

    # -- events --------------------------------------------------------------

    @app.post(_EVENT)
    @csrf.exempt
    @login_required
    def create_event(book, event):
        _authorize(auth_store, "POST", book)
        result = events.create(
            book, event, request.get_json(silent=True) or {}, current_user.username
        )
        return _resp(result, 201)

    @app.get(_EVENT)
    @csrf.exempt
    @login_required
    def get_event(book, event):
        _authorize(auth_store, "GET", book)
        return _resp(events.get(book, event))

    @app.put(_EVENT)
    @csrf.exempt
    @login_required
    def update_event(book, event):
        _authorize(auth_store, "PUT", book)
        result = events.update(
            book, event, request.get_json(silent=True) or {}, _expected_rev(),
            current_user.username,
        )
        return _resp(result)

    @app.delete(_EVENT)
    @csrf.exempt
    @login_required
    def delete_event(book, event):
        _authorize(auth_store, "DELETE", book)
        events.delete(
            book, event, _expected_rev(), current_user.username,
            detach=_truthy(request.args.get("detach")),
        )
        return "", 204

    @app.get(_EVENT + "/plotlines")
    @csrf.exempt
    @login_required
    def event_neighborhood(book, event):
        _authorize(auth_store, "GET", book)
        return jsonify(events.neighborhood(book, event, relation=request.args.get("relation")))

    # -- collaborators (book owners only, §7.5/§8.2) -------------------------

    @app.put(_BOOK + "/collaborators/<username>")
    @csrf.exempt
    @login_required
    def add_collaborator(book, username):
        _require_owner(auth_store, book)
        role = (request.get_json(silent=True) or {}).get("role", "editor")
        perms = _ROLE_PERMS.get(role)
        if perms is None:
            raise Forbidden(f"Unknown role '{role}'.")
        _replace_book_grants(auth_store, username, book)
        auth_store.add_grant(
            username, book, None, None, perms,
            granted_by=current_user.username, resource_type=BOOK_RESOURCE,
        )
        return jsonify({"book": book, "user": username, "role": role})

    @app.delete(_BOOK + "/collaborators/<username>")
    @csrf.exempt
    @login_required
    def remove_collaborator(book, username):
        _require_owner(auth_store, book)
        _replace_book_grants(auth_store, username, book)
        return "", 204


def _require_owner(auth_store, book: str) -> None:
    if not _is_owner(auth_store, book):
        raise Forbidden(f"Only an owner may manage collaborators on '{book}'.")


def _replace_book_grants(auth_store, username: str, book: str) -> None:
    """Drop this user's existing grants on *this book* (idempotent invite).

    Scoped to ``BOOK_RESOURCE`` so a user's akasha grants -- which may
    share the same name -- are never touched.
    """
    for grant in auth_store.grants_for(username):
        if (
            grant.get("resource_type") == BOOK_RESOURCE
            and grant.get("database") == book
            and grant.get("collection") is None
            and grant.get("doc_id") is None
        ):
            auth_store.delete_grant(grant["id"])


def _register_error_handler(app):
    @app.errorhandler(ChronosError)
    def handle(err: ChronosError):
        return jsonify(err.to_dict()), err.status_code

    @app.errorhandler(AkashaError)
    def handle_auth(err: AkashaError):
        # The shared auth routes (login/register/change-password) raise akasha
        # domain errors; serialise them consistently on this service too.
        return jsonify({"error": err.message}), err.status_code
