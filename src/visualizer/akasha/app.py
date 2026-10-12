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

from collections.abc import Callable

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash

from visualizer import sharing
from visualizer.auth import (
    ALL_PERMS,
    READ,
    REGISTRATION_MODES,
    ROLE_PERMS,
    WRITE,
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
    register_auth_routes,
    register_service_links,
    validate_email,
    validate_password_strength,
)
from visualizer.observability import Observability
from visualizer.observability.page import register_observability_page
from visualizer.shared_assets import register_shared_assets

from .access import (
    authorize,
    kind_for,
    require_owner,
    scope_for,
)
from .browsing import (
    DEFAULT_PER_PAGE,
    browse_articles,
    can_delete_collection,
    can_write_in_collection,
    most_recent,
    rank_suggestions,
    visible_collections,
    visible_databases,
)
from .diff import diff_documents
from .document_routes import register_document_routes
from .errors import (
    AkashaError,
    DocumentNotFound,
    InvalidRevision,
    MediaInUse,
    VersionNotFound,
)
from .history import find_snapshot, history_meta
from .labels import derive_title
from .media_routes import register_media_routes
from .media_service import MediaService
from .routing import (
    COLLECTION_ROUTE,
    DOC_ROUTE,
    document_response,
    int_arg,
    reject_reserved,
)
from .share_kinds import ACCOUNT_KINDS, account_kinds
from .store import DocumentStore
from .terms import TERMS

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


_SUGGEST_LIMIT = 12
_RECENT_DEFAULT = 8
_RECENT_MAX = 50


def register_browse_routes(app: Flask, store: DocumentStore, auth_store: AuthStore, csrf) -> None:
    """Grant-filtered listing of databases, collections and documents, the
    "recently edited" strip the home view opens with, and the link-suggestion
    type-ahead used by the editor.

    Each level answers with enough to *render a page* rather than just names: how
    much is inside, and whether the caller may add to it -- so the browser can
    show counts and hide buttons that would only earn a 403.
    """

    @app.get("/databases")
    @csrf.exempt
    @login_required
    def list_databases():
        grants = auth_store.grants_for(current_user.username)
        databases = visible_databases(grants, store.list_databases())
        return jsonify(
            {"databases": [_database_summary(store, grants, db) for db in databases]}
        )

    @app.get("/databases/<database>/collections")
    @csrf.exempt
    @login_required
    def list_collections(database):
        reject_reserved(database)
        grants = auth_store.grants_for(current_user.username)
        present = store.list_collections(database)
        collections = visible_collections(grants, database, present)
        return jsonify(
            {
                "database": database,
                "title": derive_title(database),
                "collections": [
                    _collection_summary(store, grants, database, collection)
                    for collection in collections
                ],
                # Whether the database is *actually* empty, not merely empty as
                # far as this caller can see. Seeing no collections usually means
                # you may not read the ones that are there, and offering to
                # delete a database in that state would be a lie.
                "empty": not present,
            }
        )

    @app.get("/databases/<database>/collections/<collection>/documents")
    @csrf.exempt
    @login_required
    def list_documents(database, collection):
        """One filtered, ordered page of the articles the caller may read.

        Filtering reaches the whole article, not just its title, so the box on a
        collection page is the full-text search the API always had and the
        browser never offered.
        """
        reject_reserved(database)
        grants = auth_store.grants_for(current_user.username)
        rows = _readable_rows(store, grants, database, collection)
        page = browse_articles(
            rows,
            request.args.get("filter", ""),
            int_arg("page", 1),
            int_arg("per_page", DEFAULT_PER_PAGE),
            # `match=name` narrows the filter to what an article is *called*.
            # The sidebar asks for it: it has no room to show why a body match
            # matched, and "king" hitting half the world is not a shortlist.
            names_only=request.args.get("match") == "name",
        )
        can_delete = can_delete_collection(grants, database, collection)
        can_write = can_write_in_collection(grants, database, collection)
        return jsonify(
            {
                "database": database,
                "collection": collection,
                "database_title": derive_title(database),
                "collection_title": derive_title(collection),
                "can_write": can_write,
                "can_delete": can_delete,
                # How many tombstones are here: what deleting the collection
                # would cost, and how many articles could be brought back.
                # Counted only for someone who could act on either.
                "deleted": (
                    store.count_deleted(database, collection)
                    if (can_write or can_delete) else 0
                ),
                **page,
            }
        )

    @app.get(COLLECTION_ROUTE + "/deleted")
    @csrf.exempt
    @login_required
    def list_deleted_documents(database, collection):
        """The articles deleted from this collection, and what would come back.

        Deletes are soft, so a tombstone still holds the history that makes it
        recoverable -- but nothing lists it, which until now meant a deleted
        article could only be found by already knowing its slug. Grant-filtered
        per article like every other listing, and each row says whether *this*
        caller may restore it, so the button is only drawn when it would work.
        """
        reject_reserved(database)
        grants = auth_store.grants_for(current_user.username)
        rows = [
            {
                **row,
                "database": database,
                "collection": collection,
                "can_restore": (
                    row["restore_rev"] is not None
                    and is_allowed(grants, WRITE, database, collection, row["id"])
                ),
            }
            for row in store.list_deleted(database, collection)
            if is_allowed(grants, READ, database, collection, row["id"])
        ]
        return jsonify(
            {"database": database, "collection": collection, "documents": rows}
        )

    @app.get("/recent")
    @csrf.exempt
    @login_required
    def recent_documents():
        """The articles written to most recently, newest first.

        Scans every readable namespace, the same reach ``/suggest`` has -- but
        once per visit to the home view rather than once per keystroke, which is
        what makes it affordable at the scale this runs.
        """
        limit = max(1, min(int_arg("limit", _RECENT_DEFAULT), _RECENT_MAX))
        grants = auth_store.grants_for(current_user.username)
        rows = [
            row
            for database, collection in _visible_namespaces(store, grants)
            for row in _readable_rows(store, grants, database, collection)
        ]
        return jsonify({"documents": most_recent(rows, limit)})

    @app.get("/suggest")
    @csrf.exempt
    @login_required
    def suggest():
        query = (request.args.get("q") or "").strip()
        if not query:
            return jsonify({"suggestions": []})
        current_db = request.args.get("db") or None
        current_col = request.args.get("col") or None
        grants = auth_store.grants_for(current_user.username)
        matches = _gather_suggestions(store, grants, query)
        ranked = rank_suggestions(matches, current_db, current_col)
        return jsonify({"suggestions": ranked[:_SUGGEST_LIMIT]})


