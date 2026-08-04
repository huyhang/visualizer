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

from visualizer.auth import (
    ALL_PERMS,
    DELETE,
    REGISTRATION_MODES,
    ROLE_PERMS,
    AuthError,
    AuthStore,
    Forbidden,
    InvalidEmail,
    UserNotFound,
    admin_required,
    build_limiter,
    generate_temp_password,
    init_login,
    is_allowed,
    owned_resources,
    perm_for_method,
    register_auth_routes,
    resources_shared_with,
    role_for_perms,
    validate_email,
    validate_password_strength,
)

from .browsing import rank_suggestions, visible_collections, visible_databases
from .diff import diff_documents
from .errors import (
    AkashaError,
    DocumentNotFound,
    InvalidRevision,
    ReservedName,
    VersionNotFound,
)
from .history import find_snapshot, history_meta
from .store import DocumentStore
from .validation import validate_document, validate_search_terms

_COLLECTION_ROUTE = "/databases/<database>/collections/<collection>"
_DOC_ROUTE = "/databases/<database>/collections/<collection>/documents/<doc_id>"
_SEARCH_ROUTE = "/databases/<database>/collections/<collection>/search"

# Per-IP limit for the self-service account endpoints. Looser than the auth
# limit (login/register) -- these are for a logged-in user tidying their own
# account, not a brute-force surface.
_ACCOUNT_RATE_LIMIT = "10 per minute; 60 per hour"


