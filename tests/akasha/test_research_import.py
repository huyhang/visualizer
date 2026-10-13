"""From a worker's result to Akasha drafts, and from a draft to accepted research."""

import copy
import json
from pathlib import Path

import pytest

from visualizer.akasha.research_import import (
    INBOX,
    SOURCES,
    InvalidResult,
    normalize_url,
    plan_accept,
    plan_import,
    slugify,
    validate_result,
)
from visualizer.akasha.validation import validate_document
from visualizer.gpubox.fake import FakeWorker

SPEC = json.loads((Path(__file__).resolve().parents[2] / "docs" / "gpu_worker"
                   / "openapi.json").read_text())
EXAMPLE = SPEC["paths"]["/jobs/{job_id}"]["get"]["responses"]["200"]["content"][
    "application/json"]["examples"]["researchDone"]["value"]["job"]["result"]
JOB = "rj_0123456789abcdef"


def fake_result(**request):
    worker = FakeWorker()
    job = worker.submit("research", {"question": "Song-dynasty tea culture",
                                     "include_images": True, **request},
                        service="akasha", ref="r1")
    return worker.status(job["id"])["result"]


def imported(result=None, accepted=None, taken=None):
    return plan_import(validate_result(result or fake_result()),
                       question="Song-dynasty tea culture", job_id=JOB,
                       accepted_sources=accepted or {}, taken=taken or set())


# -- shared rules --------------------------------------------------------------


@pytest.mark.parametrize("text,slug", [
    ("The Knight's Road", "the-knights-road"),
    ("Song-Dynasty Tea Culture", "song-dynasty-tea-culture"),
    ("  ¿Qué?  ", "qu"),
    ("宋代点茶", ""),
])
def test_slugs_match_the_front_end(text, slug):
    assert slugify(text) == slug


@pytest.mark.parametrize("a,b", [
    ("https://www.Museum.example/Tea/", "https://museum.example/Tea"),
    ("https://museum.example:443/tea#top", "https://museum.example/tea"),
    ("https://museum.example/tea?utm_source=x&b=2&a=1",
     "https://museum.example/tea?a=1&b=2"),
])
def test_one_spelling_per_page(a, b):
    assert normalize_url(a) == normalize_url(b)


def test_different_pages_stay_different():
    assert normalize_url("https://museum.example/tea?id=1") != \
        normalize_url("https://museum.example/tea?id=2")


# -- validating ----------------------------------------------------------------


def test_the_contract_example_and_a_fake_result_are_accepted():
    for result in (EXAMPLE, fake_result()):
        valid = validate_result(copy.deepcopy(result))
        assert valid["facts"] and valid["sources"]


@pytest.mark.parametrize("break_it", [
    lambda r: r.pop("article"),
    lambda r: r["sources"].append({"key": "x9", "url": "https://a/b", "title": "t"}),
    lambda r: r["sources"][0].update(url="javascript:alert(1)"),
    lambda r: r["verification"].update(status="maybe"),
    lambda r: r["article"].update(title=""),
    lambda r: r["article"]["image_candidates"].append({
        "url": "file:///etc/passwd", "source": "s1", "caption": "", "license": None,
        "fetch_token": "t"}),
])
def test_a_malformed_result_is_refused(break_it):
    result = fake_result()
    break_it(result)
    with pytest.raises(InvalidResult):
        validate_result(result)


def test_a_fact_without_a_real_citation_is_not_imported_as_a_fact():
    result = fake_result()
    result["article"]["facts"][0]["citations"] = []
    result["article"]["facts"][1]["citations"][0]["source"] = "s99"
    valid = validate_result(result)
    assert valid["facts"] == []
    assert {d["reason"] for d in valid["dropped"]} >= {"no_citation"}


# -- importing -----------------------------------------------------------------


def test_drafts_and_new_sources_land_in_the_inbox_unverified():
    plan = imported()
    assert plan.draft["status"] == "unverified"
    assert plan.draft["question"] == "Song-dynasty tea culture"
    assert plan.draft["research_job"] == JOB
    assert len(plan.new_sources) == 2
    for slug, document in plan.new_sources:
        assert document["status"] == "unverified" and document["kind"] == "source"
        assert document["url"].startswith("https://example.org/")
        assert f"{INBOX}/{slug}" in plan.draft["sources"]


def test_every_document_is_flat_enough_for_akasha():
    plan = imported()
    validate_document(plan.draft)
    for _, document in plan.new_sources:
        validate_document(document)


def test_citations_become_links_to_the_sources():
    plan = imported()
    body = plan.draft["body"]
    assert "[[cite:" not in body
    for ref in plan.draft["sources"]:
        assert f"[[{ref}]]" in body


