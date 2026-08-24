"""The header service switcher links across to the other services.

Admin and Account used to sit here too; they are now one "Accounts" link
leading to a page with a tab each, so the switcher is services only.
"""

import mongomock
from conftest import login
from werkzeug.security import generate_password_hash

from visualizer.akasha.app import create_app
from visualizer.akasha.store import DocumentStore
from visualizer.auth import AuthStore


def test_editor_header_has_switcher_with_timeline_link(client):
    html = client.get("/").get_data(as_text=True)
    assert "service-switch" in html
    assert "Articles" in html and "Timeline" in html and "Maps" in html
    assert "http://localhost:5003" in html          # default chronos URL
    assert "http://localhost:5004" in html          # default prithvi URL
    # Admin is no longer a header link even for an admin: it is a tab inside
    # Accounts, so the switcher carries services and nothing else.
    assert ">Admin<" not in html
    assert ">Access<" in html


def test_account_page_also_has_switcher(client):
    html = client.get("/account").get_data(as_text=True)
    assert "service-switch" in html and "Timeline" in html and "Maps" in html


def test_switcher_urls_are_configurable():
    client_db = mongomock.MongoClient()
    auth = AuthStore(client_db)
    auth.create_user("mara", generate_password_hash("pw"), role="user")
    app = create_app(
        DocumentStore(client_db), auth, secret_key="s",
        akasha_url="https://world.example/akasha",
        chronos_url="https://world.example/chronos",
        prithvi_url="https://world.example/maps",
    )
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)
    c = app.test_client()
    assert login(c, "mara", "pw").status_code == 200
    html = c.get("/").get_data(as_text=True)
    assert "https://world.example/chronos" in html
    assert "https://world.example/maps" in html
    assert 'aria-current="page"' in html              # akasha tab marked active
    # Nobody gets an Admin link in the header any more.
    assert "https://world.example/akasha/admin" not in html


def test_non_admin_has_no_admin_link():
    client_db = mongomock.MongoClient()
    auth = AuthStore(client_db)
    auth.create_user("plain", generate_password_hash("pw"), role="user")
    app = create_app(DocumentStore(client_db), auth, secret_key="s")
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)
    c = app.test_client()
    assert login(c, "plain", "pw").status_code == 200
    html = c.get("/").get_data(as_text=True)
    assert "service-switch" in html
    assert ">Admin<" not in html
