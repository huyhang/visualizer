"""LLM review of a chapter, end to end: references, the box, the issues.

Through the real app and routes, against the fake GPU box and in-memory Mongo.
Live responses are checked against docs/logos/openapi.json.
"""

import json

import pytest
from jsonschema import Draft7Validator
from jsonschema.validators import RefResolver

from visualizer.gpubox.fake import FakeWorker
from visualizer.logos.app import create_app
from visualizer.logos.errors import LlmReviewNotFound
from visualizer.logos.gateways import FakeArticleGateway
from visualizer.logos.llm_review import (
    MAX_REFERENCES,
    REFERENCE_CHARS,
    RemoteReviewer,
    assemble_references,
    discussion_reference,
    reference_text,
)
from visualizer.logos.llm_review_jobs import KEEP_PER_SECTION, LlmReviewStore
from visualizer.logos.llm_review_service import MAX_WRITER_MESSAGES, _same_issue

from .conftest import BOOK, SECTION, VOLUME, WORLD, login, section_payload
from .test_contract import OPENAPI_PATH, _as_json_schema

SPEC = _as_json_schema(json.loads(OPENAPI_PATH.read_text()))
SECTION_URL = f"/books/{BOOK}/volumes/{VOLUME}/sections/{SECTION}"
REVIEWS = SECTION_URL + "/reviews"


def conforms(body, schema):
    Draft7Validator({"$ref": f"#/components/schemas/{schema}"},
                    resolver=RefResolver.from_schema(SPEC)).validate(body)
    return body


def ref_node(collection, article, text):
    return {"type": "mention", "text": text,
            "ref": {"database": WORLD, "collection": collection, "id": article}}


CHAPTER = {"version": 1, "type": "doc", "content": [
    {"type": "paragraph", "id": "p1", "content": [
        ref_node("characters", "lyra", "Lyra"),
        {"type": "text", "text": " looked up with her brown eyes at the gate."}]},
    {"type": "paragraph", "id": "p2", "content": [
        {"type": "text", "text": "She poured tea from a teapot, as "},
        ref_node("research", "song-tea", "the custom"), {"type": "text", "text": " was."},
        ref_node("research", "rumours", " Rumour had it"),
        ref_node("research-inbox", "a-draft", " so the drafts said"),
        ref_node("characters", "ghost", " and a ghost agreed.")]},
    {"type": "paragraph", "id": "p3", "content": []},
]}


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture
def articles():
    gateway = FakeArticleGateway()
    gateway.add(WORLD, "characters", "lyra", {
        "title": "Lyra", "eyes": "grey", "body": "Lyra keeps the broken gate."})
    gateway.add(WORLD, "deviations", "qi-lanterns", {
        "title": "Qi lanterns", "body": "Lanterns float by qi. This is deliberate."})
    gateway.add(WORLD, "watchlist", "crops", {
        "title": "Anachronism watchlist", "body": "No chili peppers before the Ming."})
    gateway.add(WORLD, "research", "song-tea", {
        "title": "Song tea", "status": "verified",
        "body": "Tea was powdered and whisked in bowls.",
        "dropped_facts": ["unsupported: Tea bowls were always white."]})
    gateway.add(WORLD, "research", "rumours", {"title": "Rumours",
                                               "status": "unverified"})
    gateway.add(WORLD, "research-inbox", "a-draft", {"title": "A draft"})
    gateway.add(WORLD, "places", "highkeep", {"title": "Highkeep", "body": "A fort."})
    return gateway


@pytest.fixture
def reviews(mongo_client):
    return LlmReviewStore(mongo_client)


@pytest.fixture
def make(logos_store, chronos_gateway, articles, auth_store, reviews):
    chronos_gateway.add_book(BOOK, "The Ember Pact", events=("opening", "climax"),
                             world=WORLD)

    def build(worker, user="mara", with_reviews=True):
        app = create_app(
            logos_store, chronos_gateway, articles, auth_store,
            secret_key="test-secret",
            reviewer=RemoteReviewer(worker) if worker is not None else None,
            llm_reviews=reviews if with_reviews else None)
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                          RATELIMIT_ENABLED=False)
        client = app.test_client()
        assert login(client, user).status_code == 200
        return client

    return build