def create_app(
    store: DocumentStore,
    auth_store: AuthStore,
    secret_key: str,
    secure_cookies: bool = False,
    rate_limit_storage_uri: str = "memory://",
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

    _register_routes(app, store, auth_store, csrf)
    _register_browse_routes(app, store, auth_store, csrf)
    _register_version_routes(app, store, auth_store, csrf)
    _register_sharing_routes(app, auth_store, csrf)
    _register_account_routes(app, auth_store, csrf, limiter)
    _register_admin_routes(app, auth_store)
    _register_error_handlers(app)
    return app


def _reject_reserved(database: str) -> None:
    """Block access to internal/reserved databases (e.g. the auth store)."""
    if database.startswith("_"):
        raise ReservedName(f"Database '{database}' is reserved and not accessible.")


def _authorize(auth_store: AuthStore, method: str, database, collection, doc_id=None) -> None:
    """Raise ``Forbidden`` unless the current user may perform ``method`` here.

    Everyone -- including admins -- must hold the matching permission
    (read/write/delete) at some scope covering the resource. The admin role
    governs *account and access management* (the ``/admin`` console), not content
    access: an admin sees another user's content only where explicitly granted.
    """
    _reject_reserved(database)
    perm = perm_for_method(method)
    grants = auth_store.grants_for(current_user.username)
    if not is_allowed(grants, perm, database, collection, doc_id):
        raise Forbidden(
            f"You do not have '{perm}' permission on this resource."
        )


def _can_read(auth_store: AuthStore, database, collection, doc_id=None) -> bool:
    """Whether the current user may read a resource (per their grants)."""
    grants = auth_store.grants_for(current_user.username)
    return is_allowed(grants, "read", database, collection, doc_id)


def _expected_rev() -> int | None:
    """Parse the optimistic-concurrency precondition the client sent, if any.

    Accepts an ``If-Match`` header (an ETag such as ``"5"``, or ``*`` for an
    unconditional write) or a ``_rev`` query param. Returns the expected
    revision as an int, or ``None`` for an unconditional write. The browser
    editor always sends one; raw API callers may omit it.
    """
    raw = request.headers.get("If-Match")
    if raw is None:
        raw = request.args.get("_rev")
    if raw is None:
        return None
    raw = raw.strip().strip('"')
    if raw in ("", "*"):
        return None
    try:
        return int(raw)
    except ValueError:
        raise InvalidRevision(f"Invalid If-Match/_rev precondition: {raw!r}.")


def _document_response(result: dict, status: int = 200):
    """JSON-encode a document result and expose its rev as an ``ETag`` header."""
    response = jsonify(result)
    response.status_code = status
    if "rev" in result:
        response.headers["ETag"] = f'"{result["rev"]}"'
    return response


def _register_routes(app: Flask, store: DocumentStore, auth_store: AuthStore, csrf) -> None:
    @app.get("/health")
    @csrf.exempt
    def health():
        return jsonify({"status": "ok"})

    @app.get("/")
    @login_required
    def index():
        # The single-page article editor replaces the old server-rendered home.
        return render_template("editor.html")

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
        result = store.create(
            database, collection, doc_id, document, author=current_user.username
        )
        # The creator owns the new document outright.
        auth_store.grant_owner(
            current_user.username, database, collection, doc_id, list(ALL_PERMS)
        )
        return _document_response(result, 201)

    @app.get(_DOC_ROUTE)
    @csrf.exempt
    @login_required
    def get(database, collection, doc_id):
        _authorize(auth_store, "GET", database, collection, doc_id)
        return _document_response(store.get(database, collection, doc_id))

    @app.put(_DOC_ROUTE)
    @csrf.exempt
    @login_required
    def update(database, collection, doc_id):
        _authorize(auth_store, "PUT", database, collection, doc_id)
        document = validate_document(request.get_json(silent=True))
        result = store.update(
            database,
            collection,
            doc_id,
            document,
            expected_rev=_expected_rev(),
            author=current_user.username,
        )
        return _document_response(result)

    @app.delete(_DOC_ROUTE)
    @csrf.exempt
    @login_required
    def delete(database, collection, doc_id):
        _authorize(auth_store, "DELETE", database, collection, doc_id)
        store.delete(
            database,
            collection,
            doc_id,
            expected_rev=_expected_rev(),
            author=current_user.username,
        )
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
    grants = auth_store.grants_for(current_user.username)
    return [
        r
        for r in results
        if is_allowed(grants, "read", database, collection, r["id"])
    ]


_SUGGEST_LIMIT = 12
_LIST_DEFAULT_LIMIT = 100
_LIST_MAX_LIMIT = 500


def _register_browse_routes(app: Flask, store: DocumentStore, auth_store: AuthStore, csrf) -> None:
    """Grant-filtered listing of databases, collections and documents, plus the
    link-suggestion type-ahead used by the editor."""

    @app.get("/databases")
    @csrf.exempt
    @login_required
    def list_databases():
        databases = visible_databases(
            auth_store.grants_for(current_user.username), store.list_databases()
        )
        return jsonify({"databases": databases})

    @app.get("/databases/<database>/collections")
    @csrf.exempt
    @login_required
    def list_collections(database):
        _reject_reserved(database)
        collections = visible_collections(
            auth_store.grants_for(current_user.username),
            database,
            store.list_collections(database),
        )
        return jsonify({"database": database, "collections": collections})

    @app.get("/databases/<database>/collections/<collection>/documents")
    @csrf.exempt
    @login_required
    def list_documents(database, collection):
        _reject_reserved(database)
        limit = _parse_limit(request.args.get("limit"))
        after = request.args.get("after") or None
        docs = store.list_documents(database, collection, limit=limit, after=after)
        items = [
            _document_preview(database, collection, doc)
            for doc in docs
            if _can_read(auth_store, database, collection, doc["id"])
        ]
        return jsonify(
            {"database": database, "collection": collection, "documents": items}
        )

    @app.get("/suggest")
    @csrf.exempt
    @login_required
    def suggest():
        query = (request.args.get("q") or "").strip()
        if not query:
            return jsonify({"suggestions": []})
        current_db = request.args.get("db") or None
        current_col = request.args.get("col") or None
        matches = _gather_suggestions(store, auth_store, query)
        ranked = rank_suggestions(matches, current_db, current_col)
        return jsonify({"suggestions": ranked[:_SUGGEST_LIMIT]})


def _parse_limit(raw: str | None) -> int:
    if not raw:
        return _LIST_DEFAULT_LIMIT
    try:
        return max(1, min(_LIST_MAX_LIMIT, int(raw)))
    except ValueError:
        return _LIST_DEFAULT_LIMIT


def _document_preview(database, collection, doc: dict) -> dict:
    """Lightweight browse entry: id (slug), title if present, and rev."""
    body = doc.get("document", {})
    return {
        "id": doc["id"],
        "title": body.get("title"),
        "database": database,
        "collection": collection,
        "rev": doc.get("rev"),
    }


def _visible_namespaces(store: DocumentStore, auth_store: AuthStore):
    """Yield (database, collection) pairs the current user may read within."""
    grants = auth_store.grants_for(current_user.username)
    databases = visible_databases(grants, store.list_databases())
    for database in databases:
        collections = visible_collections(
            grants, database, store.list_collections(database)
        )
        for collection in collections:
            yield database, collection


def _gather_suggestions(store: DocumentStore, auth_store: AuthStore, query: str) -> list[dict]:
    """Find readable articles whose slug or title matches ``query``."""
    needle = query.lower()
    matches: list[dict] = []
    for database, collection in _visible_namespaces(store, auth_store):
        for doc in store.search(database, collection, text=query):
            if not _can_read(auth_store, database, collection, doc["id"]):
                continue
            title = doc["document"].get("title")
            if needle in doc["id"].lower() or (title and needle in title.lower()):
                matches.append(
                    {
                        "slug": doc["id"],
                        "title": title,
                        "database": database,
                        "collection": collection,
                    }
                )
    return matches


def _register_version_routes(app: Flask, store: DocumentStore, auth_store: AuthStore, csrf) -> None:
    """Read-only version history + diff, and restore (a new revision)."""

    @app.get(_DOC_ROUTE + "/versions")
    @csrf.exempt
    @login_required
    def list_versions(database, collection, doc_id):
        _authorize(auth_store, "GET", database, collection, doc_id)
        history = store.history(database, collection, doc_id)
        return jsonify({"id": doc_id, "versions": history_meta(history)})

    @app.get(_DOC_ROUTE + "/versions/<int:rev>")
    @csrf.exempt
    @login_required
    def get_version(database, collection, doc_id, rev):
        _authorize(auth_store, "GET", database, collection, doc_id)
        snapshot = _require_snapshot(store, database, collection, doc_id, rev)
        return jsonify(snapshot)

    @app.get(_DOC_ROUTE + "/diff")
    @csrf.exempt
    @login_required
    def diff_versions(database, collection, doc_id):
        _authorize(auth_store, "GET", database, collection, doc_id)
        from_rev, to_rev = _parse_diff_revs(request.args)
        older = _require_snapshot(store, database, collection, doc_id, from_rev)
        newer = _require_snapshot(store, database, collection, doc_id, to_rev)
        return jsonify(
            {
                "id": doc_id,
                "from": _snapshot_meta(older),
                "to": _snapshot_meta(newer),
                "diff": diff_documents(older["document"] or {}, newer["document"] or {}),
            }
        )

    @app.post(_DOC_ROUTE + "/restore/<int:rev>")
    @csrf.exempt
    @login_required
    def restore_version(database, collection, doc_id, rev):
        _authorize(auth_store, "PUT", database, collection, doc_id)
        snapshot = _require_snapshot(store, database, collection, doc_id, rev)
        if snapshot["document"] is None:
            raise VersionNotFound(
                f"Version {rev} of '{doc_id}' is a deletion and cannot be restored."
            )
        result = _restore_body(store, database, collection, doc_id, snapshot["document"])
        return _document_response(result)


def _require_snapshot(store: DocumentStore, database, collection, doc_id, rev) -> dict:
    snapshot = find_snapshot(store.history(database, collection, doc_id), rev)
    if snapshot is None:
        raise VersionNotFound(
            f"Version {rev} of '{doc_id}' is not retained."
        )
    return snapshot


def _snapshot_meta(snapshot: dict) -> dict:
    return {k: snapshot.get(k) for k in ("rev", "op", "author", "timestamp")}


def _parse_diff_revs(args) -> tuple[int, int]:
    try:
        return int(args["from"]), int(args["to"])
    except (KeyError, ValueError, TypeError):
        raise InvalidRevision("Diff requires integer 'from' and 'to' revisions.")


def _restore_body(store: DocumentStore, database, collection, doc_id, body: dict) -> dict:
    """Re-apply an old body as a new revision (update if live, else revive)."""
    try:
        current = store.get(database, collection, doc_id)
        return store.update(
            database,
            collection,
            doc_id,
            body,
            expected_rev=current["rev"],
            author=current_user.username,
        )
    except DocumentNotFound:
        return store.create(
            database, collection, doc_id, body, author=current_user.username
        )


def _render_admin(auth_store: AuthStore, selected=None, new_credential=None):
    """Render the admin console. ``new_credential`` shows a just-generated
    temporary password once (never persisted or shown again)."""
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
        registration_mode=auth_store.get_registration_mode(),
        new_credential=new_credential,
    )


