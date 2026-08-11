"""Flask application factory for Chronos (design §6.4).

``create_app`` receives its seams by injection -- the ``StoryStore`` and
``EntityGate`` plus the shared ``AuthStore`` -- so the same routing runs against
an in-memory Mongo in tests and a real one in production. Authentication and the
grant model are reused from ``akasha`` unchanged (one identity, one
login -- design decision in §12); Chronos authorizes at **book scope** using the
same allow-only, most-specific-wins ``is_allowed`` logic.
"""

from flask import Flask, jsonify, render_template, request
from flask_login import current_user, login_required
from flask_wtf.csrf import CSRFProtect

from visualizer.akasha.browsing import can_read_in_database, visible_collections
from visualizer.auth import (
    build_limiter,
    init_login,
    register_auth_routes,
    register_service_links,
)
from visualizer.auth.authz import ALL_PERMS, is_allowed, perm_for_method
from visualizer.auth.errors import AuthError
from visualizer.shared_assets import register_shared_assets

from .entity_gate import EntityGate
from .errors import ChronosError, Forbidden, InvalidRevision, InvalidTimeframe
from .presenters import with_permissions
from .services import BookService, EventService, PlotlineService, VisualizerService
from .store import StoryStore

_BOOK = "/books/<book>"
_PLOTLINE = "/books/<book>/plotlines/<plotline>"
_EVENT = "/books/<book>/events/<event>"

# Chronos grants are namespaced by this resource kind in the shared `_auth`
# store, so a book named "x" never confers access to a akasha database
# named "x" (and vice versa). See visualizer.auth.authz.
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
    akasha_url: str = "http://localhost:5002",
    chronos_url: str = "http://localhost:5003",
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
    # The read-only visualiser (below) is the HTML home a browser login lands on.
    register_auth_routes(app, auth_store, csrf, limiter, home_endpoint="index")
    register_service_links(app, akasha_url, chronos_url, current="chronos")
    register_shared_assets(app)

    books = BookService(story_store, entity_gate)
    plotlines = PlotlineService(story_store, entity_gate)
    events = EventService(story_store, entity_gate)
    visualizer = VisualizerService(story_store, entity_gate)

    _register_routes(app, csrf, auth_store, books, plotlines, events, visualizer)
    _register_ui_routes(app, csrf, auth_store, visualizer)
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


def _register_routes(app, csrf, auth_store, books, plotlines, events, visualizer):
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
        # The visualiser asks for the book before it draws anything, so this is
        # where it learns whether to offer editing at all.
        return _resp(with_permissions(
            books.get(book),
            write=_book_allowed(auth_store, "write", book),
            delete=_is_owner(auth_store, book),
        ))

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
        # Only once the book is really gone: a refused delete must leave the
        # owner able to try again.
        _revoke_book_grants(auth_store, book)
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

    @app.get(_BOOK + "/events")
    @csrf.exempt
    @login_required
    def list_events(book):
        """The book's scenes in story order -- summaries, filtered and paged.

        Lives on the core API rather than under ``/ui`` because "what scenes are
        in this book?" is a question any client has; the editor's picker is only
        its first caller. Full records come from ``GET .../events/<event>``.
        """
        _authorize(auth_store, "GET", book)
        return jsonify(visualizer.browse_events(book, **_browse_args()))

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


def _revoke_book_grants(auth_store, book: str) -> None:
    """Drop every grant on a book, for every user, once the book itself is gone.

    Not mere tidiness. Deletes are hard and ids may be recreated (see
    ``store``), so a grant left behind is a grant on a *name* -- and the next
    writer to create a book under that name would silently inherit the previous
    owner and all their collaborators, with no invite and nothing on screen to
    say so. Scoped to ``BOOK_RESOURCE``, so akasha grants that happen to share
    the name are untouched.
    """
    auth_store.delete_grants_on(book, None, None, resource_type=BOOK_RESOURCE)


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


# -- visualiser UI -----------------------------------------------------------

# How many article suggestions the picker offers at once.
_SUGGEST_LIMIT = 20


