"""Authentication: Flask-Login wiring, session routes, and the admin bootstrap.

Sessions are cookie-based (Flask-Login). The document API and the browser GUI
share the same login: a form post from the browser and a JSON/form post from a
script both end up with the same session cookie.

Kept separate from ``app.py`` so the application factory stays a thin
orchestrator and the auth concerns live in one place.

These routes are shared by both services (akasha and chronos) via
``register_auth_routes``, so invite-only registration, the forced first-login
password change, and per-IP rate limiting are enforced identically wherever the
one login is used.
"""

from functools import wraps

from flask import Blueprint, redirect, render_template, request, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from werkzeug.security import check_password_hash, generate_password_hash

from .errors import (
    EmailAlreadyExists,
    Forbidden,
    InvalidCredentials,
    InvalidEmail,
    RegistrationDisabled,
    Unauthorized,
    UserAlreadyExists,
    WeakPassword,
)
from .passwords import validate_password_strength
from .store import AuthStore, registration_allowed
from .validation import validate_email

# Pre-computed hash used to equalise login timing: when the username is unknown
# (or somehow has no stored hash) we still run a real hash comparison against
# this, so a missing account is not measurably faster than a wrong password.
_DUMMY_PASSWORD_HASH = generate_password_hash("timing-equalisation-dummy")

# Per-IP limits applied to the auth endpoints to blunt brute-forcing and abuse.
_AUTH_RATE_LIMIT = "5 per minute; 30 per hour"

# Endpoints a user with a pending forced password change may still reach. The
# auth routes live on the ``auth`` blueprint, hence the ``auth.`` prefix; the
# host app's ``static`` and ``health`` endpoints stay unprefixed.
_PW_CHANGE_ALLOWED_ENDPOINTS = frozenset(
    {
        "auth.change_password_page",
        "auth.change_password",
        "auth.logout",
        "auth.login",
        "static",
        "health",
    }
)


class User(UserMixin):
    """Minimal Flask-Login user backed by an ``AuthStore`` record."""

    def __init__(self, username: str, role: str, must_change_password: bool = False):
        self.id = username
        self.username = username
        self.role = role
        self.must_change_password = must_change_password

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def build_limiter(app, storage_uri: str = "memory://") -> Limiter:
    """Construct a per-IP rate limiter bound to ``app`` (injected storage).

    Default in-memory storage suits a single-process deployment; pass a Redis
    URI (e.g. via ``RATELIMIT_STORAGE_URI``) to share limits across gunicorn
    workers. No default limits: only the auth endpoints opt in.
    """
    return Limiter(
        key_func=get_remote_address,
        app=app,
        storage_uri=storage_uri,
        default_limits=[],
    )


def register_service_links(app, akasha_url: str, chronos_url: str, current: str) -> None:
    """Expose cross-service nav links to every template (the header switcher).

    Both services share one login (one cookie across ports/origins), so these are
    plain links between the two apps. The URLs are injected here rather than
    hard-coded in templates, so a reverse-proxy deployment can point them wherever
    it serves each service. ``current`` (``"akasha"``/``"chronos"``) lets a header
    highlight the active service.
    """
    links = {
        "akasha": akasha_url,
        "chronos": chronos_url,
        "admin": akasha_url.rstrip("/") + "/admin",
        "current": current,
    }

    @app.context_processor
    def _inject_service_links():
        return {"service_links": links}


def _wants_json() -> bool:
    """Whether to answer with JSON (API client) rather than HTML (browser)."""
    if request.path.startswith("/databases"):
        return True
    if request.is_json:
        return True
    accept = request.accept_mimetypes
    best = accept.best_match(["application/json", "text/html"])
    return best == "application/json" and accept[best] >= accept["text/html"]


def init_login(app, auth_store: AuthStore) -> None:
    """Attach a configured ``LoginManager`` to ``app``."""
    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(username: str):
        record = auth_store.get_user(username)
        # Deactivated accounts are treated as logged out on their next request.
        if record is None or not record.get("active", False):
            return None
        return User(
            username,
            record.get("role", "user"),
            record.get("must_change_password", False),
        )

    @login_manager.unauthorized_handler
    def unauthorized():
        if _wants_json():
            raise Unauthorized("Authentication required.")
        return redirect(url_for("auth.login", next=request.path))


def admin_required(view):
    """Guard a view so only authenticated admins may reach it."""

    @wraps(view)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin:
            raise Forbidden("Administrator privileges required.")
        return view(*args, **kwargs)

    return wrapper


def _credentials():
    """Pull (username, password) from a JSON body or an HTML form."""
    return _field("username"), _field("password")


def _field(name: str):
    """Read a single field from a JSON body or an HTML form."""
    if request.is_json:
        return (request.get_json(silent=True) or {}).get(name)
    return request.form.get(name)


def _form_error(template: str, message: str, json_error, **extra):
    """Answer a failed auth submission.

    API clients get the raised domain error (JSON); browsers get the form
    re-rendered with an inline message and the matching HTTP status. ``extra``
    template context (e.g. ``registration_open``) is forwarded to the re-render.
    """
    if _wants_json():
        raise json_error(message)
    return render_template(
        template, error=message, next=request.form.get("next", ""), **extra
    ), (json_error.status_code)