def _field_values(body: dict) -> list[str]:
    """Every scalar the article holds, flattened -- the filter's haystack."""
    values: list[str] = []
    for value in body.values():
        if isinstance(value, list):
            values.extend(str(v) for v in value)
        elif value is not None:
            values.append(str(value))
    return values


def _article_row(database, collection, doc: dict) -> dict:
    """A browse row: what the list renders, plus the text the filter reads."""
    body = doc.get("document", {})
    return {
        "id": doc["id"],
        "title": body.get("title"),
        "database": database,
        "collection": collection,
        "database_title": derive_title(database),
        "collection_title": derive_title(collection),
        "rev": doc.get("rev"),
        "updated": doc.get("updated"),
        "author": doc.get("author"),
        "fields": _field_values(body),
    }


def _readable_rows(store: DocumentStore, grants, database, collection) -> list[dict]:
    """Browse rows for every article in a collection the user may read."""
    return [
        _article_row(database, collection, doc)
        for doc in store.list_documents(database, collection)
        if is_allowed(grants, READ, database, collection, doc["id"])
    ]


def _readable_count(store: DocumentStore, grants, database, collection) -> int:
    """How many articles the user can see in a collection.

    The ordinary case -- a grant covering the whole collection -- is a single
    count. Only someone holding document-scoped grants pays for a per-id check,
    and then we read ids alone rather than whole documents.
    """
    if is_allowed(grants, READ, database, collection, None):
        return store.count_documents(database, collection)
    return sum(
        1
        for doc_id in store.document_ids(database, collection)
        if is_allowed(grants, READ, database, collection, doc_id)
    )


def _collection_summary(store: DocumentStore, grants, database, collection) -> dict:
    return {
        "name": collection,
        "title": derive_title(collection),
        "articles": _readable_count(store, grants, database, collection),
        "can_write": can_write_in_collection(grants, database, collection),
        "can_delete": can_delete_collection(grants, database, collection),
    }


