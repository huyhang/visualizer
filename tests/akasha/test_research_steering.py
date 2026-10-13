"""Steering research from Akasha: approving the search plan, refining a draft.

Through the real routes against the fake GPU box, as in test_research_inbox.
"""

# The research app's fixtures are imported so they outrank conftest's plain
# ``client``; tests naming them as parameters is how pytest uses them.
# ruff: noqa: F811

import pytest
from test_research_inbox import (  # noqa: F401 -- fixtures
    QUESTION,
    WORLD,
    Clock,
    ask,
    asked_and_imported,
    build,
    client,
    conforms,
    fake,
    follow,
    jobs,
    user,
    world,
)

from visualizer.akasha.research import RemoteResearcher
from visualizer.auth import READ
from visualizer.gpubox.fake import FakeWorker

EDITED = [{"q": "song dynasty tea houses", "language": "en"}]
FEEDBACK = "Focus on tea houses and ordinary drinkers, not the court."


def slug_of(job):
    return job["draft"].split("/", 1)[1]


def approve(client, job_id, queries=EDITED):
    return client.post(f"/databases/{WORLD}/research/jobs/{job_id}/plan",
                       json={"queries": queries})


def refine(client, slug, **body):
    return client.post(f"/databases/{WORLD}/research/inbox/{slug}/refine",
                       json={"feedback": FEEDBACK, **body})


def draft_detail(client, slug):
    return conforms(client.get(f"/databases/{WORLD}/research/inbox/{slug}").get_json(),
                    "ResearchDraft")


# -- approving the plan --------------------------------------------------------------


def test_a_job_waits_with_its_plan_until_approved(client, fake):
    job = conforms(ask(client, {**QUESTION, "approve_plan": True}).get_json(),
                   "ResearchJob")
    assert job["state"] == "awaiting_approval"
    assert job["plan"]["approved"] is False and job["plan"]["queries"]
    assert follow(client, job["id"]).get_json()["state"] == "awaiting_approval"

    approved = conforms(approve(client, job["id"]).get_json(), "ResearchJob")
    assert approved["state"] == "running"
    done = conforms(follow(client, job["id"]).get_json(), "ResearchJob")
    assert done["state"] == "done" and done["review"] == "pending"
    assert done["plan"] == {"queries": EDITED, "approved": True, "expires_at": None}


def test_only_a_waiting_job_can_be_approved(client):
    job = ask(client).get_json()
    response = approve(client, job["id"])
    assert response.status_code == 409


@pytest.mark.parametrize("queries,message", [
    ([{"q": "", "language": "en"}], "1-200"),
    ([{"q": "tea", "language": "english"}], "language code"),
    ([{"q": "tea", "language": "en", "x": 1}], "{q, language}"),
    (EDITED * 7, "at most 6"),
    ([], "at least one"),
])
def test_a_bad_approval_is_refused(client, queries, message):
    job = ask(client, {**QUESTION, "approve_plan": True}).get_json()
    response = approve(client, job["id"], queries)
    assert response.status_code == 400 and message in response.get_json()["error"]


def test_turning_a_plan_down_is_cancelling_the_job(client):
    job = ask(client, {**QUESTION, "approve_plan": True}).get_json()
    cancelled = client.delete(f"/databases/{WORLD}/research/jobs/{job['id']}")
    assert cancelled.get_json()["state"] == "cancelled"


def test_a_waiting_job_counts_against_the_limit(client):
    for _ in range(3):
        ask(client, {**QUESTION, "approve_plan": True})
    assert ask(client).status_code == 429


def test_a_plan_that_expired_on_the_box(build, world):
    clock = Clock()
    client = build(RemoteResearcher(FakeWorker(clock=clock, stage_seconds=1)))
    job = ask(client, {**QUESTION, "approve_plan": True}).get_json()
    clock.now = 10
    assert follow(client, job["id"]).get_json()["state"] == "awaiting_approval"
    clock.now = 25 * 3600
    expired = follow(client, job["id"]).get_json()
    assert expired["state"] == "failed" and expired["error"]["code"] == "plan_expired"


# -- refining --------------------------------------------------------------------------


