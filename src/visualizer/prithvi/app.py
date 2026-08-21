"""The Flask application factory for Prithvi.

The route layer and nothing else: work out who is asking, hand the request to
the service, and turn whatever comes back into a response. Two rules are
enforced here because they are properties of the *request* rather than of the
domain --

**Every route authorizes the world.** ``world`` is an Akasha database, so a map's
permissions are that database's permissions. There is no separate map grant to
issue, no world-owner concept to invent, and no way to reach a map in a world you
were never given.

**Every mutation carries ``If-Match``.** Absent is ``428``, stale is ``409``.
Making the precondition mandatory rather than optional is the difference between
a lost update being impossible and it being merely unlikely.

Which *pins* a reader may see is deliberately not decided here; that rule lives
in the service, where a new route cannot forget to ask for it.
"""

from flask import Flask, current_app, jsonify, make_response, request
from flask_login import current_user, login_required
from flask_wtf.csrf import CSRFProtect

from visualizer.akasha.browsing import DEFAULT_PER_PAGE, clamp_per_page
from visualizer.auth import (
    DATABASE_RESOURCE,
    AuthError,
    build_limiter,
    init_login,
    is_allowed,
    register_auth_routes,
    register_service_links,
)
from visualizer.observability import Observability

from .articles import ArticleGateway
from .errors import (
    Forbidden,
    InvalidRevision,
    PreconditionRequired,
    PrithviError,
    SvgTooLarge,
    UnsupportedMediaType,
)
from .models import ArticleRef
from .services import PrithviService
from .store import PrithviStore
from .svg import sanitize_svg

SVG_MEDIA_TYPE = "image/svg+xml"

_MAPS = "/worlds/<world>/maps"
_MAP = _MAPS + "/<map_name>"
_PIN = _MAP + "/pins/<collection>/<article>"


def create_app(
    store: PrithviStore,
    articles: ArticleGateway,
    auth_store,
    secret_key: str,
    *,
    max_svg_bytes: int = 5 * 1024 * 1024,
    secure_cookies: bool = False,
    rate_limit_storage_uri: str = "memory://",
    akasha_url: str = "http://localhost:5002",
    chronos_url: str = "http://localhost:5003",
    observability: Observability | None = None,
) -> Flask:
    if not secret_key:
        raise ValueError("create_app requires a non-empty secret_key.")
    if max_svg_bytes < 1:
        raise ValueError("create_app requires a positive max_svg_bytes.")

    app = Flask(__name__)
    app.secret_key = secret_key
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=secure_cookies,
        PRITHVI_MAX_SVG_BYTES=max_svg_bytes,
    )
    csrf = CSRFProtect(app)
    limiter = build_limiter(app, rate_limit_storage_uri)
    init_login(app, auth_store)
    # No HTML of our own, so a browser login has nowhere here to land: it falls
    # back to "/". The service links still matter, because the shared login page
    # is served by this app too and should say which service it belongs to.
    register_auth_routes(app, auth_store, csrf, limiter, home_endpoint=None)
    register_service_links(app, akasha_url, chronos_url, current="prithvi")

    service = PrithviService(
        store,
        articles,
        lambda upload: sanitize_svg(upload, max_svg_bytes),
        akasha_url,
    )
    _register_map_routes(app, csrf, auth_store, service)
    _register_pin_routes(app, csrf, auth_store, service)

    if observability is not None:
        observability.install(app, "prithvi")
    _register_error_handlers(app)
    return app


# -- maps ---------------------------------------------------------------------