@pytest.fixture
def fake():
    return FakeWorker()


@pytest.fixture
def client(make, fake):
    client = make(fake)
    assert client.post(f"/books/{BOOK}/volumes/{VOLUME}",
                       json={"title": "The Ember Pact"}).status_code == 201
    assert client.post(SECTION_URL, json=section_payload(doc=CHAPTER)
                       ).status_code == 201
    return client


def reviewed(client, **body):
    review = conforms(client.post(REVIEWS, json=body).get_json(), "LlmReview")
    return conforms(client.get(f"{REVIEWS}/{review['id']}").get_json(), "LlmReview")


# -- references ----------------------------------------------------------------------


def test_the_preview_shows_what_would_be_sent_and_what_would_not(client):
    body = conforms(client.get(REVIEWS + "/references").get_json(),
                    "LlmReviewReferences")
    assert [(r["ref"], r["kind"]) for r in body["references"]] == [
        ("ember/deviations/qi-lanterns", "deviation"),
        ("ember/watchlist/crops", "watchlist"),
        ("ember/characters/lyra", "canon"),
        ("ember/research/song-tea", "research")]
    assert {(s["ref"], s["reason"]) for s in body["skipped"]} == {
        ("ember/research/rumours", "unverified"),
        ("ember/research-inbox/a-draft", "unreviewed_research"),
        ("ember/characters/ghost", "unavailable")}


def test_more_articles_can_be_included(client):
    body = client.get(REVIEWS + "/references?include=ember/places/highkeep").get_json()
    assert body["references"][-1] == {"ref": "ember/places/highkeep", "kind": "canon",
                                      "title": "Highkeep", "chars": 7}
    assert client.get(REVIEWS + "/references?include=not-a-ref").status_code == 400


def test_a_reference_is_its_facts_then_its_body_without_bookkeeping():
    text = reference_text({"title": "Song tea", "status": "verified", "era": "Song",
                           "aliases": ["diancha", "whisked tea"],
                           "dropped_facts": ["Tea bowls were always white."],
                           "body": "Tea was whisked." + "x" * 5000})
    assert text.startswith("Era: Song\nAliases: diancha, whisked tea\nTea was whisked.")
    assert "white" not in text and "verified" not in text
    assert len(text) == REFERENCE_CHARS


def test_deviations_are_never_the_references_cut():
    gateway = FakeArticleGateway()
    for n in range(MAX_REFERENCES + 5):
        gateway.add(WORLD, "characters", f"c{n:02d}", {"title": f"C{n}"})
    gateway.add(WORLD, "deviations", "magic", {"title": "Magic", "body": "On purpose."})
    mentioned = [{"database": WORLD, "collection": "characters", "id": f"c{n:02d}"}
                 for n in range(MAX_REFERENCES + 5)]
    sent, skipped = assemble_references(gateway, [], WORLD, mentioned, [])
    assert len(sent) == MAX_REFERENCES and sent[0]["kind"] == "deviation"
    assert [s["reason"] for s in skipped] == ["over_limit"] * 6


# -- asking and following ---------------------------------------------------------------


def test_a_review_comes_back_with_anchored_issues(client, fake):
    response = client.post(REVIEWS, json={"dialect": "en-GB"})
    assert response.status_code == 202
    queued = conforms(response.get_json(), "LlmReview")
    assert queued["issues"] is None and queued["state"] == "running"

    done = conforms(client.get(f"{REVIEWS}/{queued['id']}").get_json(), "LlmReview")
    assert done["state"] == "done" and done["verification"]["status"] == "checked"
    assert done["outdated"] is False and done["dialect"] == "en-GB"
    checks = {issue["check"] for issue in done["issues"]}
    assert checks == {"continuity", "anachronism", "prose"}
    texts = {"p1": "Lyra looked up with her brown eyes at the gate."}
    for issue in done["issues"]:
        assert issue["status"] == "open" and issue["stale"] is False
        assert issue["excerpt"] == issue["quote"] and issue["category"] == issue["check"]
        if issue["block"] in texts:
            assert issue["quote"] in texts[issue["block"]]