def test_a_refinement_replaces_the_draft_as_a_new_version(client, fake, store):
    first = asked_and_imported(client)
    slug = slug_of(first)
    before = draft_detail(client, slug)
    kept, dropped = before["sources"]

    response = refine(client, slug, exclude_sources=[dropped["ref"]])
    assert response.status_code == 202
    job = conforms(response.get_json(), "ResearchJob")
    assert job["refines"] == f"research-inbox/{slug}"
    done = conforms(follow(client, job["id"]).get_json(), "ResearchJob")
    assert done["draft"] == first["draft"], "the same slug"

    after = draft_detail(client, slug)
    assert after["job"]["id"] == job["id"]
    refs = [row["ref"] for row in after["sources"]]
    assert refs[0] == kept["ref"], "a source found again keeps its document"
    assert dropped["ref"] not in refs
    assert "Refined" in after["article"]["document"]["body"]
    history = store.history(WORLD, "research-inbox", slug)
    assert [h["author"] for h in history] == ["research-bot", "research-bot"]
    dropped_slug = dropped["ref"].split("/", 1)[1]
    assert dropped_slug not in store.document_ids(WORLD, "research-inbox")

    old = follow(client, first["id"]).get_json()
    assert old["review"] == "superseded" and old["superseded_by"] == job["id"]
    drafts = client.get(f"/databases/{WORLD}/research/inbox").get_json()["drafts"]
    assert [d["draft"] for d in drafts] == [first["draft"]]


def test_what_the_box_is_told_when_refining(client, fake):
    first = asked_and_imported(client)
    before = draft_detail(client, slug_of(first))
    dropped = before["sources"][1]
    refine(client, slug_of(first), exclude_sources=[dropped["ref"]])
    sent = list(fake._jobs.values())[-1]["request"]
    assert sent["question"] == QUESTION["question"]
    assert sent["refine"]["feedback"] == FEEDBACK
    assert sent["refine"]["previous"]["facts"] == [f["text"] for f in before["facts"]]
    assert sent["refine"]["previous"]["sources"] == [
        {"url": before["sources"][0]["url"], "title": before["sources"][0]["title"]}]
    assert sent["refine"]["exclude_urls"] == [dropped["url"]]
    assert sent["max_sources"] == 5, "the sources kept, plus four"
    assert sent["include_images"] is True, "settings carry over"
    assert {"ref": "song/characters/lin", "title": "Lin Qingyu"} in sent["known_articles"]


def test_a_later_refinement_still_excludes_what_an_earlier_one_did(client, fake):
    first = asked_and_imported(client)
    slug = slug_of(first)
    dropped = draft_detail(client, slug)["sources"][1]
    follow(client, refine(client, slug, exclude_sources=[dropped["ref"]]).get_json()["id"])
    refine(client, slug, max_sources=3)
    sent = list(fake._jobs.values())[-1]["request"]
    assert sent["refine"]["exclude_urls"] == [dropped["url"]]
    assert sent["max_sources"] == 3


def test_one_refinement_at_a_time(build, world):
    clock = Clock()
    client = build(RemoteResearcher(FakeWorker(clock=clock, stage_seconds=1)))
    job = ask(client).get_json()
    clock.now = 100
    slug = slug_of(follow(client, job["id"]).get_json())
    assert refine(client, slug).status_code == 202
    assert draft_detail(client, slug)["refining"]["state"] in ("queued", "running")
    row = client.get(f"/databases/{WORLD}/research/inbox").get_json()["drafts"][0]
    assert row["refining"] is True
    again = refine(client, slug)
    assert again.status_code == 409


def test_a_draft_decided_meanwhile_gets_the_refinement_as_a_new_draft(build, world):
    clock = Clock()
    client = build(RemoteResearcher(FakeWorker(clock=clock, stage_seconds=1)))
    job = ask(client).get_json()
    clock.now = 100
    slug = slug_of(follow(client, job["id"]).get_json())
    refinement = refine(client, slug).get_json()
    client.post(f"/databases/{WORLD}/research/inbox/{slug}/accept")
    clock.now = 200
    done = follow(client, refinement["id"]).get_json()
    assert done["review"] == "pending" and done["draft"] is not None
    assert follow(client, job["id"]).get_json()["review"] == "accepted"


@pytest.mark.parametrize("body,status", [
    ({"exclude_sources": ["sources/not-this-drafts"]}, 400),
    ({"feedback": ""}, 400),
    ({"question": "Something else entirely"}, 400),
    ({"max_sources": 40}, 400),
])
def test_a_bad_refinement_is_refused(client, body, status):
    slug = slug_of(asked_and_imported(client))
    assert refine(client, slug, **body).status_code == status


def test_only_a_pending_draft_can_be_refined(client):
    slug = slug_of(asked_and_imported(client))
    client.post(f"/databases/{WORLD}/research/inbox/{slug}/reject")
    assert refine(client, slug).status_code == 409
    assert refine(client, "no-such-draft").status_code == 404


def test_a_reader_may_neither_refine_nor_approve(build, fake, world, auth_store):
    admin = build(RemoteResearcher(fake))
    slug = slug_of(asked_and_imported(admin))
    waiting = ask(admin, {**QUESTION, "approve_plan": True}).get_json()
    reader = build(RemoteResearcher(fake), *user(auth_store, "reader", [READ]))
    assert refine(reader, slug).status_code == 403
    assert approve(reader, waiting["id"]).status_code == 403
