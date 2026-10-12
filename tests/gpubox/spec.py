"""The GPU worker's OpenAPI document, as validators the tests can use.

The spec is OpenAPI 3.1, so its schemas are plain JSON Schema 2020-12 -- unlike
the services' 3.0 documents, there is no ``nullable`` dialect to translate. It is
registered once under a fixed URI so every ``#/components/...`` reference
resolves, whichever schema a test starts from.
"""

import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

SPEC_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "gpu_worker" / "openapi.json"
)
SPEC = json.loads(SPEC_PATH.read_text())

_URI = "urn:visualizer:gpu-worker-openapi"
_REGISTRY = Registry().with_resource(
    _URI, Resource(contents=SPEC, specification=DRAFT202012)
)


def _anchored(node):
    """A copy of ``node`` whose local ``#/...`` references point into the spec."""
    if isinstance(node, list):
        return [_anchored(item) for item in node]
    if not isinstance(node, dict):
        return node
    out = {key: _anchored(value) for key, value in node.items()}
    ref = out.get("$ref")
    if isinstance(ref, str) and ref.startswith("#"):
        out["$ref"] = _URI + ref
    return out


def validator_for(schema: dict) -> Draft202012Validator:
    """A validator for any schema node lifted out of the spec."""
    return Draft202012Validator(_anchored(copy.deepcopy(schema)), registry=_REGISTRY)


def validator(name: str) -> Draft202012Validator:
    """A validator for one named component schema."""
    return validator_for({"$ref": f"#/components/schemas/{name}"})


def error_codes() -> set[str]:
    """Every ``code`` an error from the worker can carry."""
    return set(SPEC["components"]["schemas"]["Error"]["properties"]["code"]["enum"])
