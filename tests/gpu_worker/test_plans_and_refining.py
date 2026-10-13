"""Research the writer steers: approving the search plan, and refining a draft.

The pipeline against a scripted model and a fake web (as in test_pipelines),
then the store, runner and API carrying a job through ``awaiting_approval``.
"""

import copy
import sqlite3
from datetime import timedelta

import pytest

from tests.gpubox.spec import validator
from visualizer.gpu_worker.pipelines import AwaitingApproval, NoSources
from visualizer.gpu_worker.store import JobStore

from .conftest import AUTH, RESEARCH_JOB, RESEARCH_RESULT, submit
from .test_pipelines import REQUEST, research_model, run_research, signed

PLAN = [{"q": "song dynasty tea whisking", "language": "en"},
        {"q": "宋代 点茶", "language": "zh"}]
FEEDBACK = "Focus on how ordinary people drank tea, not the court."


def refining(**refine):
    return {**REQUEST, "refine": {
        "feedback": FEEDBACK,
        "previous": {"title": "Song-Dynasty Tea Culture",
                     "facts": ["Song tea was powdered and whisked."],
                     "sources": [{"url": "https://encyclopedia.example/ming",
                                  "title": "Ming tea"}]},
        **refine}}


# -- the pipeline: plans -------------------------------------------------------


def test_asked_to_wait_the_pipeline_stops_after_planning_with_its_plan():
    with pytest.raises(AwaitingApproval) as parked:
        run_research(request={**REQUEST, "approve_plan": True})
    assert parked.value.plan == {"queries": PLAN}
    validator("PlanApproval").validate(parked.value.plan)


def test_an_approved_plan_is_searched_as_approved_without_planning_again():
    edited = [{"q": "song tea house customs", "language": "en"}]
    result, model, search, ctx = run_research(
        request={**REQUEST, "approve_plan": True, "_approved_plan": edited})
    assert "plan" not in [step for step, _ in model.calls]
    assert "planning" not in ctx.stages
    assert search.queries == [("song tea house customs", "en")]
    validator("ResearchResult").validate(signed(result))


def test_a_plan_only_names_languages_that_were_asked_for():
    model = research_model(plan=lambda _: {"queries": [
        {"q": "tea", "language": "english"}, {"q": "茶", "language": "zh"}]})
    with pytest.raises(AwaitingApproval) as parked:
        run_research(model=model, request={**REQUEST, "approve_plan": True})
    assert parked.value.plan["queries"] == [{"q": "tea", "language": "en"},
                                            {"q": "茶", "language": "zh"}]


# -- the pipeline: refining ----------------------------------------------------


def test_refining_re_reads_the_previous_sources_first():
    result, _, _, _ = run_research(request=refining())
    assert result["sources"][0]["url"] == "https://encyclopedia.example/ming"
    validator("ResearchResult").validate(signed(result))


def test_previous_facts_are_never_trusted_only_re_extracted():
    gone = refining(previous={"title": "x", "facts": ["Tea was invented in 1850."],
                              "sources": [{"url": "https://missing.example/",
                                           "title": "Gone"}]})
    result, _, _, _ = run_research(request=gone)
    texts = [fact["text"] for fact in result["article"]["facts"]]
    assert "Tea was invented in 1850." not in texts
    assert "https://missing.example/" not in [s["url"] for s in result["sources"]]


@pytest.mark.parametrize("excluded,kept", [
    ("https://museum.example/tea", "https://encyclopedia.example/ming"),   # search
    ("https://encyclopedia.example/ming", "https://museum.example/tea"),   # before
])
def test_excluded_pages_are_read_neither_from_before_nor_from_search(excluded, kept):
    result, _, _, _ = run_research(request=refining(exclude_urls=[excluded]))
    assert [s["url"] for s in result["sources"]] == [kept]


def test_with_everything_excluded_there_is_nothing_to_use():
    with pytest.raises(NoSources):
        run_research(request=refining(exclude_urls=[
            "https://encyclopedia.example/ming", "https://museum.example/tea"]))


def test_feedback_reaches_planner_reader_and_writer_but_the_world_does_not():
    _, model, _, _ = run_research(request=refining())
    for step in ("plan", "extract", "write"):
        sent = " ".join(m["content"] for s, ms in model.calls if s == step for m in ms)
        assert FEEDBACK in sent, step
    plan = " ".join(m["content"] for s, ms in model.calls if s == "plan" for m in ms)
    assert "Song tea was powdered and whisked." in plan
    assert "The Traitor of Highkeep" not in plan and "corwin" not in plan


def test_kept_sources_alone_need_no_search():
    request = refining()
    request["max_sources"] = 1
    _, _, search, ctx = run_research(request=request)
    assert search.queries == [] and "searching" not in ctx.stages


def test_an_approved_empty_plan_re_reads_only_the_previous_sources():
    request = {**refining(), "approve_plan": True, "_approved_plan": []}
    result, _, search, _ = run_research(request=request)
    assert search.queries == []
    assert [s["url"] for s in result["sources"]] == ["https://encyclopedia.example/ming"]


# -- the store -----------------------------------------------------------------


def parked(store, clock, plan=None):
    job, _ = store.create("research", {**RESEARCH_JOB["request"], "approve_plan": True},
                          "h", None, clock())
    store.claim_next(clock())
    store.await_approval(job["id"], {"queries": plan or PLAN}, clock())
    return job["id"]


