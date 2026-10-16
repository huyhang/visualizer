"""The tutorials as served: public pages, the stack's shell when signed in."""

import mongomock
import pytest
from werkzeug.security import generate_password_hash

from tests.tutorials.factories import (
    A_RING,
    Made,
    Note,
    Term,
    catalog,
    course,
    lesson,
    part,
    shot,
    shots,
    step,
)
from visualizer.auth import AuthStore
from visualizer.service_links import ServiceLinks
from visualizer.tutorials.app import create_app

LINKS = ServiceLinks(
    akasha="/", chronos="/timeline", prithvi="/prithvi", logos="/logos", tutorials="/tutorials"
)
CATALOG = catalog(
    course(part("world", "home", "first"), prelude="before"),
    lesson("before", title="Before you start"),
    lesson("home", title="A home for your story", lede="Make a {world}."),
    lesson(
        "first",
        title="Your first article",
        needs="home",
        steps=[
            step(
                title="Give it a name",
                text=("Type into **Title**, then press `Continue`.",),
                shot="first/name",
                alt="The New article dialog",
                note=Note("tip", "The slug fills itself in."),
            ),
        ],
        made=Made("Your first article.", shot="first/made", alt="The article"),
    ),
    terms=[Term("world", "Everything about one story.")],
)
SHOTS = shots(shot("first/name", ring=A_RING), shot("first/made"))


@pytest.fixture
def auth_store():
    store = AuthStore(mongomock.MongoClient())
    store.create_user("wren", generate_password_hash("pw-long-enough"), role="user")
    return store


@pytest.fixture
def app(auth_store):
    application = create_app(CATALOG, SHOTS, auth_store, secret_key="test", links=LINKS)
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def signed_in(app):
    client = app.test_client()
    response = client.post("/login", json={"username": "wren", "password": "pw-long-enough"})
    assert response.status_code == 200
    return client


def test_the_hub_is_public(client):
    html = client.get("/").text
    assert "From first article to first draft" in html
    assert "Before you start" in html and "A home for your story" in html
    assert "Lesson 2" in html


def test_a_signed_out_reader_is_offered_an_account_and_no_nav(client):
    html = client.get("/").text
    assert 'class="service-nav"' not in html
    assert 'href="/login">Log in<' in html
    assert 'href="/register">Create an account<' in html


def test_no_account_is_offered_once_registration_is_invite_only(client, auth_store):
    auth_store.set_registration_mode("invite")
    assert "Create an account" not in client.get("/").text


def test_signed_in_the_tab_is_lit_on_every_tutorial_page(signed_in):
    for path in ("/", "/first", "/glossary"):
        html = signed_in.get(path).text
        nav = html.split('<nav class="service-nav"', 1)[1].split("</nav>", 1)[0]
        lit = [chunk for chunk in nav.split("<a ")[1:] if 'aria-current="page"' in chunk]
        assert len(lit) == 1 and "Tutorials" in lit[0], path
        assert ">Access<" in html and "Log in" not in html


def test_a_lesson_draws_its_steps_marks_note_and_what_it_makes(client):
    html = client.get("/first").text
    assert "Lesson 2 of 2" in html
    assert '<span class="ui">Continue</span>' in html
    assert "<strong>Title</strong>" in html
    assert "The slug fills itself in." in html and "tut-note-tip" in html
    assert "What you made" in html
    assert 'href="/home"' in html  # what it needs, and the way back


def test_a_picture_comes_in_both_widths_and_both_themes_with_its_rings(client):
    html = client.get("/first").text
    for name in ("first/name-1280-light", "first/name-1280-dark",
                 "first/name-390-light", "first/name-390-dark"):
        assert f"shots/{name}.webp" in html
    assert 'alt="The New article dialog"' in html
    assert html.count("tut-ring tut-ring-desktop") == 1
    assert "left:10.0%;top:20.0%;width:30.0%;height:5.0%" in html


def test_a_glossary_word_links_to_its_entry(client):
    assert 'href="/glossary#world"' in client.get("/home").text
    glossary = client.get("/glossary").text
    assert 'id="world"' in glossary and "Everything about one story." in glossary


def test_an_unknown_lesson_is_a_friendly_404(client):
    response = client.get("/nowhere")
    assert response.status_code == 404
    assert "There's no lesson here" in response.text


def test_the_last_lesson_leads_back_to_the_hub(client):
    assert "That's every lesson" in client.get("/first").text