def _register_ui_routes(app, csrf, auth_store, visualizer):
    """The single-page plotline visualiser: an HTML shell plus its helper seams.

    The SPA (served at ``/``) reads and writes plotlines/events through the
    existing JSON API, and adds the book-scoped helpers that API lacks: ordered,
    filtered, paginated listings of plotlines and scenes; a proxy that reads (and
    searches) referenced Akasha articles so the browser stays same-origin; and a
    preview that costs nothing, so the editor can show what a candidate ordering
    would do before it is saved.

    Every write the editor performs goes through the ordinary plotline/event
    routes above -- ``If-Match`` and all -- so there is one write path, not two.
    """

    @app.get("/")
    @login_required
    def index():
        return render_template("visualizer.html")

    @app.get(_BOOK + "/ui/plotlines")
    @csrf.exempt
    @login_required
    def ui_list_plotlines(book):
        _authorize(auth_store, "GET", book)
        return jsonify(visualizer.browse_plotlines(book, **_browse_args()))

    @app.post(_BOOK + "/ui/plotline-preview")
    @csrf.exempt
    @login_required
    def ui_preview_plotline(book):
        # Writes nothing, but it is an editing affordance: gate it on the
        # permission the save will need, so the UI cannot preview happily and
        # then be refused.
        _authorize(auth_store, "POST", book)
        return jsonify(visualizer.preview_plotline(book, request.get_json(silent=True) or {}))

    @app.get(_BOOK + "/ui/entity/<database>/<collection>/<entity_id>")
    @csrf.exempt
    @login_required
    def ui_fetch_entity(book, database, collection, entity_id):
        # Two gates. You must be able to read the *book* (checked first, so an
        # unreadable book never leaks whether the article exists)...
        _authorize(auth_store, "GET", book)
        # ...and hold Akasha read permission on the *article itself*, so the
        # proxy never exposes something Akasha would refuse you directly.
        _authorize_entity_read(auth_store, database, collection, entity_id)
        return jsonify(visualizer.fetch_entity(database, collection, entity_id))

    @app.get(_BOOK + "/ui/ticks")
    @csrf.exempt
    @login_required
    def ui_format_ticks(book):
        """What the book's calendar calls these ticks -- the scene form's live
        "240 means Day 11" hint. One way only: labels are formatted here because
        a fantasy calendar cannot be parsed back (see calendar.py)."""
        _authorize(auth_store, "GET", book)
        return jsonify(visualizer.format_ticks(book, _ticks_arg()))

    @app.get("/ui/worlds")
    @csrf.exempt
    @login_required
    def ui_list_worlds():
        """The Akasha worlds this writer may draw a book's cast from.

        Not book-scoped, unlike every other ``/ui`` helper: the writer picks a
        world while *creating* a book, when there is no book to authorize
        against. So the only gate is the Akasha one -- each world, and each
        category within it, appears exactly when the caller could read
        something in it, which is the same rule Akasha's own browse applies.
        """
        grants = auth_store.grants_for(current_user.username)
        offered = []
        for world in visualizer.list_worlds():
            database = world["database"]
            if not can_read_in_database(grants, database):
                continue
            offered.append({
                "database": database,
                "collections": visible_collections(grants, database, world["collections"]),
            })
        return jsonify({"worlds": offered})

    @app.get(_BOOK + "/ui/entities")
    @csrf.exempt
    @login_required
    def ui_search_entities(book):
        """Type-ahead over the articles a new scene could reference."""
        _authorize(auth_store, "GET", book)
        found = visualizer.search_entities(
            book,
            collection=request.args.get("collection", "characters"),
            query=(request.args.get("q") or "").strip(),
            database=request.args.get("database") or None,
        )
        # The same per-article gate the fetch proxy applies, now over a list: a
        # picker must never suggest something Akasha would refuse to open.
        found["results"] = [
            r for r in found["results"]
            if _may_read_entity(auth_store, r["database"], r["collection"], r["id"])
        ][:_SUGGEST_LIMIT]
        return jsonify(found)


# A timeframe has two ends; a couple of spare slots cost nothing and keep one
# caller from asking for a thousand labels.
_MAX_TICKS = 8


def _ticks_arg() -> list[int]:
    """The ``?tick=`` values, as integers. Non-integers are a client bug, not a
    story problem, so they are rejected rather than quietly dropped."""
    raw = request.args.getlist("tick")[:_MAX_TICKS]
    try:
        return [int(value) for value in raw]
    except (TypeError, ValueError):
        raise InvalidTimeframe("Each 'tick' must be an integer.")


def _browse_args() -> dict:
    """The filter/page/per_page trio every browse endpoint accepts."""
    return {
        "query": request.args.get("filter", ""),
        "page": _positive_int(request.args.get("page"), 1),
        "per_page": _positive_int(request.args.get("per_page"), None),
    }


def _may_read_entity(auth_store, database: str, collection: str, entity_id: str) -> bool:
    """Whether Akasha would let this user read that article, mirroring Akasha's
    own document authorization: the default ``database`` grant hierarchy,
    everyone (admins included) subject to their grants. See visualizer.auth.authz."""
    grants = auth_store.grants_for(current_user.username)
    return is_allowed(grants, "read", database, collection, entity_id)


def _authorize_entity_read(auth_store, database: str, collection: str, entity_id: str) -> None:
    """Raise unless the current user may read the referenced article."""
    if not _may_read_entity(auth_store, database, collection, entity_id):
        raise Forbidden(
            f"You do not have 'read' permission on '{database}/{collection}/{entity_id}'."
        )


def _positive_int(raw, default):
    """Parse a positive int query arg, falling back to ``default`` when absent
    or malformed (the browser helpers clamp the value further)."""
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value >= 1 else default


def _register_error_handler(app):
    @app.errorhandler(ChronosError)
    def handle(err: ChronosError):
        return jsonify(err.to_dict()), err.status_code

    @app.errorhandler(AuthError)
    def handle_auth(err: AuthError):
        # The shared auth routes (login/register/change-password) raise auth
        # domain errors; serialise them consistently on this service too.
        return jsonify({"error": err.message}), err.status_code
