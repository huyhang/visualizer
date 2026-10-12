"""The GPU worker's published contract holds together on its own.

Nothing implements it yet, which is exactly when it needs checking: the client,
the fake and eventually the worker are all written against this document, so a
reference that dangles or an example that contradicts its own schema would be
copied into every one of them. The client and fake suites hold their payloads
to the same schemas.
"""

from .spec import SPEC, validator, validator_for

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def _walk(node, pointer=""):
    """Yield (pointer, node) for every dict in the document."""
    if isinstance(node, dict):
        yield pointer, node
        for key, value in node.items():
            yield from _walk(value, f"{pointer}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{pointer}/{index}")


def _resolve(ref: str):
    node = SPEC
    for part in ref.removeprefix("#/").split("/"):
        node = node[part.replace("~1", "/").replace("~0", "~")]
    return node


def _embedded_examples():
    """(where, schema, example) for every example the document carries."""
    found = []
    for pointer, node in _walk(SPEC):
        if "schema" in node and "example" in node:
            found.append((pointer, node["schema"], node["example"]))
        if "schema" in node and isinstance(node.get("examples"), dict):
            for name, example in node["examples"].items():
                found.append((f"{pointer}/examples/{name}", node["schema"],
                              example["value"]))
    for name, schema in SPEC["components"]["schemas"].items():
        for index, example in enumerate(schema.get("examples", [])):
            found.append((f"/components/schemas/{name}/examples/{index}",
                          {"$ref": f"#/components/schemas/{name}"}, example))
    return found


def test_it_is_an_openapi_31_document():
    assert SPEC["openapi"] == "3.1.0"
    assert {"health", "jobs"} <= {p.strip("/").split("/")[0] for p in SPEC["paths"]}


def test_every_ref_resolves():
    refs = [node["$ref"] for _, node in _walk(SPEC) if isinstance(node.get("$ref"), str)]
    assert refs
    for ref in refs:
        assert ref.startswith("#/"), f"external reference: {ref}"
        _resolve(ref)  # raises KeyError if it dangles


def test_every_operation_requires_the_bearer_token():
    assert SPEC["security"] == [{"bearerAuth": []}]
    for path, item in SPEC["paths"].items():
        for method, operation in item.items():
            if method in HTTP_METHODS:
                assert operation.get("security", SPEC["security"]), (method, path)
                assert "401" in operation["responses"], (method, path)


def test_every_embedded_example_conforms_to_its_schema():
    examples = _embedded_examples()
    assert len(examples) >= 15, "examples went missing from the spec"
    for where, schema, example in examples:
        errors = sorted(validator_for(schema).iter_errors(example), key=str)
        assert not errors, f"{where}: {errors[0].message}"


def test_a_job_result_is_research_or_review_never_both():
    """The ``oneOf`` on a finished job only works if the two shapes are disjoint."""
    research = _resolve("#/paths/~1jobs~1{job_id}/get/responses/200/content/"
                        "application~1json/examples/researchDone")["value"]
    review = _resolve("#/paths/~1jobs~1{job_id}/get/responses/200/content/"
                      "application~1json/examples/reviewDone")["value"]
    assert validator("ResearchResult").is_valid(research["job"]["result"])
    assert not validator("ReviewResult").is_valid(research["job"]["result"])
    assert validator("ReviewResult").is_valid(review["job"]["result"])
    assert not validator("ResearchResult").is_valid(review["job"]["result"])
