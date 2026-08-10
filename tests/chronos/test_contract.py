"""Contract tests (design §7.6, §11).

Three guarantees, so the published contract cannot drift from the code:

1. **Coverage** -- every route the app registers is documented, and every
   documented route exists. This is the check that would have caught the spec
   sitting at 2 of 20 paths.
2. **Examples conform** -- each embedded example validates against its own
   schema.
3. **Live responses conform** -- real ``create_app`` responses validate against
   the schemas they claim.

Plus two consistency checks: no dangling ``$ref``, and the documented error-code
enum matching the ``ChronosError`` subclasses actually defined.

The published document stays valid **OpenAPI 3.0**; ``_as_json_schema`` converts
its ``nullable`` spelling to JSON Schema before validating. Other OpenAPI-only
keywords (``readOnly``, ``example``) are simply ignored by the validator.
"""

import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft7Validator
from jsonschema.validators import RefResolver

from tests.chronos.conftest import ref

BOOK = "ember-pact"
_OPENAPI_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "chronos" / "openapi.json"
)

# Auth/static routes come from akasha and are out of this contract's scope.
_NOT_OUR_API = {
    "/static/{filename}",
    # The ES modules both services load, served out of the package root by
    # ``visualizer.shared_assets``. An asset route, not part of the JSON API.
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
    """The spec as published (stays valid OpenAPI 3.0)."""
    return json.loads(_OPENAPI_PATH.read_text())


def _as_json_schema(node):
    """Translate OpenAPI 3.0 dialect into plain JSON Schema for validation.

    OpenAPI 3.0 spells "may be null" as ``{"type": "x", "nullable": true}``;
    JSON Schema spells it ``{"type": ["x", "null"]}``. Without this the
    validator rejects every legitimately-null field (e.g. a book with no
    calendar). The published document keeps the OpenAPI spelling.
    """
    if isinstance(node, list):
        return [_as_json_schema(v) for v in node]
    if not isinstance(node, dict):
        return node
    out = {k: _as_json_schema(v) for k, v in node.items()}
    if out.pop("nullable", False):
        if isinstance(out.get("type"), str):
            out["type"] = [out["type"], "null"]
        elif "$ref" in out or "type" not in out:
            # A nullable $ref / untyped schema: allow null alongside it.
            out = {"anyOf": [out, {"type": "null"}]}
    return out


@pytest.fixture(scope="module")
def schema_doc(openapi):
    """The spec, converted once, for use as a validation source."""
    return _as_json_schema(openapi)


def _validator(schema_doc, schema_name):
    resolver = RefResolver.from_schema(schema_doc)
    return Draft7Validator({"$ref": f"#/components/schemas/{schema_name}"}, resolver=resolver)


def _openapi_path(rule):
    path = str(rule)
    for arg in rule.arguments:
        path = path.replace(f"<{arg}>", "{" + arg + "}").replace(f"<path:{arg}>", "{" + arg + "}")
    return path


def _app_operations(app):
    ops = set()
    for rule in app.url_map.iter_rules():
        path = _openapi_path(rule)
        if path in _NOT_OUR_API:
            continue
        for method in rule.methods:
            if method.lower() in _HTTP_METHODS:
                ops.add((method.lower(), path))
    return ops


def _spec_operations(openapi):
    return {
        (method, path)
        for path, item in openapi["paths"].items()
        for method in item
        if method in _HTTP_METHODS
    }


# -- 1. coverage -------------------------------------------------------------


def test_every_route_is_documented(openapi, app):
    undocumented = sorted(_app_operations(app) - _spec_operations(openapi))
    assert not undocumented, f"routes missing from openapi.json: {undocumented}"


def test_no_documented_route_is_imaginary(openapi, app):
    imaginary = sorted(_spec_operations(openapi) - _app_operations(app))
    assert not imaginary, f"openapi.json documents routes that do not exist: {imaginary}"


def test_spec_is_well_formed(openapi):
    assert openapi["openapi"].startswith("3.")
    assert "sessionCookie" in openapi["components"]["securitySchemes"]


def test_every_ref_resolves(openapi):
    """No dangling $ref anywhere in the document."""
    defined = {
        f"#/components/{section}/{name}"
        for section in ("schemas", "responses", "parameters", "requestBodies", "headers")
        for name in openapi["components"].get(section, {})
    }
    used = set(re.findall(r'"\$ref":\s*"([^"]+)"', json.dumps(openapi)))
    assert not (used - defined), f"dangling $refs: {sorted(used - defined)}"


def test_error_codes_match_the_implementation(openapi):
    """The Finding.code enum must list every ChronosError subclass code."""
    from visualizer.chronos import errors as err_mod

    actual = {
        cls.code
        for cls in vars(err_mod).values()
        if isinstance(cls, type) and issubclass(cls, err_mod.ChronosError)
    }
    documented = set(openapi["components"]["schemas"]["Finding"]["properties"]["code"]["enum"])
    assert actual == documented, (
        f"missing from spec: {sorted(actual - documented)}; "
        f"stale in spec: {sorted(documented - actual)}"
    )


# -- 2. embedded examples ----------------------------------------------------


def test_embedded_examples_conform_to_their_schemas(openapi, schema_doc):
    examples = [
        (name, s["example"])
        for name, s in openapi["components"]["schemas"].items()
        if "example" in s
    ]
    assert len(examples) >= 8, "expected examples on the main schemas"
    for name, example in examples:
        _validator(schema_doc, name).validate(example)


# -- 3. live responses -------------------------------------------------------


def _event(location="highkeep", start=0, end=10, characters=("aldric",), title=None):
    return {
        "title": title,
        "location": ref(location, "locations").to_dict(),
        "start_tick": start,
        "end_tick": end,
        "characters": [ref(c).to_dict() for c in characters],
    }


@pytest.fixture
def story_client(app, fake_gate):
    for c in ("aldric", "lyra"):
        fake_gate.add(ref(c))
    fake_gate.add(ref("highkeep", "locations"))
    c = app.test_client()
    assert c.post("/login", json={"username": "mara", "password": "mara-pass"}).status_code == 200
    c.post(f"/books/{BOOK}", json={"title": "The Ember Pact"})
    for eid, s, e in [("a", 0, 10), ("b", 0, 10), ("m", 20, 30), ("t", 40, 50)]:
        c.post(f"/books/{BOOK}/events/{eid}", json=_event(start=s, end=e, title=eid.upper()))
    c.post(f"/books/{BOOK}/plotlines/knights",
           json={"title": "The Knight's Road", "events": ["a", "m", "t"], "goals": ["g"]})
    c.post(f"/books/{BOOK}/plotlines/spies",
           json={"title": "The Spy's Shadow", "events": ["b", "m", "t"], "goals": ["g"]})
    c.post(f"/books/{BOOK}/terminus/t")
    return c


@pytest.mark.parametrize(
    "url,schema",
    [
        (f"/books/{BOOK}", "Book"),
        (f"/books/{BOOK}/plotlines/knights", "Plotline"),
        (f"/books/{BOOK}/plotlines/knights?expand=events", "Plotline"),
        (f"/books/{BOOK}/events/m", "Event"),
        (f"/books/{BOOK}/events/m/plotlines", "EventNeighborhood"),
        (f"/books/{BOOK}/validate", "ValidateReport"),
        (f"/books/{BOOK}/graph", "Graph"),
    ],
)
def test_live_response_conforms(schema_doc, story_client, url, schema):
    resp = story_client.get(url)
    assert resp.status_code == 200, resp.get_json()
    _validator(schema_doc, schema).validate(resp.get_json())


def test_live_preview_conforms(schema_doc, story_client):
    """The editor's dry-run: same presenter, its own documented shape."""
    resp = story_client.post(
        f"/books/{BOOK}/ui/plotline-preview",
        json={"id": "knights", "events": ["a", "m"], "goals": ["g"]},
    )
    assert resp.status_code == 200, resp.get_json()
    _validator(schema_doc, "PlotlinePreviewResult").validate(resp.get_json())


def test_live_error_conforms(schema_doc, story_client):
    """An error body must match the Finding schema, including its code enum."""
    resp = story_client.post(f"/books/{BOOK}/events/ghost", json=_event(characters=("nobody",)))
    assert resp.status_code == 422
    _validator(schema_doc, "Finding").validate(resp.get_json())


def test_live_conflicted_report_conforms(schema_doc, story_client, fake_gate):
    """The interesting case: a report with findings in every category."""
    fake_gate.add(ref("emberport", "locations"))
    # 'a' is at highkeep [0,10) with aldric; this puts him at emberport [0,10) too.
    assert story_client.post(
        f"/books/{BOOK}/events/clash", json=_event("emberport", 0, 10, ("aldric",))
    ).status_code == 201
    # out of order (m is [20,30), a is [0,10)) and never reaches the terminus
    assert story_client.post(
        f"/books/{BOOK}/plotlines/broken", json={"events": ["m", "a"], "goals": ["g"]}
    ).status_code == 201

    body = story_client.get(f"/books/{BOOK}/validate").get_json()
    assert body["status"] == "conflicted"
    assert body["temporal_conflicts"], "expected a temporal conflict"
    assert body["ordering"], "expected an ordering violation"
    assert body["convergence"]["failures"], "expected a convergence failure"
    _validator(schema_doc, "ValidateReport").validate(body)