def test_the_box_gets_text_blocks_and_reference_texts(client, fake):
    client.post(REVIEWS, json={"checks": ["continuity"]})
    (job,) = fake._jobs.values()
    sent = job["request"]
    assert sent["chapter"] == {"title": "The Broken Gate", "blocks": [
        {"id": "p1", "text": "Lyra looked up with her brown eyes at the gate."},
        {"id": "p2", "text": "She poured tea from a teapot, as the custom was. "
                             "Rumour had it so the drafts said and a ghost agreed."}]}
    assert sent["checks"] == ["continuity"] and sent["verify"] == "auto"
    lyra = next(r for r in sent["references"] if r["ref"] == "ember/characters/lyra")
    assert lyra["text"] == "Eyes: grey\nLyra keeps the broken gate."


def test_logos_keeps_no_chapter_text_and_no_reference_text(client, mongo_client):
    reviewed(client)
    (record,) = mongo_client["_logos"]["llm_reviews"].find()
    stored = json.dumps(record, default=str)
    # Issues quote a few words of a block; the rest of the chapter is not kept.
    assert "Rumour had it" not in stored and "blocks" not in record
    assert "Lyra keeps the broken gate" not in stored
    assert all(set(r) == {"ref", "kind", "title"} for r in record["references"])


def test_reviews_are_listed_newest_first(client):
    for _ in range(2):
        reviewed(client)
    body = conforms(client.get(REVIEWS).get_json(), "LlmReviewList")
    assert len(body["reviews"]) == 2
    assert body["reviews"][0]["issue_count"] == body["reviews"][0]["open"] > 0


def test_only_the_newest_finished_reviews_are_kept(client, reviews):
    for _ in range(KEEP_PER_SECTION + 2):
        reviewed(client)
    assert len(reviews.recent(BOOK, VOLUME, SECTION)) == KEEP_PER_SECTION


def test_a_named_draft_can_be_reviewed(client, fake):
    alternate = client.post(SECTION_URL + "/drafts", json={"name": "Alternate"})
    draft = alternate.get_json()["id"]
    review = reviewed(client, draft=draft)
    assert review["draft"] == draft


def test_an_empty_draft_is_not_sent(client):
    current = client.get(SECTION_URL).get_json()
    client.put(SECTION_URL, json=section_payload(doc={"version": 1, "type": "doc",
                                                      "content": []}),
               headers={"If-Match": f'"{current["rev"]}"'})
    response = client.post(REVIEWS)
    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_REVIEW_REQUEST"


@pytest.mark.parametrize("body", [{"checks": []}, {"checks": ["spelling"]},
                                  {"dialect": "en-AU"}, {"verify": "maybe"},
                                  {"include": ["a/b"]}, {"colour": "red"}])
def test_a_bad_request_never_reaches_the_box(client, fake, body):
    assert client.post(REVIEWS, json=body).status_code == 400
    assert fake._jobs == {}


def test_too_many_reviews_at_once(make, client):
    slow = make(FakeWorker(stage_seconds=10, clock=Clock()))
    for _ in range(3):
        assert slow.post(REVIEWS).status_code == 202
    response = slow.post(REVIEWS)
    assert response.status_code == 429 and response.headers["Retry-After"] == "60"
    assert response.get_json()["code"] == "LLM_REVIEW_BUSY"


