"""The worker's HTTP API answers exactly as the contract documents."""

import copy

import pytest

from tests.gpubox.spec import validator
from visualizer.gpu_worker.app import create_app

from .conftest import (
    AUTH,
    DISCUSSION_JOB,
    RESEARCH_JOB,
    REVIEW_JOB,
    SPEC,
    StaticProbes,
    submit,
)

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def documented_error(response, status, code):
    assert response.status_code == status, response.get_json()
    validator("ErrorResponse").validate(response.get_json())
    assert response.get_json()["error"]["code"] == code
    return response.get_json()["error"]


# -- coverage ----------------------------------------------------------------


def test_it_serves_exactly_the_documented_operations(app):
    served = set()
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        path = str(rule).removeprefix("/v1").replace("<job_id>", "{job_id}")
        served |= {(m.lower(), path) for m in rule.methods
                   if m.lower() in HTTP_METHODS}
    documented = {(method, path) for path, item in SPEC["paths"].items()
                  for method in item if method in HTTP_METHODS}
    assert served == documented


# -- authentication ----------------------------------------------------------


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"},
                                     {"Authorization": "t" * 32}])
@pytest.mark.parametrize("method,path", [("get", "/v1/health"),
                                         ("post", "/v1/jobs"),
                                         ("get", "/v1/jobs/j_1"),
                                         ("delete", "/v1/jobs/j_1"),
                                         ("get", "/v1/nowhere")])
def test_every_call_needs_the_token(client, headers, method, path):
    response = client.open(path, method=method.upper(), headers=headers,
                           json=RESEARCH_JOB)
    documented_error(response, 401, "unauthorized")


# -- health ------------------------------------------------------------------


def test_health_conforms_and_counts_the_queue(client, store, clock):
    store.create("research", RESEARCH_JOB["request"], "h1", None, clock())
    body = client.get("/v1/health", headers=AUTH).get_json()
    validator("Health").validate(body)
    assert body["ok"] is True and body["api_version"] == "1"
    assert body["queue"] == {"queued": 1, "running": 0, "max": 3}


@pytest.mark.parametrize("section", ["ollama", "searxng"])
def test_health_is_not_ok_when_a_dependency_is_down(config, store, runner,
                                                    contract, images, clock,
                                                    section):
    probes = StaticProbes()
    probes.sections[section]["status"] = "down"
    client = create_app(config, store, runner, probes, contract, images,
                        clock=clock).test_client()
    body = client.get("/v1/health", headers=AUTH).get_json()
    validator("Health").validate(body)
    assert body["ok"] is False


def test_the_optional_verifier_never_affects_ok(config, store, runner, contract,
                                                images, clock):
    probes = StaticProbes(verifier={"status": "down", "models": {
        "research": "bespoke-minicheck", "review": "gemma3:27b"}})
    client = create_app(config, store, runner, probes, contract, images,
                        clock=clock).test_client()
    assert client.get("/v1/health", headers=AUTH).get_json()["ok"] is True


# -- creating jobs -----------------------------------------------------------


@pytest.mark.parametrize("body", [RESEARCH_JOB, REVIEW_JOB, DISCUSSION_JOB],
                         ids=["research", "review", "discussion"])
def test_the_documented_examples_are_accepted(client, body):
    response = submit(client, body)
    assert response.status_code == 202
    envelope = response.get_json()
    validator("JobEnvelope").validate(envelope)
    assert envelope["job"]["state"] == "queued"
    assert response.headers["Location"] == f"/v1/jobs/{envelope['job']['id']}"


def test_queued_jobs_know_their_place(client):
    first = submit(client).get_json()["job"]
    second = submit(client, REVIEW_JOB).get_json()["job"]
    assert (first["position"], second["position"]) == (1, 2)


def test_a_retried_request_returns_the_original_job(client):
    first = submit(client, key="akasha-job-1")
    reordered = dict(reversed(list(RESEARCH_JOB.items())))
    again = submit(client, reordered, key="akasha-job-1")
    assert again.status_code == 200
    assert again.get_json()["job"]["id"] == first.get_json()["job"]["id"]


