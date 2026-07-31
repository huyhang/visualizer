"""Authentication: Flask-Login wiring, session routes, and the admin bootstrap.

Sessions are cookie-based (Flask-Login). The document API and the browser GUI
share the same login: a form post from the browser and a JSON/form post from a
script both end up with the same session cookie.

Kept separate from ``app.py`` so the application factory stays a thin
orchestrator and the auth concerns live in one place.
"""

from functools import wraps

from flask import redirect, render_template, request, url_for
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from werkzeug.security import check_password_hash, generate_password_hash

from .auth_store import AuthStore
from .errors import (
    EmailAlreadyExists,
    Forbidden,
    InvalidCredentials,
    InvalidEmail,
    Unauthorized,
    UserAlreadyExists,
)
from .validation import validate_email

# Pre-computed hash used to equalise login timing: when the username is unknown
# (or somehow has no stored hash) we still run a real hash comparison against
# this, so a missing account is not measurably faster than a wrong password.
_DUMMY_PASSWORD_HASH = generate_password_hash("timing-equalisation-dummy")


class User(UserMixin):
    """Minimal Flask-Login user backed by an ``AuthStore`` record."""

    def __init__(self, username: str, role: str):
        self.id = username
        self.username = username
        self.role = role

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


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
    login_manager.login_view = "login"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(username: str):
        record = auth_store.get_user(username)
        # Deactivated accounts are treated as logged out on their next request.
        if record is None or not record.get("active", False):
            return None
        return User(username, record.get("role", "user"))

    @login_manager.unauthorized_handler
    def unauthorized():
        if _wants_json():
            raise Unauthorized("Authentication required.")
        return redirect(url_for("login", next=request.path))


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


def _form_error(template: str, message: str, json_error):
    """Answer a failed auth submission.

    API clients get the raised domain error (JSON); browsers get the form
    re-rendered with an inline message and the matching HTTP status.
    """
    if _wants_json():
        raise json_error(message)
    return render_template(template, error=message, next=request.form.get("next", "")), (
        json_error.status_code
    )


def register_auth_routes(app, auth_store: AuthStore, csrf) -> None:
    @app.get("/register")
    def register_page():
        return render_template("register.html")

    @app.post("/register")
    @csrf.exempt
    def register():
        username, password = _credentials()
        if not username or not password:
            return _form_error(
                "register.html", "Username and password are required.", InvalidCredentials
            )
        try:
            email = validate_email(_field("email"))
        except InvalidEmail as err:
            return _form_error("register.html", err.message, InvalidEmail)
        # The first account ever registered becomes the admin so a fresh
        # deployment is usable; everyone after them is a plain user.
        role = "admin" if auth_store.count_users() == 0 else "user"
        try:
            auth_store.create_user(
                username, generate_password_hash(password), email=email, role=role
            )
        except (UserAlreadyExists, EmailAlreadyExists) as err:
            return _form_error("register.html", err.message, type(err))
        if _wants_json():
            return {"username": username, "email": email, "role": role}, 201
        return redirect(url_for("login"))

    @app.get("/login")
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("index"))
        return render_template("login.html", next=request.args.get("next", ""))

    @app.post("/login")
    @csrf.exempt
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
                "login.html", "Invalid username or password.", InvalidCredentials
            )
        login_user(User(username, record.get("role", "user")))
        if _wants_json():
            return {"username": username, "role": record.get("role", "user")}
        target = request.args.get("next") or request.form.get("next") or ""
        # Only allow same-app relative redirects.
        if not target.startswith("/"):
            target = url_for("index")
        return redirect(target)

    @app.post("/logout")
    @csrf.exempt
    @login_required
    def logout():
        logout_user()
        if _wants_json():
            return "", 204
        return redirect(url_for("login"))

    @app.get("/auth/me")
    @login_required
    def me():
        return {"username": current_user.username, "role": current_user.role}
