"""The studio's API: digging deeper, saving notes from drafts, closing drafts.

Through the real routes against the fake GPU box, as in test_research_inbox.
"""

# The research app's fixtures are imported so they outrank conftest's plain
# ``client``; tests naming them as parameters is how pytest uses them.
# ruff: noqa: F811

import pytest
from test_research_inbox import (  # noqa: F401 -- fixtures
    WORLD,
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
from visualizer.auth import READ, WRITE

BASE = f"/databases/{WORLD}/research"


def slug_of(job):
    return job["draft"].split("/", 1)[1]


def detail(client, slug):
    return conforms(client.get(f"{BASE}/inbox/{slug}").get_json(), "ResearchDraft")


def save(client, **body):
    return client.post(f"{BASE}/notes", json=body)


def first_source(client, done):
    """The draft's first inbox source ref, and the note text citing it."""
    ref = detail(client, slug_of(done))["sources"][0]["ref"]
    return ref, f"Tea was whisked into a froth. [[{ref}]]"


# -- digging deeper ------------------------------------------------------------


def test_digging_deeper_places_the_new_topic_under_its_parent(client, fake):
    parent = asked_and_imported(client)
    response = ask(client, {"question": "Jian ware tea bowls", "parent": parent["id"]})
    assert response.status_code == 202
    child = conforms(response.get_json(), "ResearchJob")
    assert child["parent"] == parent["id"]
    sent = [job["request"] for job in fake._jobs.values()][-1]
    assert "parent" not in sent, "Akasha's alone"
    listed = client.get(f"{BASE}/jobs").get_json()["jobs"]
    assert {job["id"]: job["parent"] for job in listed} == {
        child["id"]: parent["id"], parent["id"]: None}


def test_a_refinement_keeps_its_drafts_place_in_the_tree(client):
    parent = asked_and_imported(client)
    child = follow(client, ask(client, {"question": "Jian ware tea bowls",
                                        "parent": parent["id"]}).get_json()["id"]
                   ).get_json()
    refined = client.post(f"{BASE}/inbox/{slug_of(child)}/refine",
                          json={"feedback": "More on glazes."}).get_json()
    assert refined["parent"] == parent["id"]


@pytest.mark.parametrize("parent,status", [
    ("rj_ffffffffffffffff", 404),
    ("not-a-job", 400),
])
def test_digging_deeper_from_nothing_is_refused(client, fake, parent, status):
    before = len(fake._jobs)
    response = ask(client, {"question": "Jian ware tea bowls", "parent": parent})
    assert response.status_code == status
    assert len(fake._jobs) == before, "nothing reached the box"


@pytest.mark.parametrize("query,status,count", [
    ("", 200, 3),
    ("?limit=2", 200, 2),
    ("?limit=0", 400, None),
    ("?limit=201", 400, None),
    ("?limit=many", 400, None),
])
def test_the_job_list_can_be_asked_for_more_or_fewer(client, query, status, count):
    for _ in range(3):
        asked_and_imported(client)
    response = client.get(f"{BASE}/jobs{query}")
    assert response.status_code == status
    if count is not None:
        assert len(response.get_json()["jobs"]) == count


# -- saving a new note -----------------------------------------------------------


def test_a_new_note_accepts_only_the_sources_it_cites(client, store):
    done = asked_and_imported(client)
    _ref, body = first_source(client, done)
    response = save(client, title="Song tea", body=body, drafts=[done["draft"]])
    assert response.status_code == 201
    saved = conforms(response.get_json(), "ResearchNoteSaved")
    assert saved["note"] == "research/song-tea" and saved["rev"] == 1
    (moved,) = saved["sources"]
    note = store.get(WORLD, "research", "song-tea")["document"]
    assert note["body"] == f"Tea was whisked into a froth. [[{moved}]]"
    assert note["sources"] == [moved] and note["status"] == "verified"
    assert store.get(WORLD, "sources", moved.split("/", 1)[1])["document"][
        "status"] == "verified"
    assert store.history(WORLD, "research", "song-tea")[-1]["author"] == "admin"


def test_the_draft_stays_open_and_cites_the_accepted_source(client, store):
    done = asked_and_imported(client)
    ref, body = first_source(client, done)
    moved = save(client, title="Song tea", body=body).get_json()["sources"][0]
    after = detail(client, slug_of(done))
    assert after["sources"][0]["ref"] == moved
    assert after["sources"][0]["new"] is False
    assert all(c["source"] != ref for f in after["facts"] for c in f["citations"])
    draft = after["article"]["document"]
    assert moved in draft["sources"] and f"[[{moved}]]" in draft["body"]
    assert f"[[{ref}]]" not in draft["body"]
    inbox = {doc["id"] for doc in store.list_documents(WORLD, "research-inbox")}
    assert ref.split("/", 1)[1] not in inbox, "moved out of the inbox"
    assert after["job"]["notes"] == ["research/song-tea"]


def test_one_draft_can_feed_two_notes(client, store):
    done = asked_and_imported(client)
    rows = detail(client, slug_of(done))["sources"]
    save(client, title="Tea", body=f"One. [[{rows[0]['ref']}]]")
    second = save(client, title="Bowls", body=f"Two. [[{rows[1]['ref']}]]").get_json()
    assert second["note"] == "research/bowls"
    job = follow(client, done["id"]).get_json()
    assert job["notes"] == ["research/tea", "research/bowls"]
    assert job["review"] == "pending"


def test_a_source_another_note_already_accepted_is_relinked(client, store):
    first = asked_and_imported(client)
    second = asked_and_imported(client)   # the fake cites the same pages again
    url = detail(client, slug_of(first))["sources"][0]["url"]
    ref_a = detail(client, slug_of(first))["sources"][0]["ref"]
    ref_b = next(row["ref"] for row in detail(client, slug_of(second))["sources"]
                 if row["url"] == url)
    save(client, title="Tea", body=f"A. [[{ref_a}]]")
    again = save(client, title="Tea again", body=f"B. [[{ref_b}]]").get_json()
    assert again["sources"] == [] and len(again["relinked"]) == 1
    assert len(store.list_documents(WORLD, "sources")) == 1


@pytest.mark.parametrize("body", [
    "Cites a draft. [[research-inbox/{draft}]]",
    "Cites nothing real. [[research-inbox/no-such-source]]",
])
def test_a_note_may_cite_only_open_drafts_sources(client, store, body):
    done = asked_and_imported(client)
    response = save(client, title="Tea", body=body.format(draft=slug_of(done)))
    assert response.status_code == 400
    assert "research" not in store.list_collections(WORLD)


def test_naming_a_draft_that_is_not_open_is_refused(client, store):
    done = asked_and_imported(client)
    client.post(f"{BASE}/inbox/{slug_of(done)}/reject")
    response = save(client, title="Tea", body="Plain text.", drafts=[done["draft"]])
    assert response.status_code == 409
    assert "research" not in store.list_collections(WORLD)


# -- updating an existing note ---------------------------------------------------


@pytest.fixture
def existing_note(client):
    """A note made in the studio, then hand-edited to carry an extra field."""
    saved = save(client, title="Tea", body="What I knew before.").get_json()
    return saved


def test_updating_a_note_appends_new_material(client, store, existing_note):
    done = asked_and_imported(client)
    _ref, body = first_source(client, done)
    response = save(client, note="tea", rev=existing_note["rev"], title="Tea",
                    body="What I knew before.\n\n" + body)
    assert response.status_code == 200
    saved = conforms(response.get_json(), "ResearchNoteSaved")
    assert saved["rev"] == existing_note["rev"] + 1
    note = store.get(WORLD, "research", "tea")["document"]
    assert note["body"].startswith("What I knew before.")
    assert note["sources"] == saved["sources"]


def test_a_note_changed_meanwhile_is_refused_and_nothing_moves(client, store,
                                                               existing_note):
    done = asked_and_imported(client)
    ref, body = first_source(client, done)
    store.update(WORLD, "research", "tea", {"title": "Tea", "body": "Edited."})
    response = save(client, note="tea", rev=existing_note["rev"], title="Tea",
                    body=body)
    assert response.status_code == 409
    assert "sources" not in store.list_collections(WORLD), "nothing moved"
    assert detail(client, slug_of(done))["sources"][0]["ref"] == ref
    assert store.get(WORLD, "research", "tea")["document"]["body"] == "Edited."


def test_updating_a_note_that_does_not_exist(client):
    response = save(client, note="nothing", rev=1, title="Tea", body="Text.")
    assert response.status_code == 404


# -- closing a draft -------------------------------------------------------------


def test_done_closes_the_draft_and_keeps_what_notes_took(client, store):
    done = asked_and_imported(client)
    _ref, body = first_source(client, done)
    moved = save(client, title="Tea", body=body).get_json()["sources"][0]
    response = client.post(f"{BASE}/inbox/{slug_of(done)}/done")
    assert response.status_code == 204
    assert store.list_documents(WORLD, "research-inbox") == []
    assert store.get(WORLD, "sources", moved.split("/", 1)[1])
    job = conforms(follow(client, done["id"]).get_json(), "ResearchJob")
    assert (job["review"], job["draft"], job["notes"]) == ("done", None,
                                                           ["research/tea"])
    again = client.post(f"{BASE}/inbox/{slug_of(done)}/done")
    assert again.status_code == 409


# -- who may do what -------------------------------------------------------------


def test_a_reader_may_neither_save_nor_close(build, fake, world, auth_store):
    writer = build(RemoteResearcher(fake))
    done = asked_and_imported(writer)
    reader = build(RemoteResearcher(fake), *user(auth_store, "reader", [READ]))
    assert save(reader, title="Tea", body="Text.").status_code == 403
    assert reader.post(f"{BASE}/inbox/{slug_of(done)}/done").status_code == 403


def test_saving_needs_create_for_a_new_note_and_write_for_an_update(
        build, fake, world, auth_store):
    writer = build(RemoteResearcher(fake))
    save(writer, title="Tea", body="Mine.")
    name, password = user(auth_store, "helper", [READ])
    for collection in ("research-inbox", "sources"):
        auth_store.add_grant(name, WORLD, collection, None, [READ, WRITE],
                             granted_by="admin")
    helper = build(RemoteResearcher(fake), name, password)
    assert save(helper, title="New", body="Text.").status_code == 403
    assert save(helper, note="tea", rev=1, title="Tea", body="Theirs.").status_code == 403
    auth_store.add_grant(name, WORLD, "research", "tea", [READ, WRITE],
                         granted_by="admin")
    assert save(helper, note="tea", rev=1, title="Tea", body="Theirs.").status_code == 200
    assert save(helper, title="New", body="Text.").status_code == 403
