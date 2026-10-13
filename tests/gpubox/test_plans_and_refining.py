"""Plan approval and refinement, as the stack's client and the fake box do them."""

import pytest

from visualizer.gpubox import WorkerNotAwaitingApproval, WorkerRejected

from .spec import validator
from .test_client import Replay, make_client
from .test_fake import STEP, Clock, conforms, fake, research

PLAN = [{"q": "song tea", "language": "en"}]


@pytest.fixture
def clock():
    return Clock()


def test_the_client_posts_the_approved_queries():
    send = Replay((200, {"job": {"id": "j_1"}}))
    make_client(send).approve_plan("j/1", PLAN)
    (sent,) = send.requests
    assert sent["method"] == "POST" and sent["url"].endswith("/v1/jobs/j%2F1/plan")
    assert sent["body"] == {"queries": PLAN}


def test_the_client_raises_when_the_job_is_not_waiting():
    body = {"error": {"code": "not_awaiting_approval", "message": "running",
                      "retryable": False}}
    with pytest.raises(WorkerNotAwaitingApproval):
        make_client(Replay((409, body))).approve_plan("j_1", PLAN)


# -- the fake box ----------------------------------------------------------------


def waiting(clock, **changes):
    worker = fake(clock)
    job = worker.submit("research", research(approve_plan=True, **changes),
                        service="akasha", ref="r1")
    clock.now = 10 * STEP
    return worker, conforms(worker.status(job["id"]))


def test_the_fake_waits_for_approval_after_planning(clock):
    _, job = waiting(clock)
    assert job["state"] == "awaiting_approval" and job["result"] is None
    assert job["plan"]["approved"] is False and job["plan"]["expires_at"]
    validator("PlanApproval").validate({"queries": job["plan"]["queries"]})


def test_once_approved_the_fake_carries_on_from_searching(clock):
    worker, job = waiting(clock)
    resumed = conforms(worker.approve_plan(job["id"], PLAN))
    assert resumed["state"] == "running" and resumed["progress"]["stage"] == "searching"
    clock.now += 20 * STEP
    done = conforms(worker.status(job["id"]))
    assert done["state"] == "done"
    assert done["plan"] == {"queries": PLAN, "approved": True, "expires_at": None}
    assert done["finished_at"] > done["started_at"]


def test_the_fake_refuses_an_approval_twice(clock):
    worker, job = waiting(clock)
    worker.approve_plan(job["id"], PLAN)
    with pytest.raises(WorkerNotAwaitingApproval):
        worker.approve_plan(job["id"], PLAN)


def test_the_fake_refuses_a_malformed_plan(clock):
    worker, job = waiting(clock)
    with pytest.raises(WorkerRejected):
        worker.approve_plan(job["id"], [{"q": ""}])


def test_a_waiting_fake_job_can_be_cancelled(clock):
    worker, job = waiting(clock)
    assert conforms(worker.cancel(job["id"]))["state"] == "cancelled"


def test_an_unapproved_plan_expires(clock):
    worker, job = waiting(clock)
    clock.now += 25 * 3600
    expired = conforms(worker.status(job["id"]))
    assert expired["state"] == "failed" and expired["error"]["code"] == "plan_expired"


def test_with_no_delay_a_fake_plan_is_ready_at_once():
    worker = fake()
    job = worker.submit("research", research(approve_plan=True), service="akasha",
                        ref="r1")
    assert job["state"] == "awaiting_approval"
    assert worker.approve_plan(job["id"], PLAN)["state"] == "done"


REFINE = {"feedback": "More on tea houses.", "previous": {
    "title": "Tea", "facts": ["A fact."],
    "sources": [{"url": "https://example.org/kept", "title": "Kept"},
                {"url": "https://example.org/dropped", "title": "Dropped"}]},
    "exclude_urls": ["https://example.org/dropped"]}


def test_a_refined_fake_result_keeps_what_was_not_excluded_and_adds_one():
    job = fake().submit("research", research(refine=REFINE), service="akasha", ref="r")
    result = conforms(job)["result"]
    urls = [source["url"] for source in result["sources"]]
    assert urls[0] == "https://example.org/kept" and len(urls) == 2
    assert "https://example.org/dropped" not in urls
    assert "Refined" in result["article"]["body"]
    cited = {c["source"] for f in result["article"]["facts"] for c in f["citations"]}
    assert cited == {s["key"] for s in result["sources"]}


def test_the_fake_refuses_a_refinement_without_feedback():
    with pytest.raises(WorkerRejected):
        fake().submit("research", research(refine={"previous": {}}), service="akasha",
                      ref="r")