def test_a_parked_job_shows_its_plan_and_keeps_its_input(store, clock):
    job_id = parked(store, clock)
    job = store.get(job_id)
    validator("Job").validate(job)
    assert job["state"] == "awaiting_approval" and job["progress"] is None
    assert job["plan"] == {"queries": PLAN, "approved": False,
                           "expires_at": "2026-10-14T09:00:00Z"}
    assert store.raw_request(job_id) is not None
    assert store.counts() == {"queued": 0, "running": 0}


def test_approving_queues_it_again_ahead_of_later_jobs(store, clock):
    job_id = parked(store, clock)
    store.create("research", RESEARCH_JOB["request"], "h2", None, clock())
    edited = PLAN[:1]
    job, approved = store.approve(job_id, edited)
    assert approved and job["state"] == "queued" and job["position"] == 1
    assert job["plan"] == {"queries": edited, "approved": True, "expires_at": None}
    claimed_id, _, request = store.claim_next(clock())
    assert claimed_id == job_id and request["_approved_plan"] == edited


def test_only_a_parked_job_can_be_approved(store, clock):
    job, _ = store.create("research", RESEARCH_JOB["request"], "h", None, clock())
    assert store.approve(job["id"], PLAN)[1] is False
    assert store.approve("j_nope", PLAN) is None


def test_a_plan_nobody_approves_expires(store, clock):
    job_id = parked(store, clock)
    clock.advance(hours=23)
    store.sweep(clock())
    assert store.get(job_id)["state"] == "awaiting_approval"
    clock.advance(hours=1)
    store.sweep(clock())
    job = store.get(job_id)
    validator("Job").validate(job)
    assert job["state"] == "failed" and job["error"]["code"] == "plan_expired"
    assert store.raw_request(job_id) is None


def test_a_parked_job_can_be_cancelled(store, clock):
    job_id = parked(store, clock)
    assert store.cancel(job_id, clock())["state"] == "cancelled"
    assert store.raw_request(job_id) is None


def test_a_job_file_from_before_plans_gains_the_columns(tmp_path, clock):
    path = tmp_path / "old.sqlite3"
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE jobs (seq INTEGER PRIMARY KEY AUTOINCREMENT, "
                "id TEXT NOT NULL UNIQUE, kind TEXT NOT NULL, state TEXT NOT NULL, "
                "idem_key TEXT UNIQUE, body_hash TEXT NOT NULL, request TEXT, "
                "stage TEXT, message TEXT, created_at TEXT NOT NULL, started_at TEXT, "
                "finished_at TEXT, expires_at TEXT, result TEXT, error TEXT)")
    old.commit()
    old.close()
    store = JobStore(path, ttl=timedelta(hours=24))
    assert parked(store, clock).startswith("j_")


# -- the runner and the API ------------------------------------------------------


def stops_for_approval(request, ctx):
    if "_approved_plan" in request:
        return copy.deepcopy(RESEARCH_RESULT)
    raise AwaitingApproval({"queries": PLAN})


def test_a_job_parks_then_finishes_once_approved(client, store, runner, pipelines):
    pipelines.behaviour = stops_for_approval
    job_id = submit(client).get_json()["job"]["id"]
    runner.run_next()
    waiting = client.get(f"/v1/jobs/{job_id}", headers=AUTH).get_json()
    validator("JobEnvelope").validate(waiting)
    assert waiting["job"]["state"] == "awaiting_approval"
    assert runner.run_next() is False, "a parked job holds no place in the queue"

    approved = client.post(f"/v1/jobs/{job_id}/plan", headers=AUTH,
                           json={"queries": PLAN[:1]})
    assert approved.status_code == 200
    validator("JobEnvelope").validate(approved.get_json())
    runner.run_next()
    done = client.get(f"/v1/jobs/{job_id}", headers=AUTH).get_json()["job"]
    assert done["state"] == "done" and done["plan"]["approved"] is True
    assert pipelines.calls[-1][1]["_approved_plan"] == PLAN[:1]


def test_a_proposed_plan_outside_the_contract_fails_the_job(client, store, runner,
                                                            pipelines):
    def bad_plan(request, ctx):
        raise AwaitingApproval({"queries": [{"q": "", "language": "english"}]})

    pipelines.behaviour = bad_plan
    job_id = submit(client).get_json()["job"]["id"]
    runner.run_next()
    job = store.get(job_id)
    assert job["state"] == "failed" and job["error"]["code"] == "internal"


def test_approving_what_is_not_waiting_is_a_conflict(client):
    job_id = submit(client).get_json()["job"]["id"]
    response = client.post(f"/v1/jobs/{job_id}/plan", headers=AUTH,
                           json={"queries": PLAN})
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "not_awaiting_approval"
    validator("ErrorResponse").validate(response.get_json())


@pytest.mark.parametrize("body,status,code", [
    ({"queries": [{"q": "x", "language": "english"}]}, 400, "invalid_request"),
    ({"queries": PLAN * 4}, 400, "invalid_request"),
    ({"queries": PLAN, "extra": 1}, 400, "invalid_request"),
])
def test_an_approval_must_fit_the_contract(client, body, status, code):
    job_id = submit(client).get_json()["job"]["id"]
    response = client.post(f"/v1/jobs/{job_id}/plan", headers=AUTH, json=body)
    assert (response.status_code, response.get_json()["error"]["code"]) == (status,
                                                                             code)


def test_approving_an_unknown_job(client):
    response = client.post("/v1/jobs/j_nope/plan", headers=AUTH, json={"queries": PLAN})
    assert response.status_code == 404


def test_refining_requests_are_accepted_by_the_contract(client):
    body = copy.deepcopy(RESEARCH_JOB)
    body["request"].update(approve_plan=True, refine=refining()["refine"])
    assert submit(client, body).status_code == 202