def register_auth_routes(
    app, auth_store: AuthStore, csrf, limiter=None, home_endpoint="index"
) -> None:
    """Register the shared auth routes on ``app`` as an ``auth`` blueprint.

    The blueprint carries its own templates (login / register / change-password).
    ``home_endpoint`` is where a successful *browser* login lands -- akasha's
    ``index``. Pass ``None`` for an API-only host (e.g. chronos), where the HTML
    redirect paths are never exercised; it then falls back to ``/``.
    """
    bp = Blueprint("auth", __name__, template_folder="templates")

    def limit(view):
        """Apply the auth rate limit if a limiter was provided (else a no-op)."""
        return limiter.limit(_AUTH_RATE_LIMIT)(view) if limiter is not None else view

    def _reg_allowed() -> bool:
        return registration_allowed(
            auth_store.get_registration_mode(), auth_store.count_users()
        )

    def _home_url() -> str:
        return url_for(home_endpoint) if home_endpoint else "/"

    @bp.get("/register")
    def register_page():
        return render_template("register.html", registration_open=_reg_allowed())

    @bp.post("/register")
    @limit
    def register():
        # Invite-only mode disables self-registration (except bootstrapping the
        # very first account, which is always permitted).
        if not _reg_allowed():
            return _form_error(
                "register.html",
                "Registration is invite-only. Ask an administrator for an account.",
                RegistrationDisabled,
                registration_open=False,
            )
        username, password = _credentials()
        if not username or not password:
            return _form_error(
                "register.html",
                "Username and password are required.",
                InvalidCredentials,
                registration_open=True,
            )
        try:
            email = validate_email(_field("email"))
        except InvalidEmail as err:
            return _form_error(
                "register.html", err.message, InvalidEmail, registration_open=True
            )
        try:
            validate_password_strength(password, username)
        except WeakPassword as err:
            return _form_error(
                "register.html", err.message, WeakPassword, registration_open=True
            )
        # The first account ever registered becomes the admin so a fresh
        # deployment is usable; everyone after them is a plain user.
        role = "admin" if auth_store.count_users() == 0 else "user"
        try:
            auth_store.create_user(
                username, generate_password_hash(password), email=email, role=role
            )
        except (UserAlreadyExists, EmailAlreadyExists) as err:
            return _form_error(
                "register.html", err.message, type(err), registration_open=True
            )
        if _wants_json():
            return {"username": username, "email": email, "role": role}, 201
        return redirect(url_for("auth.login"))

    @bp.get("/login")
    def login():
        if current_user.is_authenticated:
            return redirect(_home_url())
        return render_template(
            "login.html",
            next=request.args.get("next", ""),
            registration_open=_reg_allowed(),
        )

    @bp.post("/login")
    @limit
    def do_login():
        username, password = _credentials()
        record = auth_store.get_user(username) if username else None
        # Always run one hash comparison (dummy when the user is unknown) so the
        # response time does not reveal whether the account exists.
        stored_hash = (record or {}).get("password_hash") or _DUMMY_PASSWORD_HASH
        password_ok = check_password_hash(stored_hash, password or "")
        # A single, indistinguishable failure for every case: unknown user, wrong
        # password, or a deactivated/deleted account. Revealing which one leaks
        # whether an account exists (and, for the deactivated case, that the
        # password was correct).
        if not (record and record.get("active", False) and password_ok):
            return _form_error(
                "login.html",
                "Invalid username or password.",
                InvalidCredentials,
                registration_open=_reg_allowed(),
            )
        login_user(
            User(
                username,
                record.get("role", "user"),
                record.get("must_change_password", False),
            )
        )
        if _wants_json():
            return {
                "username": username,
                "role": record.get("role", "user"),
                "must_change_password": record.get("must_change_password", False),
            }
        # A user owing a password change is sent straight to the change form.
        if record.get("must_change_password", False):
            return redirect(url_for("auth.change_password_page"))
        target = request.args.get("next") or request.form.get("next") or ""
        # Only allow same-app relative redirects.
        if not target.startswith("/"):
            target = _home_url()
        return redirect(target)

    @bp.post("/logout")
    @login_required
    def logout():
        logout_user()
        if _wants_json():
            return "", 204
        return redirect(url_for("auth.login"))

    @bp.get("/auth/me")
    @login_required
    def me():
        return {
            "username": current_user.username,
            "role": current_user.role,
            "must_change_password": current_user.must_change_password,
        }

    @bp.get("/change-password")
    @login_required
    def change_password_page():
        return render_template(
            "change_password.html", forced=current_user.must_change_password
        )

    @bp.post("/change-password")
    @limit
    @login_required
    def change_password():
        username = current_user.username
        new_password = _field("password")
        confirm = _field("confirm_password")
        if not new_password or not confirm:
            return _pw_change_error(
                "New password and confirmation are required.", InvalidCredentials
            )
        if new_password != confirm:
            return _pw_change_error("The two passwords do not match.", InvalidCredentials)
        try:
            validate_password_strength(new_password, username)
        except WeakPassword as err:
            return _pw_change_error(err.message, WeakPassword)
        # Setting a password clears the forced-change flag.
        auth_store.set_password(username, generate_password_hash(new_password))
        if _wants_json():
            return {"username": username, "status": "password_changed"}
        return redirect(_home_url())

    @bp.before_app_request
    def _enforce_password_change():
        """Block a user with a pending forced change until they set a new one."""
        if not current_user.is_authenticated:
            return None
        if not current_user.must_change_password:
            return None
        if request.endpoint in _PW_CHANGE_ALLOWED_ENDPOINTS:
            return None
        if _wants_json():
            raise Forbidden("You must change your password before continuing.")
        return redirect(url_for("auth.change_password_page"))

    csrf.exempt(bp)
    app.register_blueprint(bp)


def _pw_change_error(message: str, json_error):
    """Answer a failed change-password submission (JSON error or re-rendered form)."""
    if _wants_json():
        raise json_error(message)
    return render_template(
        "change_password.html",
        error=message,
        forced=current_user.must_change_password,
    ), (json_error.status_code)
