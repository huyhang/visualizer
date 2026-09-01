"""Contract tests for the published Akasha API.

The mirror of ``tests/chronos/test_contract.py``, which akasha did not have --
and the gap showed: the whole sharing API had drifted out of the hand-written
reference table without anything noticing. Three guarantees, so it cannot happen
again:

1. **Coverage** -- every JSON route the app registers is documented, and every
   documented route exists.
2. **Examples conform** -- each embedded example validates against its own schema.
3. **Live responses conform** -- real ``create_app`` responses validate against
   the schemas they claim.

Plus two consistency checks: no dangling ``$ref``, and the ``Document`` schema
agreeing with ``validation.py`` about what a flat document is -- the one rule the
spec could most easily describe wrongly.

The published document stays valid **OpenAPI 3.0**; ``_as_json_schema`` converts
its ``nullable`` spelling to JSON Schema before validating.
"""

import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft7Validator
from jsonschema.validators import RefResolver

_OPENAPI_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "akasha" / "openapi.json"
)

DB, COL = "earth", "lotr"
_COL_URL = f"/databases/{DB}/collections/{COL}"
_DOC_URL = f"{_COL_URL}/documents/aragorn"

_HTTP_METHODS = {"get", "post", "put", "delete"}

# Server-rendered pages and browser form posts: HTML in, redirect out. They are
# part of the app but not of the JSON contract, so they are named individually
# rather than skipped by pattern -- a new *JSON* route cannot slip through by
# resembling one of these.
_BROWSER_ONLY = {
    ("get", "/"),                       # the editor SPA shell
    ("get", "/static/{filename}"),
    # Assets every service loads, served out of the package root by
    # ``visualizer.shared_assets``. Asset routes, not part of the JSON API.
    ("get", "/static/js/shared/{filename}"),
    ("get", "/static/shared/{filename}"),
    ("get", "/login"),
    ("get", "/register"),
    ("get", "/change-password"),
    ("post", "/change-password"),
    ("get", "/account"),
    ("post", "/account/contacts"),      # the JSON twin is GET on the same path
    ("post", "/account/contacts/{username}/delete"),
}
# The admin console is entirely server-rendered forms.
_BROWSER_PREFIXES = ("/admin",)


@pytest.fixture(scope="module")
def openapi():
    return json.loads(_OPENAPI_PATH.read_text())