# -- owner-driven sharing ----------------------------------------------------


def _is_owner(auth_store: AuthStore, database, collection, doc_id=None) -> bool:
    """Whether the current user owns (holds ``delete`` on) this resource."""
    grants = auth_store.grants_for(current_user.username)
    return is_allowed(grants, DELETE, database, collection, doc_id)


def _require_owner(auth_store: AuthStore, database, collection, doc_id=None) -> None:
    """Only a resource's owner may manage who else can access it.

    Ownership is holding ``delete`` at the resource's scope -- which the creator
    gets automatically, and which a collection owner also holds over the
    documents beneath it. The admin role does *not* confer this: content access
    (and who may share it) follows ownership, not the admin console.
    """
    if not _is_owner(auth_store, database, collection, doc_id):
        raise Forbidden("Only the owner may manage sharing for this resource.")


def _replace_scope_grants(auth_store: AuthStore, username, database, collection, doc_id) -> None:
    """Drop ``username``'s grant at *exactly* this akasha scope (idempotent).

    Namespaced to akasha (the ``database`` resource type) and matched on the
    exact scope tuple, so re-sharing merely replaces the role and never touches
    a chronos grant or the user's access to a different collection/document.
    """
    for grant in auth_store.grants_on(database, collection, doc_id):
        if grant["username"] == username:
            auth_store.delete_grant(grant["id"])


