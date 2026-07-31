"""Contract tests (design §7.6, §11).

Validate that (a) every example embedded in ``docs/openapi.json`` conforms to its
own schema, and (b) real ``create_app`` responses conform too -- so the
published contract and the running code cannot drift.

OpenAPI 3.0 keywords JSON Schema doesn't know (``nullable``, ``readOnly``,
``example``) are simply ignored by the validator, which is fine here.
"""

import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator
from jsonschema.validators import RefResolver

from tests.chronos.conftest import ref

BOOK = "ember-pact"
_OPENAPI_PATH = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"


@pytest.fixture(scope="module")
def openapi():
    return json.loads(_OPENAPI_PATH.read_text())


def _validator(openapi, schema_name):
    resolver = RefResolver.from_schema(openapi)
    schema = {"$ref": f"#/components/schemas/{schema_name}"}
    return Draft7Validator(schema, resolver=resolver)


def _schemas_with_examples(openapi):
    return [
        (name, s["example"])
        for name, s in openapi["components"]["schemas"].items()
        if "example" in s
    ]


def test_openapi_is_valid_json_and_has_plotline(openapi):
    assert openapi["openapi"].startswith("3.")
    assert "Plotline" in openapi["components"]["schemas"]


def test_embedded_examples_conform_to_their_schemas(openapi):
    examples = _schemas_with_examples(openapi)
    assert examples, "expected at least one embedded example"
    for name, example in examples:
        _validator(openapi, name).validate(example)


# -- live responses conform --------------------------------------------------


def _event(location="highkeep", start=0, end=10, characters=("aldric",)):
    return {
        "location": ref(location, "locations").to_dict(),
        "start_tick": start,
        "end_tick": end,
        "characters": [ref(c).to_dict() for c in characters],
    }


@pytest.fixture
def story_client(app, fake_gate):
    for c in ("aldric", "lyra"):
        fake_gate.add(ref(c))
    for loc in ("highkeep",):
        fake_gate.add(ref(loc, "locations"))
    c = app.test_client()
    assert c.post("/login", json={"username": "mara", "password": "mara-pass"}).status_code == 200
    c.post(f"/books/{BOOK}", json={"title": "The Ember Pact"})
    for eid, s, e in [("a", 0, 10), ("b", 0, 10), ("m", 20, 30), ("t", 40, 50)]:
        c.post(f"/books/{BOOK}/events/{eid}", json=_event("highkeep", s, e))
    c.post(f"/books/{BOOK}/plotlines/knights",
           json={"title": "The Knight's Road", "events": ["a", "m", "t"], "goals": ["g"]})
    c.post(f"/books/{BOOK}/plotlines/spies",
           json={"title": "The Spy's Shadow", "events": ["b", "m", "t"], "goals": ["g"]})
    c.post(f"/books/{BOOK}/terminus/t")
    return c


def test_live_plotline_conforms(openapi, story_client):
    body = story_client.get(f"/books/{BOOK}/plotlines/knights").get_json()
    _validator(openapi, "Plotline").validate(body)


def test_live_neighborhood_conforms(openapi, story_client):
    body = story_client.get(f"/books/{BOOK}/events/m/plotlines").get_json()
    _validator(openapi, "EventNeighborhood").validate(body)
