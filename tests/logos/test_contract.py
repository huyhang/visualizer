"""The route table, the spec, the examples and the live payloads all agree.

Three guarantees, so the published contract cannot drift from the code:

1. every documented operation exists, and every operation is documented;
2. every error the service can raise appears in the documented enum;
3. every example, and every real response, validates against its schema.

Plus a check that no ``$ref`` dangles. Documentation that lies is worse than
documentation that is missing, and this is what stops it.
"""

import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft7Validator
from jsonschema.validators import RefResolver

from visualizer.logos import errors

from .conftest import BOOK, SECTION, VOLUME, section_payload

OPENAPI_PATH = Path(__file__).resolve().parents[2] / "docs" / "logos" / "openapi.json"
HTTP_METHODS = {"get", "post", "put", "delete"}

# Shared login pages, static assets, and the reader shell: HTML and asset
# routes, not JSON operations. Note that the reader's *data* is not exempt --
# `/ui/scenes` is specified below like any other read, because "the UI needs
# it" is not a reason for an endpoint to go undocumented.
NOT_API = {
    "/",
    "/static/{filename}",
    "/static/js/shared/{filename}",
    "/static/shared/{filename}",
    "/login",
    "/logout",
    "/register",
    "/auth/me",
    "/change-password",
}


@pytest.fixture(scope="module")
def openapi():
    return json.loads(OPENAPI_PATH.read_text())


def _as_json_schema(node):
    """OpenAPI's ``nullable: true`` spelled as a JSON Schema type union."""
    if isinstance(node, list):
        return [_as_json_schema(value) for value in node]
    if not isinstance(node, dict):
        return node
    result = {key: _as_json_schema(value) for key, value in node.items()}
    if result.pop("nullable", False):
        if isinstance(result.get("type"), str):
            result["type"] = [result["type"], "null"]
        else:
            result = {"anyOf": [result, {"type": "null"}]}
    return result


@pytest.fixture(scope="module")
def schema_doc(openapi):
    return _as_json_schema(openapi)


def _validator(schema_doc, name):
    return Draft7Validator(
        {"$ref": f"#/components/schemas/{name}"},
        resolver=RefResolver.from_schema(schema_doc),
    )


def _path(rule):
    path = str(rule)
    for argument in rule.arguments:
        for spelling in (f"<{argument}>", f"<int:{argument}>", f"<path:{argument}>"):
            path = path.replace(spelling, "{" + argument + "}")
    return path


def _app_operations(app):
    return {
        (method.lower(), _path(rule))
        for rule in app.url_map.iter_rules()
        if _path(rule) not in NOT_API
        for method in rule.methods
        if method.lower() in HTTP_METHODS
    }


def _spec_operations(openapi):
    return {
        (method, path)
        for path, item in openapi["paths"].items()
        for method in item
        if method in HTTP_METHODS
    }


def test_the_route_table_and_the_contract_are_the_same_set(app, openapi):
    assert _app_operations(app) == _spec_operations(openapi)


def test_the_contract_is_openapi_and_names_the_shared_session(openapi):
    assert openapi["openapi"].startswith("3.")
    assert openapi["info"]["title"] == "Logos API"
    assert "sessionCookie" in openapi["components"]["securitySchemes"]


def test_no_reference_dangles(openapi):
    defined = {
        f"#/components/{section}/{name}"
        for section in (
            "schemas",
            "responses",
            "parameters",
            "requestBodies",
            "headers",
        )
        for name in openapi["components"].get(section, {})
    }
    used = set(re.findall(r'"\$ref":\s*"([^"]+)"', json.dumps(openapi)))
    assert not used - defined


def test_every_error_the_service_can_raise_is_documented(openapi):
    implemented = {
        value.code
        for value in vars(errors).values()
        if isinstance(value, type) and issubclass(value, errors.LogosError)
    }
    documented = set(
        openapi["components"]["schemas"]["Error"]["properties"]["code"]["enum"]
    )
    assert implemented == documented


def test_every_example_conforms_to_its_own_schema(openapi, schema_doc):
    examples = [
        (name, schema["example"])
        for name, schema in openapi["components"]["schemas"].items()
        if "example" in schema
    ]
    assert len(examples) >= 8
    for name, example in examples:
        _validator(schema_doc, name).validate(example)


@pytest.fixture
def seeded(client):
    assert client.post(
        f"/books/{BOOK}/volumes/{VOLUME}", json={"title": "The Ember Pact"}
    ).status_code == 201
    assert client.post(
        f"/books/{BOOK}/volumes/{VOLUME}/sections/{SECTION}", json=section_payload()
    ).status_code == 201
    return client


@pytest.mark.parametrize(
    "path,schema",
    [
        ("/health", "Health"),
        ("/books", "BookList"),
        (f"/books/{BOOK}", "Manuscript"),
        (f"/books/{BOOK}/report", "Report"),
        (f"/books/{BOOK}/volumes/{VOLUME}", "Volume"),
        (f"/books/{BOOK}/volumes/{VOLUME}/manuscript", "VolumeManuscript"),
        (f"/books/{BOOK}/volumes/{VOLUME}/ui/scenes", "VolumeScenes"),
        (f"/books/{BOOK}/volumes/{VOLUME}/sections/{SECTION}", "Section"),
        (f"/books/{BOOK}/volumes/{VOLUME}/sections/{SECTION}/ui/scenes",
         "SingleSectionScenes"),
        (f"/books/{BOOK}/volumes/{VOLUME}/sections/{SECTION}/versions",
         "VersionList"),
        (f"/books/{BOOK}/volumes/{VOLUME}/sections/{SECTION}/versions/1",
         "SectionRevision"),
    ],
)
def test_a_live_response_conforms_to_its_documented_schema(
    schema_doc, seeded, path, schema
):
    response = seeded.get(path)
    assert response.status_code == 200, response.get_json()
    _validator(schema_doc, schema).validate(response.get_json())


@pytest.mark.parametrize(
    "make_request,expected",
    [
        (lambda c: c.post(
            f"/books/{BOOK}/volumes/{VOLUME}/sections/nope",
            json=section_payload(events=("ghost",)),
        ), 422),
        (lambda c: c.put(
            f"/books/{BOOK}/volumes/{VOLUME}", json={"title": "x"}
        ), 428),
        (lambda c: c.post(
            f"/books/{BOOK}/volumes/{VOLUME}", json={"title": "again"}
        ), 409),
        (lambda c: c.post(
            f"/books/{BOOK}/volumes/{VOLUME}/sections/bad", json={"kind": "chapter"}
        ), 400),
    ],
)
def test_a_live_error_conforms_to_the_documented_shape(
    schema_doc, seeded, make_request, expected
):
    response = make_request(seeded)
    assert response.status_code == expected, response.get_json()
    _validator(schema_doc, "Error").validate(response.get_json())