def test_cancelling_a_review(make, client):
    slow = make(FakeWorker(stage_seconds=10, clock=Clock()))
    review = slow.post(REVIEWS).get_json()
    cancelled = slow.delete(f"{REVIEWS}/{review['id']}")
    assert conforms(cancelled.get_json(), "LlmReview")["state"] == "cancelled"


def test_a_review_the_box_failed(client, fake):
    fake.fail_next("timeout")
    review = reviewed(client)
    assert review["state"] == "failed" and review["error"]["code"] == "timeout"
    assert review["issues"] is None


def test_a_review_the_box_forgot(make, client):
    class Forgetful(FakeWorker):
        def status(self, job_id):
            raise LlmReviewNotFound("gone")

    forgetful = make(Forgetful())
    review = forgetful.post(REVIEWS).get_json()
    assert forgetful.get(f"{REVIEWS}/{review['id']}").get_json()["error"][
        "code"] == "expired"


def test_an_asleep_box_leaves_the_review_as_it_was(make, client):
    clock = Clock()
    worker = FakeWorker(stage_seconds=10, clock=clock)
    slow = make(worker)
    review = slow.post(REVIEWS).get_json()
    worker.set_mode("unreachable")
    clock.now = 1000
    assert slow.get(f"{REVIEWS}/{review['id']}").get_json()["state"] == "queued"


# -- working through the issues ----------------------------------------------------------


def test_marking_issues(client):
    review = reviewed(client)
    issue = review["issues"][0]["id"]
    url = f"{REVIEWS}/{review['id']}/issues/{issue}"
    marked = conforms(client.put(url, json={"status": "dismissed"}).get_json(),
                      "LlmReviewIssue")
    assert marked["status"] == "dismissed"
    again = client.get(f"{REVIEWS}/{review['id']}").get_json()
    assert again["issues"][0]["status"] == "dismissed"
    assert client.put(url, json={"status": "ignored"}).status_code == 400
    assert client.put(f"{REVIEWS}/{review['id']}/issues/i999",
                      json={"status": "resolved"}).status_code == 404


def test_a_dismissed_issue_starts_dismissed_in_the_next_review(client):
    first = reviewed(client)
    dismissed, resolved = first["issues"][0], first["issues"][1]
    issues = f"{REVIEWS}/{first['id']}/issues"
    client.put(f"{issues}/{dismissed['id']}", json={"status": "dismissed"})
    client.put(f"{issues}/{resolved['id']}", json={"status": "resolved"})

    second = reviewed(client)
    again = {issue["id"]: issue for issue in second["issues"]}
    assert again[dismissed["id"]]["status"] == "dismissed"
    assert again[dismissed["id"]]["dismissed_before"] == first["id"]
    # Back again, so not resolved after all.
    assert again[resolved["id"]]["status"] == "open"
    assert again[resolved["id"]]["dismissed_before"] is None
    summary = conforms(client.get(REVIEWS).get_json(), "LlmReviewList")["reviews"][0]
    assert summary["open"] == summary["issue_count"] - 1

    reopened = client.put(f"{REVIEWS}/{second['id']}/issues/{dismissed['id']}",
                          json={"status": "open"})
    reopened = conforms(reopened.get_json(), "LlmReviewIssue")
    assert reopened["status"] == "open" and reopened["dismissed_before"] is None


def test_the_same_issue_is_known_by_its_check_block_and_overlapping_quote():
    old = {"check": "prose", "block": "p1", "quote": "her brown eyes"}
    assert _same_issue({**old, "quote": "with her brown eyes at"}, old)
    assert _same_issue({**old, "quote": "brown eyes"}, old)
    assert not _same_issue({**old, "quote": "at the gate"}, old)
    assert not _same_issue({**old, "block": "p2"}, old)
    assert not _same_issue({**old, "check": "continuity"}, old)