def _collaborators(auth_store: AuthStore, database, collection, doc_id) -> list[dict]:
    """Everyone granted access to this exact scope, as ``{username, role}`` pairs.

    Sorted by username for a stable display order. Includes the owner's own
    grant; callers that render "who else can see this" filter themselves out.
    """
    people = [
        {"username": g["username"], "role": role_for_perms(g["perms"])}
        for g in auth_store.grants_on(database, collection, doc_id)
    ]
    return sorted(people, key=lambda p: p["username"])


def _share(auth_store: AuthStore, database, collection, doc_id, username):
    """Grant ``username`` a role on a resource the current user owns."""
    _reject_reserved(database)
    _require_owner(auth_store, database, collection, doc_id)
    if auth_store.get_user(username) is None:
        raise UserNotFound(f"User '{username}' does not exist.")
    if username == current_user.username:
        # You already own it; sharing with yourself could only *reduce* your own
        # access, so refuse rather than risk locking an owner out.
        raise Forbidden("You already own this resource.")
    role = (request.get_json(silent=True) or {}).get("role", "editor")
    perms = ROLE_PERMS.get(role)
    if perms is None:
        raise Forbidden(f"Unknown role '{role}'.")
    _replace_scope_grants(auth_store, username, database, collection, doc_id)
    auth_store.add_grant(
        username,
        database,
        collection,
        doc_id,
        list(perms),
        granted_by=current_user.username,
    )
    return jsonify(
        {
            "database": database,
            "collection": collection,
            "doc_id": doc_id,
            "user": username,
            "role": role,
        }
    )


def _unshare(auth_store: AuthStore, database, collection, doc_id, username):
    """Revoke ``username``'s access to a resource the current user owns."""
    _reject_reserved(database)
    _require_owner(auth_store, database, collection, doc_id)
    _replace_scope_grants(auth_store, username, database, collection, doc_id)
    return "", 204


