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
"""

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash

from .auth import admin_required, init_login, register_auth_routes
from .auth_store import AuthStore
from .authz import ALL_PERMS, is_allowed, perm_for_method
from .errors import DocumentServerError, Forbidden, ReservedName, UserNotFound
from .store import DocumentStore
from .validation import validate_document, validate_email, validate_search_terms

_COLLECTION_ROUTE = "/databases/<database>/collections/<collection>"
_DOC_ROUTE = "/databases/<database>/collections/<collection>/documents/<doc_id>"
_SEARCH_ROUTE = "/databases/<database>/collections/<collection>/search"


def create_app(
    store: DocumentStore,
    auth_store: AuthStore,
    secret_key: str,
    secure_cookies: bool = False,
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
    init_login(app, auth_store)
    register_auth_routes(app, auth_store, csrf)

    _register_routes(app, store, auth_store, csrf)
    _register_admin_routes(app, auth_store)
    _register_error_handlers(app)
    return app


def _reject_reserved(database: str) -> None:
    """Block access to internal/reserved databases (e.g. the auth store)."""
    if database.startswith("_"):
        raise ReservedName(f"Database '{database}' is reserved and not accessible.")


def _authorize(auth_store: AuthStore, method: str, database, collection, doc_id=None) -> None:
    """Raise ``Forbidden`` unless the current user may perform ``method`` here.

    Admins bypass grant checks; everyone else must hold the matching permission
    (read/write/delete) at some scope covering the resource.
    """
    _reject_reserved(database)
    if current_user.is_admin:
        return
    perm = perm_for_method(method)
    grants = auth_store.grants_for(current_user.username)
    if not is_allowed(grants, perm, database, collection, doc_id):
        raise Forbidden(
            f"You do not have '{perm}' permission on this resource."
        )


def _register_routes(app: Flask, store: DocumentStore, auth_store: AuthStore, csrf) -> None:
    @app.get("/health")
    @csrf.exempt
    def health():
        return jsonify({"status": "ok"})

    @app.get("/")
    @login_required
    def index():
        return render_template("index.html")

    @app.post(_COLLECTION_ROUTE)
    @csrf.exempt
    @login_required
    def create_collection(database, collection):
        # Any authenticated user may create a namespace and owns what they make.
        _reject_reserved(database)
        result = store.create_collection(database, collection)
        auth_store.grant_owner(
            current_user.username, database, collection, None, list(ALL_PERMS)
        )
        return jsonify(result), 201

    @app.post(_DOC_ROUTE)
    @csrf.exempt
    @login_required
    def create(database, collection, doc_id):
        _authorize(auth_store, "POST", database, collection, doc_id)
        document = validate_document(request.get_json(silent=True))
        result = store.create(database, collection, doc_id, document)
        # The creator owns the new document outright.
        auth_store.grant_owner(
            current_user.username, database, collection, doc_id, list(ALL_PERMS)
        )
        return jsonify(result), 201

    @app.get(_DOC_ROUTE)
    @csrf.exempt
    @login_required
    def get(database, collection, doc_id):
        _authorize(auth_store, "GET", database, collection, doc_id)
        return jsonify(store.get(database, collection, doc_id))

    @app.put(_DOC_ROUTE)
    @csrf.exempt
    @login_required
    def update(database, collection, doc_id):
        _authorize(auth_store, "PUT", database, collection, doc_id)
        document = validate_document(request.get_json(silent=True))
        return jsonify(store.update(database, collection, doc_id, document))

    @app.delete(_DOC_ROUTE)
    @csrf.exempt
    @login_required
    def delete(database, collection, doc_id):
        _authorize(auth_store, "DELETE", database, collection, doc_id)
        store.delete(database, collection, doc_id)
        return "", 204

    @app.get(_SEARCH_ROUTE)
    @csrf.exempt
    @login_required
    def search(database, collection):
        _reject_reserved(database)
        key, text = validate_search_terms(
            request.args.get("key"), request.args.get("text")
        )
        results = store.search(database, collection, key=key, text=text)
        results = _filter_readable(auth_store, database, collection, results)
        return jsonify({"results": results, "count": len(results)})


def _filter_readable(auth_store: AuthStore, database, collection, results):
    """Drop search results the current user is not allowed to read."""
    if current_user.is_admin:
        return results
    grants = auth_store.grants_for(current_user.username)
    return [
        r
        for r in results
        if is_allowed(grants, "read", database, collection, r["id"])
    ]


def _register_admin_routes(app: Flask, auth_store: AuthStore) -> None:
    @app.get("/admin")
    @admin_required
    def admin_page():
        selected = request.args.get("user") or None
        record = auth_store.get_user(selected) if selected else None
        grants = auth_store.grants_for(selected) if selected else []
        return render_template(
            "admin.html",
            users=auth_store.list_users(),
            selected=selected,
            selected_is_admin=bool(record and record.get("role") == "admin"),
            selected_email=record.get("email") if record else None,
            grants=grants,
            all_perms=ALL_PERMS,
        )

    @app.post("/admin/users/<username>/edit")
    @admin_required
    def edit_user(username):
        if auth_store.get_user(username) is None:
            raise UserNotFound(f"User '{username}' does not exist.")
        email_raw = (request.form.get("email") or "").strip()
        new_password = request.form.get("password") or ""
        if not email_raw and not new_password:
            flash("Nothing to update.", "error")
            return redirect(url_for("admin_page", user=username))
        try:
            if email_raw:
                auth_store.update_user(username, email=validate_email(email_raw))
            if new_password:
                auth_store.set_password(username, generate_password_hash(new_password))
        except DocumentServerError as err:
            flash(err.message, "error")
            return redirect(url_for("admin_page", user=username))
        flash(f"User '{username}' updated.", "success")
        return redirect(url_for("admin_page", user=username))

    @app.post("/admin/users")
    @admin_required
    def create_user_admin():
        username = request.form.get("username")
        password = request.form.get("password")
        role = request.form.get("role", "user")
        if not username or not password:
            flash("Username and password are required.", "error")
            return redirect(url_for("admin_page"))
        if role not in ("admin", "user"):
            flash("Unknown role.", "error")
            return redirect(url_for("admin_page"))
        try:
            email = validate_email(request.form.get("email"))
            auth_store.create_user(
                username, generate_password_hash(password), email=email, role=role
            )
        except DocumentServerError as err:
            flash(err.message, "error")
            return redirect(url_for("admin_page"))
        flash(f"User '{username}' created.", "success")
        return redirect(url_for("admin_page", user=username))

    @app.post("/admin/users/<username>/role")
    @admin_required
    def set_role(username):
        role = request.form.get("role", "user")
        if role not in ("admin", "user"):
            raise Forbidden("Unknown role.")
        if role != "admin" and _is_last_admin(auth_store, username):
            raise Forbidden("Cannot demote the last remaining admin.")
        auth_store.update_user(username, role=role)
        return redirect(url_for("admin_page", user=username))

    @app.post("/admin/users/<username>/active")
    @admin_required
    def set_active(username):
        active = request.form.get("active") == "true"
        if not active and _is_last_admin(auth_store, username):
            raise Forbidden("Cannot deactivate the last remaining admin.")
        auth_store.update_user(username, active=active)
        return redirect(url_for("admin_page", user=username))

    @app.post("/admin/users/<username>/delete")
    @admin_required
    def delete_user(username):
        if _is_last_admin(auth_store, username):
            raise Forbidden("Cannot delete the last remaining admin.")
        auth_store.delete_user(username)
        return redirect(url_for("admin_page"))

    @app.post("/admin/grants")
    @admin_required
    def add_grant():
        username = request.form.get("username")
        if not username or auth_store.get_user(username) is None:
            raise UserNotFound(f"User '{username}' does not exist.")
        perms = [p for p in request.form.getlist("perms") if p in ALL_PERMS]
        if not perms:
            raise Forbidden("Select at least one permission.")
        auth_store.add_grant(
            username,
            request.form.get("database") or None,
            request.form.get("collection") or None,
            request.form.get("doc_id") or None,
            perms,
            granted_by=current_user.username,
        )
        return redirect(url_for("admin_page", user=username))

    @app.post("/admin/grants/<grant_id>/delete")
    @admin_required
    def delete_grant(grant_id):
        auth_store.delete_grant(grant_id)
        return redirect(url_for("admin_page", user=request.form.get("user") or None))


def _is_last_admin(auth_store: AuthStore, username: str) -> bool:
    """Whether ``username`` is currently the only admin account."""
    record = auth_store.get_user(username)
    if record is None or record.get("role") != "admin":
        return False
    return auth_store.count_admins() <= 1


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(DocumentServerError)
    def handle_domain_error(err: DocumentServerError):
        return jsonify({"error": err.message}), err.status_code