def test_a_source_already_accepted_is_linked_not_copied():
    result = fake_result()
    first_url = result["sources"][0]["url"]
    plan = imported(result, accepted={normalize_url(first_url + "/"): "song-tea"})
    assert f"{SOURCES}/song-tea" in plan.draft["sources"]
    assert "[[sources/song-tea]]" in plan.draft["body"]
    assert [d["url"] for _, d in plan.new_sources] == [result["sources"][1]["url"]]
    rows = {row["ref"]: row["new"] for row in plan.details["sources"]}
    assert rows[f"{SOURCES}/song-tea"] is False


def test_related_articles_are_linked_and_nothing_else():
    result = copy.deepcopy(EXAMPLE)
    plan = imported(result)
    assert plan.draft["body"].endswith(
        "== Related ==\n* [[song-dynasty/research/song-tea-bowls]]")


def test_slugs_never_collide_and_titles_without_latin_letters_still_get_one():
    result = fake_result()
    result["article"]["title"] = "宋代点茶"
    taken = {"example-org-fake-source-1-on-song-dynasty-tea-culture"}
    plan = imported(result, taken=taken)
    assert plan.draft_slug == f"research-{JOB[-8:]}"
    slugs = [slug for slug, _ in plan.new_sources]
    assert len(set(slugs)) == 2 and taken >= set(slugs) | {plan.draft_slug}
    assert "example-org-fake-source-1-on-song-dynasty-tea-culture-2" in slugs


def test_the_nested_details_go_to_the_job_record():
    plan = imported(fake_result(verify="auto"))
    details = plan.details
    assert [f["check"] for f in details["facts"]] == ["supported", "partial"]
    assert plan.draft["partial_facts"] == [details["facts"][1]["text"]]
    assert all(c["source"].startswith(f"{INBOX}/") for f in details["facts"]
               for c in f["citations"])
    image = details["images"][0]
    assert image["fetch_token"] and image["imported"] is None
    assert image["source"].startswith(f"{INBOX}/")
    assert plan.draft["dropped_facts"][0].startswith("quote_not_found: ")


# -- accepting -----------------------------------------------------------------


def accept(plan, **overrides):
    options = {"writer": "mara", "accepted_at": "2026-10-13T20:00:00Z",
               "accepted_sources": {}, "taken_research": set(),
               "taken_sources": set(), "draft_slug": plan.draft_slug}
    options.update(overrides)
    return plan_accept(plan.draft, dict(plan.new_sources), **options)


def test_accepting_moves_the_draft_and_its_sources_verified():
    plan = imported()
    accepted = accept(plan)
    assert accepted.article_slug == plan.draft_slug
    assert accepted.article["status"] == "verified"
    assert (accepted.article["verified_by"], accepted.article["drafted_by"]) == \
        ("mara", "research-bot")
    assert len(accepted.moves) == 2
    for inbox_slug, target, document in accepted.moves:
        assert target == inbox_slug and document["status"] == "verified"
        assert f"[[sources/{target}]]" in accepted.article["body"]
        assert f"[[{INBOX}/{inbox_slug}]]" not in accepted.article["body"]
    assert all(ref.startswith(f"{SOURCES}/") for ref in accepted.article["sources"])
    validate_document(accepted.article)


def test_a_source_accepted_meanwhile_is_relinked_not_duplicated():
    plan = imported()
    (first_slug, first), _ = plan.new_sources
    accepted = accept(plan, accepted_sources={normalize_url(first["url"]): "song-tea"})
    assert accepted.relinked == {first_slug: "song-tea"}
    assert [move[0] for move in accepted.moves] != [first_slug]
    assert "[[sources/song-tea]]" in accepted.article["body"]


def test_taken_names_in_research_and_sources_are_avoided():
    plan = imported()
    first_slug = plan.new_sources[0][0]
    accepted = accept(plan, taken_research={plan.draft_slug},
                      taken_sources={first_slug})
    assert accepted.article_slug == f"{plan.draft_slug}-2"
    targets = {inbox: target for inbox, target, _ in accepted.moves}
    assert targets[first_slug] == f"{first_slug}-2"
    assert f"[[sources/{first_slug}-2]]" in accepted.article["body"]


def test_the_writers_edits_are_what_is_accepted():
    plan = imported()
    plan.draft["body"] += "\nMy own note."
    first_slug = plan.new_sources[0][0]
    edited = {**dict(plan.new_sources)[first_slug], "title": "Corrected title"}
    accepted = plan_accept(plan.draft, {first_slug: edited}, writer="mara",
                           accepted_at="t", accepted_sources={}, taken_research=set(),
                           taken_sources=set(), draft_slug=plan.draft_slug)
    assert accepted.article["body"].endswith("My own note.")
    assert accepted.moves[0][2]["title"] == "Corrected title"