def _register_sharing_routes(app: Flask, auth_store: AuthStore, csrf) -> None:
    """Owner-driven sharing: a resource's owner grants others reader/editor/owner
    access to a collection or a single document -- without needing an admin.
    Mirrors the collaborator model chronos already uses for books."""

    _COLLAB = "/collaborators"

    @app.get(_COLLECTION_ROUTE + _COLLAB)
    @csrf.exempt
    @login_required
    def list_collection_collaborators(database, collection):
        _reject_reserved(database)
        _require_owner(auth_store, database, collection, None)
        return jsonify(
            {"collaborators": _collaborators(auth_store, database, collection, None)}
        )

    @app.put(_COLLECTION_ROUTE + _COLLAB + "/<username>")
    @csrf.exempt
    @login_required
    def add_collection_collaborator(database, collection, username):
        return _share(auth_store, database, collection, None, username)

    @app.delete(_COLLECTION_ROUTE + _COLLAB + "/<username>")
    @csrf.exempt
    @login_required
    def remove_collection_collaborator(database, collection, username):
        return _unshare(auth_store, database, collection, None, username)

    @app.get(_DOC_ROUTE + _COLLAB)
    @csrf.exempt
    @login_required
    def list_document_collaborators(database, collection, doc_id):
        _reject_reserved(database)
        _require_owner(auth_store, database, collection, doc_id)
        return jsonify(
            {"collaborators": _collaborators(auth_store, database, collection, doc_id)}
        )

    @app.put(_DOC_ROUTE + _COLLAB + "/<username>")
    @csrf.exempt
    @login_required
    def add_document_collaborator(database, collection, doc_id, username):
        return _share(auth_store, database, collection, doc_id, username)

    @app.delete(_DOC_ROUTE + _COLLAB + "/<username>")
    @csrf.exempt
    @login_required
    def remove_document_collaborator(database, collection, doc_id, username):
        return _unshare(auth_store, database, collection, doc_id, username)


# -- self-service account management ------------------------------------------


def _account_field(name: str):
    """Read a field from a JSON body (API) or an HTML form (browser)."""
    if request.is_json:
        return (request.get_json(silent=True) or {}).get(name)
    return request.form.get(name)


def _render_account(auth_store: AuthStore):
    """Render the account page: profile plus a compact list of the resources the
    user owns. Each resource's collaborators are loaded on demand (see the page's
    ``/collaborators`` fetch), so this stays cheap no matter how much is owned."""
    username = current_user.username
    record = auth_store.get_user(username) or {}
    grants = auth_store.grants_for(username)
    owned = []
    for scope in owned_resources(grants):
        # The GET-collaborators URL doubles as the base for the PUT/DELETE the
        # page's sharing controls call (append ``/<username>``).
        if scope["doc_id"] is None:
            collab_url = url_for(
                "list_collection_collaborators",
                database=scope["database"],
                collection=scope["collection"],
            )
        else:
            collab_url = url_for(
                "list_document_collaborators",
                database=scope["database"],
                collection=scope["collection"],
                doc_id=scope["doc_id"],
            )
        owned.append({**scope, "collab_url": collab_url})
    return render_template(
        "account.html",
        username=username,
        email=record.get("email"),
        role=record.get("role", "user"),
        # Split by scope so the page can offer a collection view and an article
        # view as separate, filterable/paginated modes.
        owned_collections=[r for r in owned if r["doc_id"] is None],
        owned_articles=[r for r in owned if r["doc_id"] is not None],
        contacts=auth_store.list_contacts(username),
        shared_with_me=resources_shared_with(grants, username),
        roles=list(ROLE_PERMS.keys()),
    )


def _register_account_routes(app: Flask, auth_store: AuthStore, csrf, limiter) -> None:
    """Let any logged-in user view their account and change their own email.
    (Password changes live in the shared auth routes.)"""

    def limit(view):
        return limiter.limit(_ACCOUNT_RATE_LIMIT)(view) if limiter is not None else view

    @app.get("/account")
    @login_required
    def account_page():
        return _render_account(auth_store)

    @app.post("/account/email")
    @csrf.exempt
    @limit
    @login_required
    def update_own_email():
        username = current_user.username
        raw = (_account_field("email") or "").strip()
        if not raw:
            if request.is_json:
                raise InvalidEmail("An email address is required.")
            flash("Enter an email address.", "error")
            return redirect(url_for("account_page"))
        try:
            email = validate_email(raw)
            auth_store.update_user(username, email=email)
        except (AkashaError, AuthError) as err:
            if request.is_json:
                raise
            flash(err.message, "error")
            return redirect(url_for("account_page"))
        if request.is_json:
            return {"username": username, "email": email}
        flash("Your email address was updated.", "success")
        return redirect(url_for("account_page"))

    @app.get("/account/contacts")
    @csrf.exempt
    @login_required
    def list_contacts():
        """The current user's collaborator roster (for the sharing pickers)."""
        return {"contacts": auth_store.list_contacts(current_user.username)}

    @app.post("/account/contacts")
    @login_required
    def add_contact():
        username = (request.form.get("username") or "").strip()
        if not username:
            flash("Enter a username to add.", "error")
            return redirect(url_for("account_page"))
        if username == current_user.username:
            flash("You cannot add yourself as a collaborator.", "error")
            return redirect(url_for("account_page"))
        try:
            auth_store.add_contact(current_user.username, username)
        except (AkashaError, AuthError) as err:
            flash(err.message, "error")
            return redirect(url_for("account_page"))
        flash(f"Added '{username}' to your collaborators.", "success")
        return redirect(url_for("account_page"))

    @app.post("/account/contacts/<username>/delete")
    @login_required
    def remove_contact(username):
        auth_store.remove_contact(current_user.username, username)
        return redirect(url_for("account_page"))