def _register_map_routes(app, csrf, auth_store, service: PrithviService):
    @app.get("/health")
    @csrf.exempt
    def health():
        return jsonify({"status": "ok", "service": "prithvi"})

    @app.get(_MAPS)
    @csrf.exempt
    @login_required
    def list_maps(world):
        _authorize(auth_store, "read", world)
        return jsonify(_page("maps", service.list_maps(world)))

    @app.post(_MAP)
    @csrf.exempt
    @login_required
    def create_map(world, map_name):
        _authorize(auth_store, "write", world)
        result = service.create_map(world, map_name, _upload(), current_user.username)
        return _resource(result, 201)

    @app.get(_MAP)
    @csrf.exempt
    @login_required
    def get_map(world, map_name):
        _authorize(auth_store, "read", world)
        return _resource(service.get_map(world, map_name))

    @app.delete(_MAP)
    @csrf.exempt
    @login_required
    def delete_map(world, map_name):
        _authorize(auth_store, "delete", world)
        service.delete_map(world, map_name, _expected_rev(), current_user.username)
        return "", 204

    @app.get(_MAP + "/svg")
    @csrf.exempt
    @login_required
    def get_svg(world, map_name):
        _authorize(auth_store, "read", world)
        record = service.get_svg(world, map_name)
        return _svg(record["svg"], etag=f'"{record["rev"]}"')

    @app.put(_MAP + "/svg")
    @csrf.exempt
    @login_required
    def replace_svg(world, map_name):
        _authorize(auth_store, "write", world)
        result = service.replace_svg(
            world, map_name, _upload(), _expected_rev(), current_user.username
        )
        return _resource(result)

    @app.put(_MAP + "/scale")
    @csrf.exempt
    @login_required
    def set_scale(world, map_name):
        _authorize(auth_store, "write", world)
        result = service.set_scale(
            world,
            map_name,
            request.get_json(silent=True),
            _expected_rev(),
            current_user.username,
        )
        return _resource(result)

    @app.get(_MAP + "/render.svg")
    @csrf.exempt
    @login_required
    def render_map(world, map_name):
        _authorize(auth_store, "read", world)
        drawing = service.render(world, map_name, _may_read(auth_store))
        # Not cacheable by revision: two readers with different grants see
        # different pins on the same revision of the same map.
        return _svg(drawing, cache_control="no-store")

    @app.get(_MAP + "/versions")
    @csrf.exempt
    @login_required
    def map_versions(world, map_name):
        _authorize(auth_store, "read", world)
        return jsonify({"versions": service.map_history(world, map_name)})

    @app.get(_MAP + "/versions/<int:rev>")
    @csrf.exempt
    @login_required
    def map_version(world, map_name, rev):
        _authorize(auth_store, "read", world)
        return jsonify(service.map_revision(world, map_name, rev))

    @app.post(_MAP + "/restore/<int:rev>")
    @csrf.exempt
    @login_required
    def restore_map(world, map_name, rev):
        _authorize(auth_store, "write", world)
        result = service.restore_map(
            world, map_name, rev, _expected_rev(), current_user.username
        )
        return _resource(result)


# -- pins ---------------------------------------------------------------------


def _register_pin_routes(app, csrf, auth_store, service: PrithviService):
    @app.get(_MAP + "/pins")
    @csrf.exempt
    @login_required
    def list_pins(world, map_name):
        _authorize(auth_store, "read", world)
        pins = service.list_pins(world, map_name, _may_read(auth_store))
        return jsonify(_page("pins", pins))

    @app.post(_PIN)
    @csrf.exempt
    @login_required
    def create_pin(world, map_name, collection, article):
        _authorize(auth_store, "write", world)
        result = service.create_pin(
            world,
            map_name,
            collection,
            article,
            request.get_json(silent=True),
            _may_read(auth_store),
            current_user.username,
        )
        return _resource(result, 201)

    @app.get(_PIN)
    @csrf.exempt
    @login_required
    def get_pin(world, map_name, collection, article):
        _authorize(auth_store, "read", world)
        result = service.get_pin(
            world, map_name, collection, article, _may_read(auth_store)
        )
        return _resource(result)

    @app.put(_PIN)
    @csrf.exempt
    @login_required
    def update_pin(world, map_name, collection, article):
        _authorize(auth_store, "write", world)
        result = service.update_pin(
            world,
            map_name,
            collection,
            article,
            request.get_json(silent=True),
            _may_read(auth_store),
            _expected_rev(),
            current_user.username,
        )
        return _resource(result)

    @app.delete(_PIN)
    @csrf.exempt
    @login_required
    def delete_pin(world, map_name, collection, article):
        _authorize(auth_store, "write", world)
        service.delete_pin(
            world,
            map_name,
            collection,
            article,
            _may_read(auth_store),
            _expected_rev(),
            current_user.username,
        )
        return "", 204

    @app.get(_PIN + "/versions")
    @csrf.exempt
    @login_required
    def pin_versions(world, map_name, collection, article):
        _authorize(auth_store, "read", world)
        versions = service.pin_history(
            world, map_name, collection, article, _may_read(auth_store)
        )
        return jsonify({"versions": versions})

    @app.get(_PIN + "/versions/<int:rev>")
    @csrf.exempt
    @login_required
    def pin_version(world, map_name, collection, article, rev):
        _authorize(auth_store, "read", world)
        return jsonify(
            service.pin_revision(
                world, map_name, collection, article, rev, _may_read(auth_store)
            )
        )

    @app.post(_PIN + "/restore/<int:rev>")
    @csrf.exempt
    @login_required
    def restore_pin(world, map_name, collection, article, rev):
        _authorize(auth_store, "write", world)
        result = service.restore_pin(
            world,
            map_name,
            collection,
            article,
            rev,
            _may_read(auth_store),
            _expected_rev(),
            current_user.username,
        )
        return _resource(result)


