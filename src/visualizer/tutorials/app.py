"""The tutorials' application factory: wiring, and nothing else.

Everything it uses is handed in -- the lessons, the pictures, the accounts
store, the links to the other services -- and ``stack.py`` is the one place
that picks the real ones. A test builds it over an ``InMemoryCatalog`` and a
dict of pictures.
"""

from __future__ import annotations

from flask import Flask
from flask_wtf.csrf import CSRFProtect

from visualizer.auth import (
    AuthStore,
    build_limiter,
    init_login,
    register_auth_routes,
    register_service_links,
)
from visualizer.auth.store import registration_allowed
from visualizer.observability import Observability
from visualizer.service_links import STANDALONE_LINKS, ServiceLinks
from visualizer.shared_assets import register_shared_assets
from visualizer.static_versions import install_versioned_static

from .catalog import LessonCatalog
from .routes import is_tutorial_page, register_routes
from .shots import ShotLibrary


def create_app(
    catalog: LessonCatalog,
    shots: ShotLibrary,
    auth_store: AuthStore,
    secret_key: str,
    links: ServiceLinks = STANDALONE_LINKS,
    secure_cookies: bool = False,
    rate_limit_storage_uri: str = "memory://",
    observability: Observability | None = None,
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

    # The pages are public, but a signed-in reader still gets the stack's nav
    # and header, and logging out from here has to work like anywhere else.
    csrf = CSRFProtect(app)
    limiter = build_limiter(app, rate_limit_storage_uri)
    init_login(app, auth_store)
    register_auth_routes(app, auth_store, csrf, limiter, home_endpoint="index")
    register_service_links(app, links, current="tutorials", is_home=is_tutorial_page)
    register_shared_assets(app)
    install_versioned_static(app)
    _offer_registration(app, auth_store)
    register_routes(app, catalog, shots)

    if observability is not None:
        observability.install(app, "tutorials")
    return app


def _offer_registration(app: Flask, auth_store: AuthStore) -> None:
    """Whether a signed-out reader is offered "Create an account".

    A function, so the accounts store is asked only by a page that shows the
    offer -- one with nobody signed in.
    """

    @app.context_processor
    def _registration():
        return {
            "registration_open": lambda: registration_allowed(
                auth_store.get_registration_mode(), auth_store.count_users()
            )
        }
