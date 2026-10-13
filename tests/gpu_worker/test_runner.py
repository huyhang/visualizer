"""The runner: one job at a time, every ending recorded as the contract names it."""

import copy
import threading
import time
from datetime import UTC, datetime

import pytest

from tests.gpubox.spec import validator
from visualizer.gpu_worker.pipelines import (
    NoSources,
    NotBuiltPipelines,
    PipelineUnavailable,
)
from visualizer.gpu_worker.runner import Runner

from .conftest import RESEARCH_JOB, RESEARCH_RESULT, REVIEW_JOB, REVIEW_RESULT


def queue(store, clock, body=RESEARCH_JOB, key=None):
    job, _ = store.create(body["kind"], body["request"], "hash", key, clock())
    return job["id"]


def ended(store, job_id):
    job = store.get(job_id)
    validator("Job").validate(job)
    return job


def test_jobs_run_oldest_first_and_one_per_call(store, runner, pipelines, clock):
    first = queue(store, clock)
    second = queue(store, clock, REVIEW_JOB)
    assert runner.run_next() is True
    assert [kind for kind, _ in pipelines.calls] == ["research"]
    assert ended(store, first)["state"] == "done"
    assert ended(store, second)["state"] == "queued"
    runner.run_next()
    assert ended(store, second)["state"] == "done"
    assert runner.run_next() is False


def test_progress_is_visible_while_a_job_runs(store, runner, pipelines, clock):
    job_id = queue(store, clock)
    seen = []

    def look(request, ctx):
        seen.append(store.get(job_id))
        return copy.deepcopy(RESEARCH_RESULT)

    pipelines.behaviour = look
    runner.run_next()
    (during,) = seen
    validator("Job").validate(during)
    assert during["state"] == "running" and during["started_at"]
    assert during["progress"] == {"stage": "writing", "message": "writing…"}
    assert ended(store, job_id)["progress"] is None


def test_a_job_cancelled_mid_run_stays_cancelled(store, runner, pipelines, clock):
    job_id = queue(store, clock)

    def cancel_then_continue(request, ctx):
        store.cancel(job_id, clock())
        ctx.progress("writing")
        raise AssertionError("progress() should have stopped the pipeline")

    pipelines.behaviour = cancel_then_continue
    runner.run_next()
    job = ended(store, job_id)
    assert job["state"] == "cancelled" and job["result"] is None


def test_running_past_the_time_limit_fails_as_timeout(store, runner, pipelines,
                                                     clock):
    job_id = queue(store, clock)

    def dawdle(request, ctx):
        clock.advance(minutes=16)
        ctx.progress("writing")

    pipelines.behaviour = dawdle
    runner.run_next()
    job = ended(store, job_id)
    assert job["state"] == "failed"
    assert job["error"] == {"code": "timeout", "retryable": True,
                            "message": "The job exceeded its time limit"}


@pytest.mark.parametrize("raised,code,retryable", [
    (PipelineUnavailable("Ollama stopped responding"), "unavailable", True),
    (NoSources("No usable sources were found"), "no_sources", False),
    (RuntimeError("bug while reading the question about Corwin"), "internal", False),
])
def test_pipeline_failures_become_documented_codes(store, runner, pipelines, clock,
                                                   raised, code, retryable):
    job_id = queue(store, clock)

    def fail(request, ctx):
        raise raised

    pipelines.behaviour = fail
    runner.run_next()
    error = ended(store, job_id)["error"]
    assert (error["code"], error["retryable"]) == (code, retryable)
    assert "Corwin" not in error["message"], "a bug's message is never passed on"


def test_a_result_outside_the_contract_never_reaches_a_caller(store, runner,
                                                            pipelines, clock):
    job_id = queue(store, clock)
    pipelines.behaviour = lambda request, ctx: {"article": "not like this"}
    runner.run_next()
    job = ended(store, job_id)
    assert job["state"] == "failed" and job["result"] is None
    assert job["error"]["code"] == "internal"


def test_review_issues_must_quote_their_own_block(store, runner, pipelines, clock):
    job_id = queue(store, clock, REVIEW_JOB)
    invented = copy.deepcopy(REVIEW_RESULT)
    invented["issues"].append({**invented["issues"][0],
                               "quote": "words that are not in the chapter"})
    invented["issues"].append({**invented["issues"][0], "block": "b99"})
    pipelines.behaviour = lambda request, ctx: invented
    runner.run_next()
    issues = ended(store, job_id)["result"]["issues"]
    assert issues == REVIEW_RESULT["issues"]


def test_the_shipped_pipelines_say_they_are_not_built(store, contract, clock,
                                                      signer):
    runner = Runner(store, NotBuiltPipelines(), contract, sign=signer.sign,
                    clock=clock)
    research = queue(store, clock)
    review = queue(store, clock, REVIEW_JOB)
    runner.run_next()
    runner.run_next()
    for job_id, kind in ((research, "research"), (review, "review")):
        error = ended(store, job_id)["error"]
        assert error["code"] == "internal"
        assert error["message"] == f"The {kind} pipeline is not built yet"


def test_on_its_thread_it_never_runs_two_jobs_at_once(store, contract, signer):
    running = []
    peak = []
    lock = threading.Lock()

    class Slow:
        def research(self, request, ctx):
            with lock:
                running.append(1)
                peak.append(len(running))
            time.sleep(0.05)
            with lock:
                running.pop()
            return copy.deepcopy(RESEARCH_RESULT)

    runner = Runner(store, Slow(), contract, sign=signer.sign, poll_seconds=0.01)
    ids = [store.create("research", RESEARCH_JOB["request"], "h", None,
                        datetime.now(UTC))[0]["id"] for _ in range(4)]
    runner.start()
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and any(
                store.get(i)["state"] != "done" for i in ids):
            time.sleep(0.02)
    finally:
        runner.stop()
    assert all(store.get(i)["state"] == "done" for i in ids)
    assert max(peak) == 1
