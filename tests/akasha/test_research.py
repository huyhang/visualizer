"""Akasha's research seam: off by default, honest about the box when it is on."""

import json
from pathlib import Path

import pytest
from conftest import ADMIN_PASS, ADMIN_USER, login

from visualizer.akasha.app import create_app
from visualizer.akasha.errors import (
    ResearchBusy,
    ResearchJobNotFound,
    ResearchUnavailable,
)
from visualizer.akasha.research import RemoteResearcher, UnavailableResearcher
from visualizer.gpubox import STATES
from visualizer.gpubox.fake import FakeWorker

OPENAPI = json.loads(
    (Path(__file__).resolve().parents[2] / "docs" / "akasha" / "openapi.json")
    .read_text()
)
QUESTION = {"question": "Song-dynasty tea culture", "languages": ["en", "zh"]}


@pytest.fixture
def research_client(store, auth_store):
    """A signed-in client for an app whose researcher the test chooses."""

    def build(researcher):
        app = create_app(store, auth_store, secret_key="test-secret",
                         researcher=researcher)
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                          RATELIMIT_ENABLED=False)
        client = app.test_client()
        assert login(client, ADMIN_USER, ADMIN_PASS).status_code == 200
        return client

    return build


# -- the route ---------------------------------------------------------------


def test_research_is_off_unless_a_box_is_configured(client):
    body = client.get("/research/availability").get_json()
    assert body == {"state": "off", "can_submit": False, "private": True,
                    "message": "No GPU box is configured for this stack.",
                    "model": None, "verifier": None}


def test_availability_needs_a_session(anon_client):
    # A JSON caller gets the documented 401; a browser is sent to the login page,
    # as on every route outside /databases.
    url = "/research/availability"
    assert anon_client.get(url, headers={"Accept": "application/json"}
                           ).status_code == 401
    assert anon_client.get(url).status_code == 302


@pytest.mark.parametrize("mode", ["ready", "cold", "busy", "degraded",
                                  "queue_full", "unreachable", "misconfigured"])
def test_availability_reports_the_box(research_client, mode):
    client = research_client(RemoteResearcher(FakeWorker(mode=mode)))
    body = client.get("/research/availability").get_json()
    assert body["state"] == mode
    assert body["private"] is True


def test_the_documented_states_are_the_ones_the_stack_produces():
    schema = OPENAPI["components"]["schemas"]["ResearchAvailability"]
    assert tuple(schema["properties"]["state"]["enum"]) == STATES


# -- the seam ----------------------------------------------------------------


@pytest.mark.parametrize("call", [
    lambda r: r.submit(QUESTION, "akasha-job-1"),
    lambda r: r.status("j_1"),
    lambda r: r.cancel("j_1"),
])
def test_with_no_box_every_job_call_says_research_is_off(call):
    with pytest.raises(ResearchUnavailable, match="no GPU box"):
        call(UnavailableResearcher())


def test_a_job_round_trip_through_the_fake_box():
    researcher = RemoteResearcher(FakeWorker())
    job = researcher.submit(QUESTION, "akasha-job-1")
    assert researcher.status(job["id"])["state"] == "done"
    assert researcher.submit(QUESTION, "akasha-job-1")["id"] == job["id"], \
        "Akasha's job id is the idempotency key"


def test_jobs_are_submitted_as_akasha():
    seen = {}

    class Recorder:
        def submit(self, kind, request, *, service, ref):
            seen.update(kind=kind, service=service, ref=ref)
            return {"id": "j_1", "state": "queued"}

    RemoteResearcher(Recorder()).submit(QUESTION, "akasha-job-7")
    assert seen == {"kind": "research", "service": "akasha", "ref": "akasha-job-7"}


@pytest.mark.parametrize("mode,error,status", [
    ("queue_full", ResearchBusy, 429),
    ("unreachable", ResearchUnavailable, 503),
    ("misconfigured", ResearchUnavailable, 503),
])
def test_worker_failures_become_akasha_errors(mode, error, status):
    with pytest.raises(error) as raised:
        RemoteResearcher(FakeWorker(mode=mode)).submit(QUESTION, "akasha-job-1")
    assert raised.value.status_code == status
    if error is ResearchBusy:
        assert raised.value.retry_after == 30


def test_an_expired_job_is_not_found():
    with pytest.raises(ResearchJobNotFound) as raised:
        RemoteResearcher(FakeWorker()).status("fake_999999")
    assert raised.value.status_code == 404
