"""Research from Akasha's side, end to end: ask, follow, review, import images.

Through the real app and routes, against the fake GPU box (jobs finish at once
unless a clock says otherwise) and an in-memory Mongo.
"""

import json
from pathlib import Path

import pytest
from conftest import ADMIN_PASS, ADMIN_USER, login
from jsonschema import Draft7Validator
from jsonschema.validators import RefResolver
from test_contract import _as_json_schema
from werkzeug.security import generate_password_hash

from visualizer.akasha.app import create_app
from visualizer.akasha.errors import ResearchJobNotFound
from visualizer.akasha.research import RemoteResearcher
from visualizer.akasha.research_jobs import ResearchJobStore
from visualizer.auth import READ, WRITE
from visualizer.gpubox.fake import FakeWorker

SPEC = _as_json_schema(json.loads(
    (Path(__file__).resolve().parents[2] / "docs" / "akasha" / "openapi.json").read_text()))
WORLD = "song"
QUESTION = {"question": "How was tea served in the Song dynasty?",
            "include_images": True}


def conforms(body, schema):
    Draft7Validator({"$ref": f"#/components/schemas/{schema}"},
                    resolver=RefResolver.from_schema(SPEC)).validate(body)
    return body


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture
def fake():
    return FakeWorker()


@pytest.fixture
def jobs(mongo_client):
    return ResearchJobStore(mongo_client)


@pytest.fixture
def build(store, auth_store, media_service, jobs):
    """An app wired to a researcher of the test's choosing, and a signed-in client."""

    def make(researcher, user=ADMIN_USER, password=ADMIN_PASS):
        app = create_app(store, auth_store, secret_key="test-secret",
                         media_service=media_service, researcher=researcher,
                         research_jobs=jobs)
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)
        client = app.test_client()
        assert login(client, user, password).status_code == 200
        return client

    return make


@pytest.fixture
def world(store):
    store.create_collection(WORLD, "characters")
    store.create(WORLD, "characters", "lin", {"title": "Lin Qingyu",
                                              "body": "A secret of the plot."})
    return WORLD


@pytest.fixture
def client(build, fake, world):
    return build(RemoteResearcher(fake))


def ask(client, body=None):
    return client.post(f"/databases/{WORLD}/research/jobs", json=body or QUESTION)


def follow(client, job_id):
    return client.get(f"/databases/{WORLD}/research/jobs/{job_id}")


def asked_and_imported(client):
    job = conforms(ask(client).get_json(), "ResearchJob")
    done = conforms(follow(client, job["id"]).get_json(), "ResearchJob")
    assert done["state"] == "done", done
    return done


# -- asking and following -------------------------------------------------------


def test_a_question_becomes_a_draft_in_the_inbox(client, store):
    response = ask(client)
    assert response.status_code == 202
    job = response.get_json()
    assert (job["state"], job["review"], job["draft"]) == ("running", None, None)
    done = conforms(follow(client, job["id"]).get_json(), "ResearchJob")
    assert done["review"] == "pending" and done["draft"].startswith("research-inbox/")
    assert done["verification"] == "checked"
    slug = done["draft"].split("/", 1)[1]
    draft = store.get(WORLD, "research-inbox", slug)["document"]
    assert draft["status"] == "unverified" and draft["question"] == QUESTION["question"]
    assert store.history(WORLD, "research-inbox", slug)[-1]["author"] == "research-bot"


def test_following_twice_imports_once(client):
    job = ask(client).get_json()
    first = follow(client, job["id"]).get_json()
    second = follow(client, job["id"]).get_json()
    assert first["draft"] == second["draft"]
    drafts = client.get(f"/databases/{WORLD}/research/inbox").get_json()["drafts"]
    assert len(drafts) == 1


def test_only_one_caller_can_claim_an_import(jobs):
    job = jobs.create(world=WORLD, requester="a", question="q", request={})
    jobs.update(job["_id"], state="running")
    assert [jobs.claim_import(job["_id"]) for _ in range(2)] == [True, False]


def test_the_box_is_sent_titles_of_the_world_never_bodies(client, fake):
    ask(client)
    (sent,) = [job["request"] for job in fake._jobs.values()]
    assert {"ref": "song/characters/lin", "title": "Lin Qingyu"} in sent["known_articles"]
    assert "secret" not in json.dumps(sent)


def test_jobs_are_listed_newest_first(client):
    for _ in range(2):
        ask(client)
    body = conforms(client.get(f"/databases/{WORLD}/research/jobs").get_json(),
                    "ResearchJobList")
    times = [job["created_at"] for job in body["jobs"]]
    assert len(times) == 2 and times == sorted(times, reverse=True)


