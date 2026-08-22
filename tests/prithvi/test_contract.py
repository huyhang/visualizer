"""Contract tests: the published document cannot drift from the code.

The same three guarantees the other two services hold themselves to --
coverage, examples, live responses -- plus the two consistency checks: no
dangling ``$ref``, and a documented error-code enum that matches the
``PrithviError`` subclasses actually defined.

The document stays valid **OpenAPI 3.0**; ``_as_json_schema`` converts its
``nullable`` spelling to JSON Schema before validating anything against it.
"""

import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft7Validator
from jsonschema.validators import RefResolver

from .conftest import COLLECTION, MAP_URL, OPEN_ARTICLE, PIN_URL, SVG, WORLD

_OPENAPI_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "prithvi" / "openapi.json"
)

# The shared auth pages and static assets come from ``visualizer.auth``; they
# are the same on every service and are not part of this contract. So is the
# map browser's HTML shell, which is a page rather than an endpoint -- but note
# what is *not* here: the ``/ui/...`` routes it calls are ordinary JSON the
# document describes like any other, because "the UI needs it" is not a reason
# for an endpoint to go unspecified.
_NOT_OUR_API = {
    "/",
    "/static/{filename}",
    "/static/js/shared/{filename}",
    "/login",
    "/logout",
    "/register",
    "/auth/me",
    "/change-password",
}
_HTTP_METHODS = {"get", "post", "put", "delete"}


@pytest.fixture(scope="module")
def openapi():
    return json.loads(_OPENAPI_PATH.read_text())


def _as_json_schema(node):
    """OpenAPI's ``nullable: true`` becomes a JSON Schema union."""
    if isinstance(node, list):
        return [_as_json_schema(value) for value in node]
    if not isinstance(node, dict):
        return node
    out = {key: _as_json_schema(value) for key, value in node.items()}
    if out.pop("nullable", False):
        if isinstance(out.get("type"), str):
            out["type"] = [out["type"], "null"]
        else:
            out = {"anyOf": [out, {"type": "null"}]}
    return out


@pytest.fixture(scope="module")
def schema_doc(openapi):
    return _as_json_schema(openapi)


def validator(schema_doc, name):
    resolver = RefResolver.from_schema(schema_doc)
    return Draft7Validator({"$ref": f"#/components/schemas/{name}"}, resolver=resolver)


def _openapi_path(rule):
    path = str(rule)
    for argument in rule.arguments:
        for spelling in (f"<{argument}>", f"<int:{argument}>", f"<path:{argument}>"):
            path = path.replace(spelling, "{" + argument + "}")
    return path


def _app_operations(app):
    return {
        (method.lower(), _openapi_path(rule))
        for rule in app.url_map.iter_rules()
        if _openapi_path(rule) not in _NOT_OUR_API
        for method in rule.methods
        if method.lower() in _HTTP_METHODS
    }


def _spec_operations(openapi):
    return {
        (method, path)
        for path, item in openapi["paths"].items()
        for method in item
        if method in _HTTP_METHODS
    }


# -- 1. coverage --------------------------------------------------------------


def test_the_document_and_the_route_table_are_the_same_set(openapi, app):
    assert _app_operations(app) == _spec_operations(openapi)


def test_the_document_is_well_formed(openapi):
    assert openapi["openapi"].startswith("3.")
    assert openapi["info"]["title"] == "Prithvi API"
    assert "sessionCookie" in openapi["components"]["securitySchemes"]


def test_no_reference_dangles(openapi):
    defined = {
        f"#/components/{section}/{name}"
        for section in ("schemas", "responses", "parameters", "requestBodies", "headers")
        for name in openapi["components"].get(section, {})
    }
    used = set(re.findall(r'"\$ref":\s*"([^"]+)"', json.dumps(openapi)))
    assert not used - defined


def test_every_error_the_code_can_raise_is_documented(openapi):
    from visualizer.prithvi import errors

    raisable = {
        value.code
        for value in vars(errors).values()
        if isinstance(value, type) and issubclass(value, errors.PrithviError)
    }
    documented = set(openapi["components"]["schemas"]["Error"]["properties"]["code"]["enum"])
    assert raisable == documented


# -- 2. examples --------------------------------------------------------------


def test_every_embedded_example_conforms_to_its_own_schema(openapi, schema_doc):
    examples = [
        (name, definition["example"])
        for name, definition in openapi["components"]["schemas"].items()
        if "example" in definition
    ]
    assert len(examples) >= 10
    for name, example in examples:
        validator(schema_doc, name).validate(example)


# -- 3. live responses --------------------------------------------------------


@pytest.fixture
def seeded(client):
    """One map, scaled, with one pin on it -- enough to reach every schema."""
    assert client.post(MAP_URL, data=SVG, content_type="image/svg+xml").status_code == 201
    assert client.put(
        f"{MAP_URL}/scale",
        json={"across": 400, "unit": "leagues"},
        headers={"If-Match": '"1"'},
    ).status_code == 200
    assert client.post(PIN_URL, json={"x": 10, "y": 20}).status_code == 201
    return client


@pytest.mark.parametrize(
    "url,name",
    [
        ("/health", "Health"),
        ("/ui/worlds", "WorldList"),
        (f"/ui/worlds/{WORLD}/articles", "ArticleChoiceList"),
        (f"/ui/worlds/{WORLD}/articles/{COLLECTION}/{OPEN_ARTICLE}", "ArticlePreview"),
        (f"/worlds/{WORLD}/maps", "MapPage"),
        (MAP_URL, "Map"),
        (f"{MAP_URL}/versions", "VersionList"),
        (f"{MAP_URL}/versions/1", "MapVersion"),
        (f"{MAP_URL}/pins", "PinPage"),
        (PIN_URL, "Pin"),
        (f"{PIN_URL}/versions", "VersionList"),
        (f"{PIN_URL}/versions/1", "PinVersion"),
    ],
)
def test_a_live_response_conforms(schema_doc, seeded, url, name):
    response = seeded.get(url)
    assert response.status_code == 200, response.get_json()
    validator(schema_doc, name).validate(response.get_json())


def test_a_live_error_conforms(schema_doc, seeded):
    response = seeded.post(
        f"{MAP_URL}/pins/{COLLECTION}/{OPEN_ARTICLE}", json={"x": 10, "y": 20}
    )
    assert response.status_code == 409
    validator(schema_doc, "Error").validate(response.get_json())