def test_issues_go_stale_as_the_draft_changes(client):
    review = reviewed(client)
    current = client.get(SECTION_URL).get_json()
    edited = json.loads(json.dumps(CHAPTER))
    edited["content"][0]["content"][1]["text"] = " looked up at the gate."
    assert client.put(SECTION_URL, json=section_payload(doc=edited),
                      headers={"If-Match": f'"{current["rev"]}"'}).status_code == 200
    after = client.get(f"{REVIEWS}/{review['id']}").get_json()
    assert after["outdated"] is True
    by_block = {issue["block"]: issue["stale"] for issue in after["issues"]}
    assert by_block.get("p1") is True
    assert by_block.get("p2", False) is False


# -- discussing an issue -----------------------------------------------------------------


def issue_url(review, check="continuity"):
    issue = next(i for i in review["issues"] if i["check"] == check)
    return f"{REVIEWS}/{review['id']}/issues/{issue['id']}"


def discussions(fake):
    return [job["request"] for job in fake._jobs.values() if job["kind"] == "discussion"]


def say(client, url, text):
    """Send a message and poll until the editor's reply is in."""
    sent = client.post(url + "/messages", json={"text": text})
    assert sent.status_code == 202, sent.get_json()
    conforms(sent.get_json(), "LlmReviewIssue")
    return conforms(client.get(url).get_json(), "LlmReviewIssue")


def test_answering_an_issue_gets_the_editors_reply(client):
    url = issue_url(reviewed(client))
    sent = client.post(url + "/messages", json={"text": "  Why does that matter?  "})
    assert sent.status_code == 202
    waiting = conforms(sent.get_json(), "LlmReviewIssue")
    assert [(t["role"], t["text"]) for t in waiting["discussion"]] == [
        ("writer", "Why does that matter?")]
    assert waiting["reply"]["state"] == "running"

    replied = conforms(client.get(url).get_json(), "LlmReviewIssue")
    assert replied["reply"] is None and len(replied["discussion"]) == 2
    editor = replied["discussion"][-1]
    assert (editor["role"], editor["stance"], editor["model"]) == (
        "editor", "maintains", "fake-model")
    assert editor["text"].startswith("[Fake]") and editor["at"]
    assert client.get(f"{url.rsplit('/issues', 1)[0]}").get_json()["issues"][0][
        "discussion"] == replied["discussion"]


@pytest.mark.parametrize("said,stance,suggests", [
    ("That's deliberate.", "withdraws", False),
    ("What would you do instead?", "revises", True),
])
def test_a_reply_never_changes_the_writers_status(client, said, stance, suggests):
    replied = say(client, issue_url(reviewed(client)), said)
    editor = replied["discussion"][-1]
    assert editor["stance"] == stance and (editor["suggestion"] is not None) == suggests
    assert (editor["replacement"] is not None) == suggests
    assert replied["status"] == "open"


@pytest.mark.parametrize("check,offers", [("continuity", False), ("prose", True)])
def test_an_issue_carries_the_exact_replacement_when_there_is_one(client, check,
                                                                 offers):
    issue = next(i for i in reviewed(client)["issues"] if i["check"] == check)
    assert issue["replacement"] == (f"[Fake fix] {issue['quote']}" if offers
                                    else None)


def test_a_revised_replacement_goes_back_to_the_box_next_turn(client, fake):
    review = reviewed(client)
    issue = next(i for i in review["issues"] if i["check"] == "prose")
    url = issue_url(review, "prose")
    revised = say(client, url, "What would you do instead?")["discussion"][-1]
    say(client, url, "Why that?")
    sent = discussions(fake)[-1]
    assert sent["issue"]["replacement"] == issue["replacement"]
    assert f"(Suggested replacement: {revised['replacement']})" in \
        sent["messages"][1]["text"]


