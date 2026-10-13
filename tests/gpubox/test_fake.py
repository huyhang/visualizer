"""The fake GPU box keeps the contract, and every state it promises is reachable."""

import inspect
import re
from datetime import UTC, datetime

import pytest

from visualizer.gpubox import (
    JOB_FAILURE_CODES,
    WorkerBusy,
    WorkerClient,
    WorkerJobNotFound,
    WorkerRejected,
    WorkerUnavailable,
    availability,
)
from visualizer.gpubox.fake import MODES, FakeWorker

from .spec import SPEC, validator

EXAMPLE_REQUESTS = SPEC["paths"]["/jobs"]["post"]["requestBody"]["content"][
    "application/json"]["examples"]
RESEARCH = EXAMPLE_REQUESTS["research"]["value"]["request"]
REVIEW = EXAMPLE_REQUESTS["review"]["value"]["request"]
STEP = 1.5


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


def fake(clock=None, **kwargs):
    if clock is not None:
        kwargs.update(clock=clock, stage_seconds=STEP)
    return FakeWorker(now=lambda: datetime(2026, 10, 13, 9, 0, tzinfo=UTC), **kwargs)


def research(**changes):
    return {**RESEARCH, **changes}


def conforms(job):
    validator("JobEnvelope").validate({"job": job})
    return job


def finished(worker, kind="research", request=None, ref="r1"):
    request = request if request is not None else (RESEARCH if kind == "research"
                                                   else REVIEW)
    job = worker.submit(kind, request, service="akasha", ref=ref)
    return conforms(worker.status(job["id"]))


# -- the same calls as the real client ---------------------------------------


def test_it_answers_the_same_calls_as_the_real_client():
    for name in ("health", "submit", "status", "cancel"):
        real = inspect.signature(getattr(WorkerClient, name))
        stand_in = inspect.signature(getattr(FakeWorker, name))
        assert list(stand_in.parameters) == list(real.parameters), name


# -- every state reachable ---------------------------------------------------


@pytest.mark.parametrize("mode", MODES)
def test_each_mode_reads_as_the_state_of_the_same_name(mode):
    assert availability(fake(mode=mode), "research")["state"] == mode


@pytest.mark.parametrize("mode", [m for m in MODES
                                  if m not in ("unreachable", "misconfigured",
                                               "incompatible")])
def test_its_health_reports_conform(mode):
    for verifier in ("up", "down", "not_configured"):
        validator("Health").validate(fake(mode=mode, verifier=verifier).health())


def test_a_cold_box_warms_up_once_a_job_has_run():
    worker = fake(mode="cold")
    finished(worker)
    assert availability(worker, "research")["state"] == "ready"


def test_degraded_means_search_is_down_so_review_still_runs():
    worker = fake(mode="degraded")
    assert availability(worker, "review")["can_submit"]
    assert finished(worker, "review")["state"] == "done"


@pytest.mark.parametrize("mode,error", [("unreachable", WorkerUnavailable),
                                        ("misconfigured", WorkerRejected)])
def test_a_box_you_cannot_reach_refuses_every_call(mode, error):
    worker = fake()
    job = worker.submit("research", RESEARCH, service="akasha", ref="r1")
    worker.set_mode(mode)
    for call in (worker.health, lambda: worker.status(job["id"]),
                 lambda: worker.cancel(job["id"]),
                 lambda: worker.submit("research", RESEARCH, service="akasha",
                                       ref="r2")):
        with pytest.raises(error):
            call()


def test_a_full_queue_turns_new_jobs_away():
    with pytest.raises(WorkerBusy) as raised:
        fake(mode="queue_full").submit("research", RESEARCH, service="akasha",
                                       ref="r1")
    assert raised.value.code == "queue_full" and raised.value.retry_after


# -- a job's life ------------------------------------------------------------


def test_a_research_job_walks_the_documented_stages(clock):
    worker = fake(clock, mode="cold")
    job = conforms(worker.submit("research", RESEARCH, service="akasha", ref="r1"))
    assert (job["state"], job["position"]) == ("queued", 1)
    seen = []
    while (job := conforms(worker.status(job["id"])))["state"] in ("queued",
                                                                   "running"):
        if job["progress"]:
            seen.append(job["progress"]["stage"])
        clock.now += STEP
    assert list(dict.fromkeys(seen)) == [
        "loading_model", "planning", "searching", "fetching", "extracting",
        "verifying", "writing", "second_check"]
    assert job["state"] == "done"
    assert job["finished_at"] and job["expires_at"] > job["finished_at"]


def test_the_queue_count_follows_the_jobs(clock):
    worker = fake(clock)
    worker.submit("research", RESEARCH, service="akasha", ref="r1")
    assert worker.health()["queue"]["queued"] == 1
    clock.now += STEP
    assert worker.health()["queue"] == {"queued": 0, "running": 1, "max": 20}


