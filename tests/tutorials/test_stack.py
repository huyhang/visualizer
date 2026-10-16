"""The tutorials in the real stack: mounted at /tutorials, linked from everywhere."""

import mongomock
import mongomock.gridfs
import pytest
from werkzeug.test import Client

from visualizer.stack import build_application


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("MONITORING_ENABLED", "false")
    for name in ("AKASHA_URL", "TUTORIALS_URL"):
        monkeypatch.delenv(name, raising=False)
    # Akasha keeps images in GridFS, which mongomock fakes only once asked to,
    # as the dev server does.
    mongomock.gridfs.enable_gridfs_integration()
    return Client(build_application(mongomock.MongoClient()))


def test_the_hub_and_its_lessons_are_served_under_tutorials(client):
    hub = client.get("/tutorials/")
    assert hub.status_code == 200
    assert "From first article to first draft" in hub.text
    assert client.get("/tutorials/before-you-start").status_code == 200
    assert client.get("/tutorials/glossary").status_code == 200


def test_signing_in_says_where_to_learn_how_it_works(client):
    page = client.get("/login").text
    assert 'New here? <a href="/tutorials">See how it works</a>' in page


def test_every_service_s_nav_has_the_tutorials_tab(client):
    client.post("/register", json={"username": "w", "password": "Correct-horse-9",
                                   "email": "w@example.com"})
    client.post("/login", json={"username": "w", "password": "Correct-horse-9"})
    for path in ("/", "/timeline/", "/prithvi/", "/logos/"):
        nav = client.get(path).text.split('<nav class="service-nav"', 1)[1].split("</nav>")[0]
        assert 'href="/tutorials"' in nav and ">Tutorials<" in nav, path
