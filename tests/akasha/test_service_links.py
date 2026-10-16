"""One value for where every service lives, and which pages light the nav.

``ServiceLinks`` replaced a keyword per service in every app factory;
``is_home`` replaced the single "index" a service's surface had to be.
"""

import dataclasses

import pytest
from flask import Flask, render_template_string

from visualizer.akasha.config import get_service_links
from visualizer.auth.session import is_index, register_service_links
from visualizer.service_links import STANDALONE_LINKS, ServiceLinks, tutorials_beside

LINKS = ServiceLinks(
    akasha="https://world.example/",
    chronos="https://world.example/timeline",
    prithvi="https://world.example/prithvi",
    logos="https://world.example/logos",
    tutorials="https://world.example/tutorials",
)


def test_account_admin_and_signing_in_are_akasha_pages():
    assert LINKS.account == "https://world.example/account"
    assert LINKS.admin == "https://world.example/admin"
    assert LINKS.login == "https://world.example/login"
    assert LINKS.register == "https://world.example/register"


@pytest.mark.parametrize(
    ("akasha", "tutorials"),
    [("/", "/tutorials"), ("http://localhost:5002", "http://localhost:5002/tutorials")],
)
def test_the_tutorials_sit_beside_akasha_unless_told_otherwise(akasha, tutorials):
    assert tutorials_beside(akasha) == tutorials


def test_no_link_can_be_left_out():
    with pytest.raises(TypeError):
        ServiceLinks(akasha="/", chronos="/timeline", prithvi="/prithvi", logos="/logos")


def test_the_standalone_links_are_the_per_service_ports():
    assert STANDALONE_LINKS.chronos == "http://localhost:5003"
    assert STANDALONE_LINKS.tutorials == "http://localhost:5002/tutorials"


def test_links_are_values():
    with pytest.raises(dataclasses.FrozenInstanceError):
        LINKS.akasha = "/elsewhere"  # type: ignore[misc]


def test_the_environment_names_every_link(monkeypatch):
    monkeypatch.setenv("AKASHA_URL", "https://world.example/")
    monkeypatch.setenv("CHRONOS_URL", "https://world.example/timeline")
    monkeypatch.setenv("PRITHVI_URL", "https://world.example/prithvi")
    monkeypatch.setenv("LOGOS_URL", "https://world.example/logos")
    monkeypatch.delenv("TUTORIALS_URL", raising=False)
    assert get_service_links() == LINKS
    monkeypatch.setenv("TUTORIALS_URL", "https://help.example/")
    assert get_service_links().tutorials == "https://help.example/"


@pytest.mark.parametrize(("endpoint", "home"), [("index", True), ("article", False), (None, False)])
def test_a_service_surface_is_its_index_by_default(endpoint, home):
    assert is_index(endpoint) is home


def _app(**kwargs):
    app = Flask(__name__)
    register_service_links(app, LINKS, current="tutorials", **kwargs)
    for rule in ("/", "/lesson"):
        app.add_url_rule(
            rule,
            "index" if rule == "/" else "lesson",
            lambda: render_template_string(
                "{{ service_links.active }}|{{ service_links.tutorials }}"
            ),
        )
    return app.test_client()


def test_by_default_only_the_index_lights_the_nav():
    client = _app()
    assert client.get("/").text == "tutorials|https://world.example/tutorials"
    assert client.get("/lesson").text == "None|https://world.example/tutorials"


def test_an_app_can_say_every_page_is_its_own():
    client = _app(is_home=lambda endpoint: endpoint is not None)
    assert client.get("/lesson").text.startswith("tutorials|")