@pytest.mark.parametrize("given,kept", [
    ("  ", None),
    (42, None),
    ("QUOTE", None),                              # the quote itself is no fix
    ("Lyra looked up, grey-eyed", "Lyra looked up, grey-eyed"),
    ("x" * 1000, "x" * 1000),
    ("x" * 1001, None),                           # never kept cut short
])
def test_a_replacement_from_the_box_is_checked(make, given, kept):
    class Rewording(FakeWorker):
        def status(self, job_id):
            job = super().status(job_id)
            if job["kind"] == "review" and job["result"]:
                for issue in job["result"]["issues"]:
                    issue["replacement"] = issue["quote"] if given == "QUOTE" \
                        else given
            return job

    rewording = make(Rewording())
    assert rewording.post(f"/books/{BOOK}/volumes/{VOLUME}",
                          json={"title": "The Ember Pact"}).status_code == 201
    assert rewording.post(SECTION_URL, json=section_payload(doc=CHAPTER)
                          ).status_code == 201
    review = reviewed(rewording, checks=["prose"])
    assert [i["replacement"] for i in review["issues"]] == [kept]


def test_the_box_gets_the_issue_its_passage_its_article_and_the_whole_talk(client,
                                                                           fake):
    url = issue_url(reviewed(client, dialect="en-GB"))
    first = say(client, url, "Her eyes were brown as a child.")
    say(client, url, "Does that change anything?")
    sent = discussions(fake)[-1]
    assert sent["passage"] == "Lyra looked up with her brown eyes at the gate."
    assert sent["reference"] == {"ref": "ember/characters/lyra", "kind": "canon",
                                 "title": "Lyra",
                                 "text": "Eyes: grey\nLyra keeps the broken gate."}
    assert [m["role"] for m in sent["messages"]] == ["writer", "editor", "writer"]
    assert sent["messages"][1]["text"] == first["discussion"][1]["text"]
    assert sent["messages"][2]["text"] == "Does that change anything?"
    assert sent["issue"]["check"] == "continuity" and sent["dialect"] == "en-GB"


def test_a_prose_issue_goes_without_an_article(client, fake):
    say(client, issue_url(reviewed(client), "prose"), "Is it the rhythm?")
    assert discussions(fake)[-1]["reference"] is None


def test_the_passage_is_the_block_as_it_reads_now(client, fake):
    url = issue_url(reviewed(client))
    current = client.get(SECTION_URL).get_json()
    edited = json.loads(json.dumps(CHAPTER))
    edited["content"][0]["content"][1]["text"] = " looked up at the gate."
    client.put(SECTION_URL, json=section_payload(doc=edited),
               headers={"If-Match": f'"{current["rev"]}"'})
    say(client, url, "I changed it; does it read better?")
    assert discussions(fake)[-1]["passage"] == "Lyra looked up at the gate."


def test_the_cited_article_is_sent_only_while_the_writer_may_rely_on_it(articles):
    lyra = discussion_reference(articles, [], "ember/characters/lyra", "canon")
    assert lyra["text"] == "Eyes: grey\nLyra keeps the broken gate."
    assert discussion_reference(articles, [], "ember/research/song-tea",
                                "research")["kind"] == "research"
    for ref, kind in (("ember/research/rumours", "research"),      # unverified
                      ("ember/research-inbox/a-draft", None),        # never sent
                      ("ember/characters/ghost", "canon"),           # missing
                      (None, None), ("not-a-ref", None)):
        assert discussion_reference(articles, [], ref, kind) is None


def test_one_reply_at_a_time(make, client):
    worker = FakeWorker(stage_seconds=10, clock=Clock())
    slow = make(worker)
    review = slow.post(REVIEWS).get_json()
    worker.stage_seconds = 0      # the review finishes; replies are slow again below
    review = slow.get(f"{REVIEWS}/{review['id']}").get_json()
    worker.stage_seconds = 10
    url = issue_url(review)
    assert slow.post(url + "/messages", json={"text": "Why?"}).status_code == 202
    again = slow.post(url + "/messages", json={"text": "Hello?"})
    assert again.status_code == 429 and again.headers["Retry-After"] == "5"
    assert len(discussions(worker)) == 1
    assert slow.get(url).get_json()["reply"]["state"] == "queued"