# -- who is asking ------------------------------------------------------------


def _grants(auth_store):
    return auth_store.grants_for(current_user.username)


def _authorize(auth_store, permission: str, world: str) -> None:
    if not is_allowed(
        _grants(auth_store), permission, world, resource_type=DATABASE_RESOURCE
    ):
        raise Forbidden(
            f"You lack '{permission}' permission on the Akasha world '{world}'."
        )


def _may_read(auth_store):
    """A predicate the service uses to decide which pins this caller may see."""

    def may_read(ref: ArticleRef) -> bool:
        return is_allowed(
            _grants(auth_store),
            "read",
            ref.world,
            ref.collection,
            ref.article_id,
            resource_type=DATABASE_RESOURCE,
        )

    return may_read


# -- reading the request ------------------------------------------------------


def _upload() -> bytes:
    """The raw SVG body, refused early if it is the wrong type or too large.

    The cap is checked here and again inside the sanitizer. Here it is a memory
    guard, so an oversized upload is refused from its declared length before it
    is buffered; there it is the guarantee, because a declared length is only a
    claim. The alternative -- Flask's ``MAX_CONTENT_LENGTH`` -- is app-wide, and
    a small SVG limit would silently become a small *login* limit too.
    """
    if request.mimetype != SVG_MEDIA_TYPE:
        raise UnsupportedMediaType(f"Content-Type must be {SVG_MEDIA_TYPE}.")
    cap = current_app.config["PRITHVI_MAX_SVG_BYTES"]
    declared = request.content_length
    if declared is not None and declared > cap:
        raise SvgTooLarge(
            f"An SVG upload is at most {cap} bytes.",
            evidence={"bytes": declared, "max_bytes": cap},
        )
    return request.get_data(cache=False)


def _expected_rev() -> int:
    raw = request.headers.get("If-Match")
    if raw is None:
        raise PreconditionRequired(
            "This request must carry an If-Match header naming the revision "
            "you read."
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


def _page(key: str, rows: list[dict]) -> dict:
    """One page of ``rows``, in the shape and with the caps Akasha already uses.

    Out-of-range values are clamped rather than refused, for the reason browsing
    already gives: a filter can narrow the list under someone who was on page 4.
    """
    per_page = clamp_per_page(_int_arg("per_page", DEFAULT_PER_PAGE))
    total = len(rows)
    pages = max(1, -(-total // per_page))
    page = max(1, min(_int_arg("page", 1), pages))
    start = (page - 1) * per_page
    return {
        key: rows[start : start + per_page],
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
    }


def _int_arg(name: str, default: int) -> int:
    try:
        return int(request.args[name])
    except (KeyError, TypeError, ValueError):
        return default


# -- writing the response -----------------------------------------------------


def _resource(result: dict, status: int = 200):
    response = jsonify(result)
    response.status_code = status
    response.headers["ETag"] = f'"{result["rev"]}"'
    return response


def _svg(content: str, *, etag: str | None = None, cache_control: str | None = None):
    """An SVG served so a browser will draw it and nothing else.

    ``nosniff`` stops the document being re-interpreted as something with more
    privileges, and the policy denies every fetch and every script even if the
    sanitizer somehow let one through. Top-level navigation stays allowed, and
    only on a click, because a pin linking to its article is the point.
    """
    response = make_response(content)
    response.content_type = f"{SVG_MEDIA_TYPE}; charset=utf-8"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = (
        "sandbox allow-top-navigation-by-user-activation; "
        "default-src 'none'; style-src 'unsafe-inline'"
    )
    if etag is not None:
        response.headers["ETag"] = etag
    if cache_control is not None:
        response.headers["Cache-Control"] = cache_control
    return response


def _register_error_handlers(app):
    @app.errorhandler(PrithviError)
    def handle_prithvi(err: PrithviError):
        return jsonify(err.to_dict()), err.status_code

    @app.errorhandler(AuthError)
    def handle_auth(err: AuthError):
        return jsonify({"error": err.message}), err.status_code