@pytest.mark.parametrize("body,message", [
    ({"question": "hi"}, "3-500"),
    ({"question": "Song tea", "colour": "red"}, "Unknown fields"),
    ({"question": "Song tea", "languages": ["english"]}, "language codes"),
    ({"question": "Song tea", "max_sources": 99}, "1 to 15"),
])
def test_a_bad_request_is_refused_before_the_box_hears_of_it(client, fake, body,
                                                             message):
    response = ask(client, body)
    assert response.status_code == 400 and message in response.get_json()["error"]
    assert fake._jobs == {}


def test_too_many_jobs_at_once(build, world):
    fake = FakeWorker(stage_seconds=10, clock=Clock())
    client = build(RemoteResearcher(fake))
    for _ in range(3):
        assert ask(client).status_code == 202
    response = ask(client)
    assert response.status_code == 429 and response.headers["Retry-After"] == "60"


def test_cancelling_a_running_job(build, world):
    clock = Clock()
    client = build(RemoteResearcher(FakeWorker(stage_seconds=10, clock=clock)))
    job = ask(client).get_json()
    clock.now = 15
    assert follow(client, job["id"]).get_json()["state"] == "running"
    cancelled = client.delete(f"/databases/{WORLD}/research/jobs/{job['id']}")
    assert conforms(cancelled.get_json(), "ResearchJob")["state"] == "cancelled"


def test_an_asleep_box_leaves_the_job_as_it_was(build, world):
    clock = Clock()
    fake = FakeWorker(stage_seconds=10, clock=clock)
    client = build(RemoteResearcher(fake))
    job = ask(client).get_json()
    fake.set_mode("unreachable")
    clock.now = 500
    assert follow(client, job["id"]).get_json()["state"] == "queued"


def test_a_job_the_box_failed(client, fake):
    fake.fail_next("no_sources")
    job = ask(client).get_json()
    failed = follow(client, job["id"]).get_json()
    assert failed["state"] == "failed" and failed["error"]["code"] == "no_sources"
    assert failed["draft"] is None


def test_a_result_that_expired_before_anyone_looked(build, world, fake):
    class Forgetful(RemoteResearcher):
        def status(self, job_id):
            raise ResearchJobNotFound("Unknown or expired job")

    client = build(Forgetful(FakeWorker(stage_seconds=10, clock=Clock())))
    job = ask(client).get_json()
    expired = follow(client, job["id"]).get_json()
    assert expired["state"] == "failed" and expired["error"]["code"] == "expired"


def test_a_malformed_result_is_refused_and_leaves_nothing_behind(build, world, store):
    class Garbled(RemoteResearcher):
        def status(self, job_id):
            job = super().status(job_id)
            job["result"]["sources"][1]["url"] = "javascript:alert(1)"
            return job

    client = build(Garbled(FakeWorker()))
    job = ask(client).get_json()
    failed = follow(client, job["id"]).get_json()
    assert failed["error"]["code"] == "invalid_result"
    assert "research-inbox" not in store.list_collections(WORLD) or \
        store.list_documents(WORLD, "research-inbox") == []


# -- the inbox -------------------------------------------------------------------


def test_the_inbox_and_a_drafts_detail(client):
    done = asked_and_imported(client)
    inbox = conforms(client.get(f"/databases/{WORLD}/research/inbox").get_json(),
                     "ResearchInbox")
    (row,) = inbox["drafts"]
    assert row["draft"] == done["draft"] and row["images"] == 2
    slug = done["draft"].split("/", 1)[1]
    detail = conforms(client.get(f"/databases/{WORLD}/research/inbox/{slug}").get_json(),
                      "ResearchDraft")
    assert [f["check"] for f in detail["facts"]] == ["supported", "partial"]
    assert {d["reason"] for d in detail["dropped_facts"]} == {"quote_not_found",
                                                              "unsupported"}
    assert all("fetch_token" not in image for image in detail["images"])


def test_accepting_moves_the_draft_into_research(client, store):
    done = asked_and_imported(client)
    slug = done["draft"].split("/", 1)[1]
    response = client.post(f"/databases/{WORLD}/research/inbox/{slug}/accept")
    accepted = conforms(response.get_json(), "ResearchAccepted")
    article = store.get(WORLD, "research", accepted["article"].split("/", 1)[1])
    assert article["document"]["status"] == "verified"
    assert article["document"]["verified_by"] == ADMIN_USER
    assert len(accepted["sources"]) == 2
    for ref in accepted["sources"]:
        assert store.get(WORLD, "sources", ref.split("/", 1)[1])["document"][
            "status"] == "verified"
        assert f"[[{ref}]]" in article["document"]["body"]
    assert store.list_documents(WORLD, "research-inbox") == []
    job = follow(client, done["id"]).get_json()
    assert (job["review"], job["accepted"], job["draft"]) == (
        "accepted", accepted["article"], None)
    again = client.post(f"/databases/{WORLD}/research/inbox/{slug}/accept")
    assert again.status_code == 409


