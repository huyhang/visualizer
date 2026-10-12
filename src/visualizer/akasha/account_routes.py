"""Self-service account management for any logged-in user."""

from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from visualizer import sharing
from visualizer.auth import (
    ROLE_PERMS,
    AuthError,
    AuthStore,
    InvalidEmail,
    validate_email,
)

from .errors import AkashaError
from .share_kinds import ACCOUNT_KINDS

# Per-IP limit for the self-service account endpoints. Looser than the auth
# limit (login/register) -- these are for a logged-in user tidying their own
# account, not a brute-force surface.
_ACCOUNT_RATE_LIMIT = "10 per minute; 60 per hour"


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