def test_with_no_delay_a_job_is_finished_at_once():
    assert finished(fake())["state"] == "done"


def test_retrying_with_the_same_key_returns_the_same_job():
    worker = fake()
    first = worker.submit("research", RESEARCH, service="akasha", ref="r1")
    assert worker.submit("research", RESEARCH, service="akasha", ref="r1")["id"] == \
        first["id"]
    with pytest.raises(WorkerRejected) as raised:
        worker.submit("research", research(question="Something else"),
                      service="akasha", ref="r1")
    assert raised.value.code == "idempotency_conflict"


def test_cancelling(clock):
    worker = fake(clock)
    queued = worker.submit("research", RESEARCH, service="akasha", ref="r1")
    cancelled = conforms(worker.cancel(queued["id"]))
    assert cancelled["state"] == "cancelled" and cancelled["started_at"] is None
    clock.now += 100
    assert worker.status(queued["id"])["state"] == "cancelled"
    later = worker.submit("research", RESEARCH, service="akasha", ref="r2")
    clock.now += 100
    assert worker.status(later["id"])["state"] == "done"
    assert worker.cancel(later["id"])["state"] == "done", "finished jobs stay finished"


def test_unknown_jobs_are_not_found():
    with pytest.raises(WorkerJobNotFound):
        fake().status("fake_999999")


@pytest.mark.parametrize("code", sorted(JOB_FAILURE_CODES))
def test_any_documented_failure_can_be_staged(code):
    worker = fake()
    worker.fail_next(code)
    job = finished(worker)
    assert job["state"] == "failed" and job["error"]["code"] == code
    assert finished(worker, ref="r2")["state"] == "done", "only the next job fails"


@pytest.mark.parametrize("kind,request_", [
    ("research", research(question="hi")),
    ("research", {"languages": ["en"]}),
    ("review", {"chapter": {"title": "x", "blocks": []}, "references": []}),
    ("portraits", {"question": "Song tea"}),
])
def test_it_refuses_what_the_worker_would_refuse(kind, request_):
    with pytest.raises(WorkerRejected) as raised:
        fake().submit(kind, request_, service="akasha", ref="r1")
    assert raised.value.code == "invalid_request"


# -- results that keep the worker's promises ---------------------------------


def test_research_results_cite_quotes_that_are_really_there():
    result = finished(fake(), request=research(include_images=True))["result"]
    validator("ResearchResult").validate(result)
    excerpts = {s["key"]: s["excerpts"] for s in result["sources"]}
    for fact in result["article"]["facts"]:
        for citation in fact["citations"]:
            assert citation["quote"] in excerpts[citation["source"]]
    cited = set(re.findall(r"\[\[cite:(s\d+)\]\]", result["article"]["body"]))
    assert cited <= set(excerpts)
    known = {a["ref"] for a in RESEARCH["known_articles"]}
    assert set(result["article"]["links"]) <= known
    assert result["article"]["image_candidates"]
    assert all("[Fake]" in f["text"] for f in result["article"]["facts"])


def test_images_only_when_asked_for():
    result = finished(fake(), request=research(include_images=False))["result"]
    assert result["article"]["image_candidates"] == []


def test_review_issues_quote_their_own_block_verbatim():
    result = finished(fake(), "review")["result"]
    validator("ReviewResult").validate(result)
    texts = {b["id"]: b["text"] for b in REVIEW["chapter"]["blocks"]}
    refs = {r["ref"] for r in REVIEW["references"]}
    assert result["issues"]
    for issue in result["issues"]:
        assert issue["quote"] and issue["quote"] in texts[issue["block"]]
        assert issue["reference"] is None or issue["reference"] in refs


@pytest.mark.parametrize("verifier,verify,status,reason,check", [
    ("up", "auto", "checked", None, "supported"),
    ("down", "auto", "skipped", "verifier_unavailable", "unchecked"),
    ("not_configured", "auto", "off", "not_configured", "unchecked"),
    ("up", "off", "off", "caller_off", "unchecked"),
])
def test_second_check_outcomes(verifier, verify, status, reason, check):
    job = finished(fake(verifier=verifier), request=research(verify=verify))
    verification = job["result"]["verification"]
    assert (verification["status"], verification["reason"]) == (status, reason)
    assert job["result"]["article"]["facts"][0]["check"]["status"] == check
    review = finished(fake(verifier=verifier), "review",
                      request={**REVIEW, "verify": verify}, ref="r2")["result"]
    assert review["verification"]["status"] == status
    assert {i["verified"] for i in review["issues"]} == {
        True if status == "checked" else None}


def test_a_required_second_check_fails_the_job_when_the_verifier_is_down():
    job = finished(fake(verifier="down"), request=research(verify="required"))
    assert job["state"] == "failed" and job["error"]["code"] == "unavailable"
