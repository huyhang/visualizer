"""The admin console: accounts, registration mode and raw grants."""

from collections.abc import Callable

from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import current_user
from werkzeug.security import generate_password_hash

from visualizer.auth import (
    ALL_PERMS,
    REGISTRATION_MODES,
    AuthError,
    AuthStore,
    Forbidden,
    UserNotFound,
    admin_required,
    generate_temp_password,
    validate_email,
    validate_password_strength,
)

from .errors import AkashaError


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