def test_the_next_draft_reuses_accepted_sources(client, store):
    first = asked_and_imported(client)
    client.post(f"/databases/{WORLD}/research/inbox/"
                f"{first['draft'].split('/', 1)[1]}/accept")
    second = asked_and_imported(client)
    draft = store.get(WORLD, "research-inbox", second["draft"].split("/", 1)[1])
    assert all(ref.startswith("sources/") for ref in draft["document"]["sources"])
    assert len(store.list_documents(WORLD, "research-inbox")) == 1, "no new sources"


def test_rejecting_a_draft(client, store):
    done = asked_and_imported(client)
    slug = done["draft"].split("/", 1)[1]
    assert client.post(f"/databases/{WORLD}/research/inbox/{slug}/reject"
                       ).status_code == 204
    assert store.list_documents(WORLD, "research-inbox") == []
    assert store.history(WORLD, "research-inbox", slug), "soft: history remains"
    assert follow(client, done["id"]).get_json()["review"] == "rejected"


# -- images ------------------------------------------------------------------------


def test_previewing_and_importing_an_image(client, media_service):
    done = asked_and_imported(client)
    base = f"/databases/{WORLD}/research/inbox/{done['draft'].split('/', 1)[1]}"
    preview = client.get(f"{base}/images/0")
    assert preview.status_code == 200 and preview.content_type == "image/png"
    assert preview.headers["Cache-Control"] == "private, max-age=86400"
    imported = client.post(f"{base}/images/0/import")
    assert imported.status_code == 201
    media = conforms(imported.get_json(), "Media")
    assert media["source_url"].startswith("https://example.org/fake-research/")
    assert media["license"] == "CC0 (fake)"
    assert media["alt"].startswith("[Fake] An image about")
    detail = client.get(base).get_json()
    assert detail["images"][0]["imported"] == media["id"]


def test_an_image_that_has_vanished(client):
    done = asked_and_imported(client)
    base = f"/databases/{WORLD}/research/inbox/{done['draft'].split('/', 1)[1]}"
    for response in (client.get(f"{base}/images/1"),
                     client.post(f"{base}/images/1/import")):
        assert response.status_code == 502
    assert client.get(f"{base}/images/9").status_code == 404
    assert client.get(f"{base}/images/0?size=huge").status_code == 400


# -- who may do what -----------------------------------------------------------------


def user(auth_store, name, perms):
    auth_store.create_user(name, generate_password_hash(f"{name}-Pass-123"))
    if perms:
        auth_store.add_grant(name, WORLD, None, None, perms, granted_by=ADMIN_USER)
    return name, f"{name}-Pass-123"


def test_a_reader_may_look_but_not_ask_or_decide(build, fake, world, auth_store):
    admin = build(RemoteResearcher(fake))
    done = asked_and_imported(admin)
    slug = done["draft"].split("/", 1)[1]
    reader = build(RemoteResearcher(fake), *user(auth_store, "reader", [READ]))
    assert reader.get(f"/databases/{WORLD}/research/inbox").status_code == 200
    assert ask(reader).status_code == 403
    for action in ("accept", "reject"):
        assert reader.post(f"/databases/{WORLD}/research/inbox/{slug}/{action}"
                           ).status_code == 403


def test_a_stranger_sees_nothing(build, fake, world, auth_store):
    stranger = build(RemoteResearcher(fake), *user(auth_store, "stranger", []))
    assert stranger.get(f"/databases/{WORLD}/research/inbox").status_code == 403


def test_an_editor_may_ask_and_accept(build, fake, world, auth_store):
    editor = build(RemoteResearcher(fake), *user(auth_store, "editor", [READ, WRITE]))
    done = asked_and_imported(editor)
    slug = done["draft"].split("/", 1)[1]
    assert editor.post(f"/databases/{WORLD}/research/inbox/{slug}/accept"
                       ).status_code == 200


def test_with_research_off_nothing_is_recorded(build, world, jobs):
    client = build(None)
    response = ask(client)
    assert response.status_code == 503
    assert jobs.recent(WORLD) == []


def test_reserved_databases_stay_out_of_reach(client):
    assert client.get("/databases/_research/research/inbox").status_code == 400