def _database_summary(store: DocumentStore, grants, database) -> dict:
    collections = visible_collections(
        grants, database, store.list_collections(database)
    )
    return {
        "name": database,
        "title": derive_title(database),
        "collections": len(collections),
        "articles": sum(
            _readable_count(store, grants, database, collection)
            for collection in collections
        ),
    }


def _visible_namespaces(store: DocumentStore, grants):
    """Yield (database, collection) pairs the user may read within."""
    for database in visible_databases(grants, store.list_databases()):
        for collection in visible_collections(
            grants, database, store.list_collections(database)
        ):
            yield database, collection


def _gather_suggestions(store: DocumentStore, grants, query: str) -> list[dict]:
    """Find readable articles whose slug or title matches ``query``."""
    needle = query.lower()
    matches: list[dict] = []
    for database, collection in _visible_namespaces(store, grants):
        for doc in store.search(database, collection, text=query):
            if not is_allowed(grants, READ, database, collection, doc["id"]):
                continue
            title = doc["document"].get("title")
            if needle in doc["id"].lower() or (title and needle in title.lower()):
                matches.append(
                    {
                        "slug": doc["id"],
                        "title": title,
                        "database": database,
                        "collection": collection,
                        "database_title": derive_title(database),
                        "collection_title": derive_title(collection),
                    }
                )
    return matches


def register_version_routes(app: Flask, store: DocumentStore, auth_store: AuthStore, csrf) -> None:
    """Read-only version history + diff, and restore (a new revision)."""

    @app.get(DOC_ROUTE + "/versions")
    @csrf.exempt
    @login_required
    def list_versions(database, collection, doc_id):
        authorize(auth_store, "GET", database, collection, doc_id)
        history = store.history(database, collection, doc_id)
        return jsonify({"id": doc_id, "versions": history_meta(history)})

    @app.get(DOC_ROUTE + "/versions/<int:rev>")
    @csrf.exempt
    @login_required
    def get_version(database, collection, doc_id, rev):
        authorize(auth_store, "GET", database, collection, doc_id)
        snapshot = _require_snapshot(store, database, collection, doc_id, rev)
        return jsonify(snapshot)

    @app.get(DOC_ROUTE + "/diff")
    @csrf.exempt
    @login_required
    def diff_versions(database, collection, doc_id):
        authorize(auth_store, "GET", database, collection, doc_id)
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

    @app.post(DOC_ROUTE + "/restore/<int:rev>")
    @csrf.exempt
    @login_required
    def restore_version(database, collection, doc_id, rev):
        authorize(auth_store, "PUT", database, collection, doc_id)
        snapshot = _require_snapshot(store, database, collection, doc_id, rev)
        if snapshot["document"] is None:
            raise VersionNotFound(
                f"Version {rev} of '{doc_id}' is a deletion and cannot be restored."
            )
        result = _restore_body(store, database, collection, doc_id, snapshot["document"])
        return document_response(result)


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


def _collaborators(auth_store: AuthStore, database, collection, doc_id) -> list[dict]:
    return sharing.collaborators(
        auth_store, kind_for(collection, doc_id), scope_for(database, collection, doc_id)
    )


def _share(auth_store: AuthStore, database, collection, doc_id, username):
    """Grant ``username`` a role on a resource the current user owns.

    The resource-shaped spelling of the same operation the account page reaches
    through ``/account/sharing/...``; both run ``visualizer.sharing.share``.
    """
    kind = kind_for(collection, doc_id)
    role = (request.get_json(silent=True) or {}).get("role", kind.default_role)
    return jsonify(sharing.share(
        auth_store, kind, scope_for(database, collection, doc_id), username, role,
        me=current_user.username,
    ))


def _unshare(auth_store: AuthStore, database, collection, doc_id, username):
    """Revoke ``username``'s access to a resource the current user owns."""
    sharing.unshare(
        auth_store, kind_for(collection, doc_id), scope_for(database, collection, doc_id),
        username, me=current_user.username,
    )
    return "", 204