def test_a_reused_key_with_a_different_body_is_a_conflict(client):
    submit(client, key="akasha-job-1")
    changed = copy.deepcopy(RESEARCH_JOB)
    changed["request"]["question"] = "Tang-dynasty hairpins"
    documented_error(submit(client, changed, key="akasha-job-1"), 409,
                     "idempotency_conflict")


def test_a_full_queue_says_when_to_come_back(client):
    for n in range(3):
        assert submit(client, key=f"k{n}").status_code == 202
    response = submit(client, key="k3")
    error = documented_error(response, 429, "queue_full")
    assert error["retryable"] is True
    assert response.headers["Retry-After"] == "30"


@pytest.mark.parametrize("body,where", [
    ({**RESEARCH_JOB, "request": {"languages": ["en"]}}, "request"),
    ({**RESEARCH_JOB, "kind": "portraits"}, "kind"),
    ({**RESEARCH_JOB, "client": {"service": "chronos", "ref": "x"}}, "client"),
    ({**RESEARCH_JOB, "extra": 1}, "the body"),
])
def test_schema_violations_are_refused(client, body, where):
    error = documented_error(submit(client, body), 400, "invalid_request")
    assert where in error["message"]


def test_a_body_that_is_not_json(client):
    response = client.post("/v1/jobs", data=b"{nope", headers=AUTH,
                           content_type="application/json")
    documented_error(response, 400, "invalid_request")


def test_refusals_never_echo_what_was_sent(client):
    secret = "THE-TRAITOR-IS-CORWIN " * 30   # over the 500-character limit
    body = copy.deepcopy(RESEARCH_JOB)
    body["request"]["question"] = secret
    error = documented_error(submit(client, body), 400, "invalid_request")
    assert "CORWIN" not in error["message"]
    assert "request.question" in error["message"]


def test_research_requests_are_small(client):
    body = copy.deepcopy(RESEARCH_JOB)
    body["request"]["known_articles"] = [
        {"ref": f"world/research/article-{n:03d}", "title": "x" * 300}
        for n in range(200)]
    documented_error(submit(client, body), 413, "payload_too_large")


def test_a_discussion_carries_one_passage_not_a_chapter(client):
    body = copy.deepcopy(DISCUSSION_JOB)
    # Within every per-field limit, but Chinese is three bytes a character.
    body["request"]["messages"] = [{"role": "writer", "text": "字" * 4000}] * 40
    documented_error(submit(client, body), 413, "payload_too_large")


def test_nothing_may_exceed_the_largest_limit(client):
    body = copy.deepcopy(REVIEW_JOB)
    body["request"]["chapter"]["blocks"] = [
        {"id": f"b{n}", "text": "y" * 1000} for n in range(1200)]
    documented_error(submit(client, body), 413, "payload_too_large")


# -- reading and cancelling --------------------------------------------------


def test_a_finished_job_carries_its_result(client, runner):
    job = submit(client).get_json()["job"]
    runner.run_next()
    envelope = client.get(f"/v1/jobs/{job['id']}", headers=AUTH).get_json()
    validator("JobEnvelope").validate(envelope)
    assert envelope["job"]["state"] == "done"
    assert envelope["job"]["expires_at"] > envelope["job"]["finished_at"]


def test_cancelling_a_queued_job(client, runner):
    job = submit(client).get_json()["job"]
    response = client.delete(f"/v1/jobs/{job['id']}", headers=AUTH)
    validator("JobEnvelope").validate(response.get_json())
    assert response.get_json()["job"]["state"] == "cancelled"
    assert runner.run_next() is False, "a cancelled job is not run"
    again = client.delete(f"/v1/jobs/{job['id']}", headers=AUTH)
    assert again.get_json()["job"]["state"] == "cancelled"


@pytest.mark.parametrize("method", ["get", "delete"])
def test_unknown_jobs_are_not_found(client, method):
    response = client.open("/v1/jobs/j_missing", method=method.upper(), headers=AUTH)
    documented_error(response, 404, "not_found")


def test_unknown_routes_and_methods_answer_in_the_error_shape(client):
    documented_error(client.get("/v1/nowhere", headers=AUTH), 404, "not_found")
    response = client.put("/v1/jobs", headers=AUTH, json={})
    assert response.status_code == 405
    validator("ErrorResponse").validate(response.get_json())