def _as_json_schema(node):
    """Translate the OpenAPI 3.0 dialect into plain JSON Schema.

    OpenAPI spells "may be null" as ``{"type": "x", "nullable": true}``; JSON
    Schema spells it ``{"type": ["x", "null"]}``. Without this every honestly
    null field (an article with no title, a tombstone with no body) is rejected.
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
            out = {"anyOf": [out, {"type": "null"}]}
    return out


@pytest.fixture(scope="module")
def schema_doc(openapi):
    return _as_json_schema(openapi)


def _validator(schema_doc, name):
    resolver = RefResolver.from_schema(schema_doc)
    return Draft7Validator({"$ref": f"#/components/schemas/{name}"}, resolver=resolver)


def _openapi_path(rule):
    path = str(rule)
    for arg in rule.arguments:
        for spelling in (f"<{arg}>", f"<path:{arg}>", f"<int:{arg}>"):
            path = path.replace(spelling, "{" + arg + "}")
    return path


def _app_operations(app):
    ops = set()
    for rule in app.url_map.iter_rules():
        path = _openapi_path(rule)
        if path.startswith(_BROWSER_PREFIXES):
            continue
        for method in rule.methods:
            method = method.lower()
            if method in _HTTP_METHODS and (method, path) not in _BROWSER_ONLY:
                ops.add((method, path))
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


def test_the_excluded_pages_really_are_pages(app):
    """The exclusion list is hand-kept, so hold it to the app: everything on it
    must still be a route, or it is stale cover for something that moved."""
    registered = {
        (m.lower(), _openapi_path(r))
        for r in app.url_map.iter_rules()
        for m in r.methods
        if m.lower() in _HTTP_METHODS
    }
    assert not (_BROWSER_ONLY - registered), (
        f"stale exclusions: {sorted(_BROWSER_ONLY - registered)}"
    )


def test_spec_is_well_formed(openapi):
    assert openapi["openapi"].startswith("3.")
    assert openapi["info"]["title"] == "Akasha API"
    assert "sessionCookie" in openapi["components"]["securitySchemes"]


def test_every_ref_resolves(openapi):
    defined = {
        f"#/components/{section}/{name}"
        for section in ("schemas", "responses", "parameters", "requestBodies", "headers")
        for name in openapi["components"].get(section, {})
    }
    used = set(re.findall(r'"\$ref":\s*"([^"]+)"', json.dumps(openapi)))
    assert not (used - defined), f"dangling $refs: {sorted(used - defined)}"


def test_the_document_schema_agrees_with_the_validator(schema_doc):
    """The flat rule is the one thing the spec could most easily describe wrongly,
    so it is checked against the implementation rather than by eye."""
    from visualizer.akasha.errors import InvalidDocument
    from visualizer.akasha.validation import validate_document

    document = _validator(schema_doc, "Document")
    allowed = {"title": "Aragorn", "age": 87, "alive": True, "heir": None,
               "titles": ["Strider", "Elessar"]}
    rejected = [{"stats": {"str": 10}}, {"paths": [["a"], ["b"]]}, {"cast": [{"id": "x"}]}]

    validate_document(allowed)          # the implementation takes it...
    document.validate(allowed)          # ...and so does the spec

    for bad in rejected:
        with pytest.raises(InvalidDocument):
            validate_document(bad)
        assert not document.is_valid(bad), f"the spec allows what the API rejects: {bad}"


# -- 2. embedded examples ----------------------------------------------------


def test_embedded_examples_conform_to_their_schemas(openapi, schema_doc):
    examples = [
        (name, s["example"])
        for name, s in openapi["components"]["schemas"].items()
        if "example" in s
    ]
    assert len(examples) >= 20, "expected an example on essentially every schema"
    for name, example in examples:
        _validator(schema_doc, name).validate(example)


# -- 3. live responses -------------------------------------------------------


@pytest.fixture
def seeded(client):
    """One collection with a live article, a tombstone, and a collaborator."""
    from visualizer.auth import AuthStore  # noqa: F401  (documents the shared store)

    client.post(_COL_URL)
    client.post(_DOC_URL, json={"title": "Aragorn", "body": "Heir of [[isildur]].",
                                "race": "Man", "titles": ["Strider", "Elessar"]})
    client.put(_DOC_URL, json={"title": "Aragorn", "race": "Man"},
               headers={"If-Match": "1"})
    client.post(f"{_COL_URL}/documents/boromir", json={"title": "Boromir"})
    client.delete(f"{_COL_URL}/documents/boromir", headers={"If-Match": "1"})
    return client


@pytest.mark.parametrize(
    "url,schema",
    [
        ("/health", "Health"),
        ("/auth/me", "Identity"),
        ("/databases", "DatabaseList"),
        (f"/databases/{DB}/collections", "CollectionList"),
        (f"{_COL_URL}/documents", "ArticlePage"),
        (f"{_COL_URL}/documents?filter=man&page=1&per_page=10", "ArticlePage"),
        (f"{_COL_URL}/deleted", "DeletedList"),
        (f"{_COL_URL}/search?text=man", "SearchResults"),
        (_DOC_URL, "DocumentResult"),
        (f"{_DOC_URL}/versions", "VersionList"),
        (f"{_DOC_URL}/versions/1", "Snapshot"),
        (f"{_DOC_URL}/diff?from=1&to=2", "Diff"),
        (f"{_COL_URL}/collaborators", "CollaboratorList"),
        ("/recent?limit=3", "RecentList"),
        ("/suggest?q=arag", "SuggestionList"),
        ("/account/contacts", "Contacts"),
    ],
)
def test_live_response_conforms(schema_doc, seeded, url, schema):
    resp = seeded.get(url)
    assert resp.status_code == 200, resp.get_json()
    _validator(schema_doc, schema).validate(resp.get_json())


def test_live_writes_conform(schema_doc, seeded):
    created = seeded.post(f"{_COL_URL}/documents/faramir", json={"title": "Faramir"})
    assert created.status_code == 201
    _validator(schema_doc, "DocumentResult").validate(created.get_json())
    assert created.headers["ETag"] == '"1"', "the documented ETag header"

    namespace = seeded.post(f"/databases/{DB}/collections/spare")
    assert namespace.status_code == 201
    _validator(schema_doc, "NamespaceResult").validate(namespace.get_json())

    dropped = seeded.delete(f"/databases/{DB}/collections/spare")
    assert dropped.status_code == 200
    _validator(schema_doc, "NamespaceDeleted").validate(dropped.get_json())


def test_live_restore_conforms(schema_doc, seeded):
    """Restoring a *deleted* article — the case the schemas exist to describe."""
    resp = seeded.post(f"{_COL_URL}/documents/boromir/restore/1")
    assert resp.status_code == 200
    _validator(schema_doc, "DocumentResult").validate(resp.get_json())


def test_live_sharing_conforms(schema_doc, seeded, auth_store):
    from werkzeug.security import generate_password_hash

    auth_store.create_user("bob", generate_password_hash("pw"), role="user")
    shared = seeded.put(f"{_COL_URL}/collaborators/bob", json={"role": "editor"})
    assert shared.status_code == 200
    _validator(schema_doc, "CollaboratorResult").validate(shared.get_json())
    _validator(schema_doc, "CollaboratorList").validate(
        seeded.get(f"{_COL_URL}/collaborators").get_json()
    )


@pytest.mark.parametrize(
    "method,url,status",
    [
        ("get", f"{_COL_URL}/documents/ghost", 404),
        ("get", "/databases/_auth/collections", 400),
        ("post", f"{_COL_URL}/documents/aragorn", 409),
    ],
)
def test_live_errors_conform(schema_doc, seeded, method, url, status):
    resp = seeded.open(url, method=method.upper(), json={"title": "x"})
    assert resp.status_code == status, resp.get_json()
    _validator(schema_doc, "Error").validate(resp.get_json())


def test_an_unauthenticated_call_is_documented_as_401(schema_doc, anon_client):
    resp = anon_client.get("/databases")
    assert resp.status_code == 401
