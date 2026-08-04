"""The header service switcher links across to Chronos (and Admin)."""

import mongomock
from conftest import login
from werkzeug.security import generate_password_hash

from visualizer.akasha.app import create_app
from visualizer.akasha.store import DocumentStore
from visualizer.auth import AuthStore


def test_editor_header_has_switcher_with_timeline_link(client):
    html = client.get("/").get_data(as_text=True)
    assert "service-switch" in html
    assert "Articles" in html and "Timeline" in html
    assert "http://localhost:5003" in html          # default chronos URL
    assert ">Admin<" in html                          # seeded client is an admin


def test_account_page_also_has_switcher(client):
    html = client.get("/account").get_data(as_text=True)
    assert "service-switch" in html and "Timeline" in html


def test_switcher_urls_are_configurable():
    client_db = mongomock.MongoClient()
    auth = AuthStore(client_db)
    auth.create_user("mara", generate_password_hash("pw"), role="user")
    app = create_app(
        DocumentStore(client_db), auth, secret_key="s",
        akasha_url="https://world.example/akasha",
        chronos_url="https://world.example/chronos",
    )
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)
    c = app.test_client()
    assert login(c, "mara", "pw").status_code == 200
    html = c.get("/").get_data(as_text=True)
    assert "https://world.example/chronos" in html
    assert 'aria-current="page"' in html              # akasha tab marked active
    # A non-admin sees no Admin link.
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