def test_a_failed_reply_keeps_the_message_and_can_be_asked_again(client, fake):
    url = issue_url(reviewed(client))
    fake.fail_next("timeout")
    client.post(url + "/messages", json={"text": "Why?"})
    failed = conforms(client.get(url).get_json(), "LlmReviewIssue")
    assert failed["reply"]["state"] == "failed"
    assert failed["reply"]["error"]["code"] == "timeout"
    assert [t["role"] for t in failed["discussion"]] == ["writer"]
    replied = say(client, url, "Why, though?")
    assert [t["role"] for t in replied["discussion"]] == ["writer", "writer", "editor"]


@pytest.mark.parametrize("body", [{"text": ""}, {"text": "   "}, {"text": "x" * 2001},
                                  {"text": 3}, {"message": "Why?"},
                                  {"text": "Why?", "colour": "red"}])
def test_a_bad_message_never_reaches_the_box(client, fake, body):
    url = issue_url(reviewed(client))
    response = client.post(url + "/messages", json=body)
    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_REVIEW_REQUEST"
    assert discussions(fake) == []


def test_an_issue_takes_a_limited_number_of_messages(client):
    url = issue_url(reviewed(client))
    for n in range(MAX_WRITER_MESSAGES):
        say(client, url, f"Point {n}.")
    response = client.post(url + "/messages", json={"text": "One more."})
    assert response.status_code == 400


def test_an_issue_that_is_not_there(client):
    review = reviewed(client)
    url = f"{REVIEWS}/{review['id']}/issues/i999"
    assert client.get(url).status_code == 404
    assert client.post(url + "/messages", json={"text": "Why?"}).status_code == 404


def test_a_discussion_records_no_username(client, mongo_client):
    say(client, issue_url(reviewed(client)), "Why?")
    (record,) = mongo_client["_logos"]["llm_reviews"].find()
    turns = [t for issue in record["issues"] for t in issue.get("discussion", [])]
    assert turns and "mara" not in json.dumps(turns)


# -- who may, and when it is off ---------------------------------------------------------


def test_a_reader_of_the_book_may_not(make, client):
    review = reviewed(client)
    reader = make(FakeWorker(), user="devi")
    assert reader.get(REVIEWS + "/references").status_code == 403
    assert reader.post(REVIEWS).status_code == 403
    assert reader.get(REVIEWS).status_code == 403
    url = issue_url(review)
    assert reader.get(url).status_code == 403
    assert reader.post(url + "/messages", json={"text": "Hi"}).status_code == 403


def test_with_no_box_review_is_off(make, client):
    off = make(None, with_reviews=False)
    assert off.get("/llm-review/availability").get_json()["state"] == "off"
    response = off.post(REVIEWS)
    assert response.status_code == 503
    assert response.get_json()["code"] == "LLM_REVIEW_UNAVAILABLE"


def test_availability_reports_the_box(client):
    body = client.get("/llm-review/availability").get_json()
    assert body["state"] == "ready" and body["private"] is True


def test_reviews_go_with_their_book_and_their_requester(client, logos_store, reviews):
    reviewed(client)
    logos_store.purge_user("mara")
    assert reviews.recent(BOOK, VOLUME, SECTION) == []
    reviewed(client)
    logos_store.purge_book(BOOK)
    assert reviews.recent(BOOK, VOLUME, SECTION) == []


def test_a_malformed_result_is_refused(make, client):
    class Garbled(FakeWorker):
        def status(self, job_id):
            job = super().status(job_id)
            job["result"]["issues"][0]["check"] = "spelling"
            return job

    garbled = make(Garbled())
    review = garbled.post(REVIEWS).get_json()
    failed = garbled.get(f"{REVIEWS}/{review['id']}").get_json()
    assert failed["state"] == "failed" and failed["error"]["code"] == "invalid_result"
    assert failed["issues"] is None
