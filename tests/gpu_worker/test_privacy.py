"""The worker never logs, echoes or keeps a writer's words beyond the job.

Questions and chapters are unpublished work. The contract says the worker logs
job metadata only and erases inputs; this plants a recognisable phrase in every
place a request can carry text and looks for it everywhere it must not appear.
"""

import copy
import logging

from .conftest import AUTH, RESEARCH_JOB, REVIEW_JOB, submit

SECRET = "the seal was forged by Magister Corwin"


def test_nothing_a_writer_sent_reaches_the_logs(client, runner, pipelines, store,
                                                caplog):
    caplog.set_level(logging.DEBUG)
    research = copy.deepcopy(RESEARCH_JOB)
    research["request"]["question"] = f"Was {SECRET}?"
    review = copy.deepcopy(REVIEW_JOB)
    review["request"]["chapter"]["blocks"].append({"id": "b2", "text": SECRET})
    failing = copy.deepcopy(research)
    failing["client"]["ref"] = "another"

    ids = [submit(client, body).get_json()["job"]["id"]
           for body in (research, review)]
    runner.run_next()
    runner.run_next()

    def blow_up(request, ctx):
        raise ValueError(f"could not parse {request['question']}")

    pipelines.behaviour = blow_up
    ids.append(submit(client, failing).get_json()["job"]["id"])
    runner.run_next()

    assert SECRET not in caplog.text
    assert caplog.text, "the runner does log -- just not this"
    for job_id in ids:
        job = client.get(f"/v1/jobs/{job_id}", headers=AUTH).get_json()["job"]
        assert SECRET not in str(job.get("error"))
        assert store.raw_request(job_id) is None, "inputs are erased when a job ends"