def _register_admin_routes(app: Flask, auth_store: AuthStore) -> None:
    @app.get("/admin")
    @admin_required
    def admin_page():
        return _render_admin(auth_store, selected=request.args.get("user") or None)

    @app.post("/admin/settings/registration")
    @admin_required
    def set_registration_mode():
        mode = request.form.get("mode", "")
        if mode not in REGISTRATION_MODES:
            flash("Unknown registration mode.", "error")
            return redirect(url_for("admin_page"))
        auth_store.set_registration_mode(mode)
        flash(f"Registration is now {mode}.", "success")
        return redirect(url_for("admin_page"))

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
                validate_password_strength(new_password, username)
                # An admin reset forces the user to change it again on next login.
                auth_store.set_password(
                    username,
                    generate_password_hash(new_password),
                    must_change_password=True,
                )
        except (AkashaError, AuthError) as err:
            flash(err.message, "error")
            return redirect(url_for("admin_page", user=username))
        flash(f"User '{username}' updated.", "success")
        return redirect(url_for("admin_page", user=username))

    @app.post("/admin/users/<username>/reset-password")
    @admin_required
    def reset_password(username):
        # One-click reset: generate a strong temporary password, force a change on
        # next login, and show it once so the admin can hand it over.
        if auth_store.get_user(username) is None:
            raise UserNotFound(f"User '{username}' does not exist.")
        temp_password = generate_temp_password()
        auth_store.set_password(
            username,
            generate_password_hash(temp_password),
            must_change_password=True,
        )
        return _render_admin(
            auth_store,
            selected=username,
            new_credential={"username": username, "password": temp_password},
        )

    @app.post("/admin/users")
    @admin_required
    def create_user_admin():
        username = (request.form.get("username") or "").strip()
        role = request.form.get("role", "user")
        password = request.form.get("password") or ""
        if not username:
            flash("A username is required.", "error")
            return redirect(url_for("admin_page"))
        if role not in ("admin", "user"):
            flash("Unknown role.", "error")
            return redirect(url_for("admin_page"))
        generated = None
        try:
            email_raw = (request.form.get("email") or "").strip()
            email = validate_email(email_raw) if email_raw else None
            if password:
                # An admin may set a specific password; it is still strength-checked.
                validate_password_strength(password, username)
            else:
                # The easy path: generate a strong temporary password to hand over.
                password = generated = generate_temp_password()
            auth_store.create_user(
                username,
                generate_password_hash(password),
                email=email,
                role=role,
                must_change_password=True,
            )
        except (AkashaError, AuthError) as err:
            flash(err.message, "error")
            return redirect(url_for("admin_page"))
        # Show a generated credential once, in-page (not via a redirect that would
        # expose the password in the URL/history).
        if generated is not None:
            return _render_admin(
                auth_store,
                selected=username,
                new_credential={"username": username, "password": generated},
            )
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
    @app.errorhandler(AkashaError)
    def handle_domain_error(err: AkashaError):
        return jsonify({"error": err.message}), err.status_code

    @app.errorhandler(AuthError)
    def handle_auth_error(err: AuthError):
        # Auth/access-control errors (login, grants, admin actions) now come from
        # the shared ``visualizer.auth`` package with their own base class.
        return jsonify({"error": err.message}), err.status_code