def register_collaborator_routes(app: Flask, auth_store: AuthStore, csrf) -> None:
    """Owner-driven sharing: a resource's owner grants others reader/editor/owner
    access to a collection or a single document -- without needing an admin.
    Mirrors the collaborator model chronos already uses for books."""

    _COLLAB = "/collaborators"

    @app.get(COLLECTION_ROUTE + _COLLAB)
    @csrf.exempt
    @login_required
    def list_collection_collaborators(database, collection):
        reject_reserved(database)
        require_owner(auth_store, database, collection, None)
        return jsonify(
            {"collaborators": _collaborators(auth_store, database, collection, None)}
        )

    @app.put(COLLECTION_ROUTE + _COLLAB + "/<username>")
    @csrf.exempt
    @login_required
    def add_collection_collaborator(database, collection, username):
        return _share(auth_store, database, collection, None, username)

    @app.delete(COLLECTION_ROUTE + _COLLAB + "/<username>")
    @csrf.exempt
    @login_required
    def remove_collection_collaborator(database, collection, username):
        return _unshare(auth_store, database, collection, None, username)

    @app.get(DOC_ROUTE + _COLLAB)
    @csrf.exempt
    @login_required
    def list_document_collaborators(database, collection, doc_id):
        reject_reserved(database)
        require_owner(auth_store, database, collection, doc_id)
        return jsonify(
            {"collaborators": _collaborators(auth_store, database, collection, doc_id)}
        )

    @app.put(DOC_ROUTE + _COLLAB + "/<username>")
    @csrf.exempt
    @login_required
    def add_document_collaborator(database, collection, doc_id, username):
        return _share(auth_store, database, collection, doc_id, username)

    @app.delete(DOC_ROUTE + _COLLAB + "/<username>")
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


def _owned_by_kind(grants) -> list[dict]:
    """The resources the user owns, grouped into one segment per kind.

    Every kind gets a group even when it is empty, so the page's segmented
    control is stable: a writer with no books still sees *Books (0)* and learns
    that sharing one is a thing they could do.
    """
    by_kind: dict[str, list] = {k.name: [] for k in ACCOUNT_KINDS}
    for scope in sharing.owned_resources(grants, ACCOUNT_KINDS):
        kind = next(k for k in ACCOUNT_KINDS if k.name == scope["kind"])
        by_kind[kind.name].append({
            **scope,
            "name": kind.describe(scope),
            # The context shown beside the name: the coarser scope fields, which
            # for a book or a calendar is nothing at all.
            "context": [scope[f] for f in kind.fills[:-1] if scope[f]],
            # The GET-collaborators URL doubles as the base for the PUT/DELETE
            # the page's sharing controls call (append ``/<username>``).
            "collab_url": sharing.account_sharing_url(kind, scope),
        })
    # "resources", not "items": in Jinja ``k.items`` resolves to the dict's own
    # ``items`` method rather than this key, and renders as a bound method.
    return [
        {"name": k.name, "label": k.label, "plural": k.plural,
         "resources": by_kind[k.name]}
        for k in ACCOUNT_KINDS
    ]


def _render_account(auth_store: AuthStore):
    """Render the account page: profile plus a compact list of the resources the
    user owns -- across both services, since one grant store holds them all.
    Each resource's collaborators are loaded on demand (see the page's
    ``/collaborators`` fetch), so this stays cheap no matter how much is owned."""
    username = current_user.username
    record = auth_store.get_user(username) or {}
    grants = auth_store.grants_for(username)
    owned = _owned_by_kind(grants)
    return render_template(
        "account.html",
        username=username,
        email=record.get("email"),
        role=record.get("role", "user"),
        owned_kinds=owned,
        owned_total=sum(len(k["resources"]) for k in owned),
        contacts=auth_store.list_contacts(username),
        shared_with_me=sharing.resources_shared_with(grants, username, ACCOUNT_KINDS),
        roles=list(ROLE_PERMS.keys()),
    )


def register_account_routes(app: Flask, auth_store: AuthStore, csrf, limiter) -> None:
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


def register_admin_routes(
    app: Flask, auth_store: AuthStore, user_cleanup: Callable[[str], None]
) -> None:
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
        user_cleanup(username)
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
        payload = {"error": err.message}
        if isinstance(err, MediaInUse):
            payload["references"] = err.references
        return jsonify(payload), err.status_code

    @app.errorhandler(AuthError)
    def handle_auth_error(err: AuthError):
        # Auth/access-control errors (login, grants, admin actions) now come from
        # the shared ``visualizer.auth`` package with their own base class.
        return jsonify({"error": err.message}), err.status_code
