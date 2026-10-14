"""The studio's rules, pure: digging deeper, and composing notes from drafts.

No app and no database -- the request rules in ``research`` and the planning
in ``research_import`` are functions from data to data.
"""

import pytest

from visualizer.akasha.errors import InvalidResearchRequest
from visualizer.akasha.research import split_parent, validate_note
from visualizer.akasha.research_import import (
    INBOX,
    SOURCES,
    cited,
    move_sources,
    plan_note,
    relink,
    relink_details,
    relink_draft,
    source_owners,
)
from visualizer.akasha.validation import validate_document

PARENT = "rj_0123456789abcdef"
WRITER = "mara"
AT = "2026-10-13T12:00:00+00:00"


# -- digging deeper ------------------------------------------------------------


@pytest.mark.parametrize("payload,expected", [
    ({"question": "Tea bowls"}, ({"question": "Tea bowls"}, None)),
    ({"question": "Tea bowls", "parent": None}, ({"question": "Tea bowls"}, None)),
    ({"question": "Tea bowls", "parent": PARENT}, ({"question": "Tea bowls"}, PARENT)),
    ("not an object", ("not an object", None)),
])
def test_the_parent_is_taken_off_before_the_box_rules(payload, expected):
    assert split_parent(payload) == expected


@pytest.mark.parametrize("parent", ["", "rj_short", "j_0123456789abcdef", 7,
                                    "rj_0123456789ABCDEF", ["rj_0123456789abcdef"]])
def test_a_parent_must_look_like_a_job(parent):
    with pytest.raises(InvalidResearchRequest, match="parent"):
        split_parent({"question": "Tea bowls", "parent": parent})


# -- what a note save may say ----------------------------------------------------


NEW_NOTE = {"title": " Tea ", "body": " Tea was whisked. [[research-inbox/s1]] "}


@pytest.mark.parametrize("payload,expected", [
    (NEW_NOTE, {"note": None, "rev": None, "title": "Tea",
                "body": "Tea was whisked. [[research-inbox/s1]]", "drafts": []}),
    ({**NEW_NOTE, "note": "tea", "rev": 3},
     {"note": "tea", "rev": 3, "title": "Tea",
      "body": "Tea was whisked. [[research-inbox/s1]]", "drafts": []}),
    ({**NEW_NOTE, "drafts": ["research-inbox/a", "research-inbox/a",
                             "research-inbox/b"]},
     {"note": None, "rev": None, "title": "Tea",
      "body": "Tea was whisked. [[research-inbox/s1]]", "drafts": ["a", "b"]}),
    ({**NEW_NOTE, "rev": 9},
     {"note": None, "rev": None, "title": "Tea",
      "body": "Tea was whisked. [[research-inbox/s1]]", "drafts": []}),
])
def test_a_valid_note(payload, expected):
    assert validate_note(payload) == expected


@pytest.mark.parametrize("payload,message", [
    ([], "JSON object"),
    ({**NEW_NOTE, "colour": "red"}, "Unknown fields: colour"),
    ({**NEW_NOTE, "title": "   "}, "title"),
    ({**NEW_NOTE, "title": "x" * 301}, "title"),
    ({**NEW_NOTE, "body": ""}, "body"),
    ({**NEW_NOTE, "body": "x" * 60_001}, "body"),
    ({**NEW_NOTE, "note": "tea"}, "revision"),
    ({**NEW_NOTE, "note": "tea", "rev": 0}, "revision"),
    ({**NEW_NOTE, "note": "tea", "rev": True}, "revision"),
    ({**NEW_NOTE, "note": "../tea", "rev": 1}, "slug"),
    ({**NEW_NOTE, "drafts": ["research/tea"]}, "drafts"),
    ({**NEW_NOTE, "drafts": "research-inbox/a"}, "drafts"),
])
def test_an_invalid_note_is_refused(payload, message):
    with pytest.raises(InvalidResearchRequest, match=message):
        validate_note(payload)


# -- reading citations out of a body ----------------------------------------------


@pytest.mark.parametrize("text,collection,expected", [
    ("plain", INBOX, []),
    ("a [[research-inbox/x]] b [[research-inbox/y|Y]] [[research-inbox/x]]",
     INBOX, ["x", "y"]),
    ("[[sources/s]] [[research-inbox/x]]", INBOX, ["x"]),
    ("[[sources/s]] [[sources/t|T]] [[research-inbox/x]]", SOURCES, ["s", "t"]),
    ("[[song/research-inbox/x]]", INBOX, []),
])
def test_citations_are_read_in_order_without_repeats(text, collection, expected):
    assert cited(text, collection) == expected


def test_each_inbox_source_has_the_pending_job_whose_draft_cites_it():
    one = {"_id": "rj_1", "details": {"sources": [
        {"ref": "research-inbox/a"}, {"ref": "sources/accepted"}]}}
    two = {"_id": "rj_2", "details": {"sources": [{"ref": "research-inbox/b"}]}}
    bare = {"_id": "rj_3", "details": None}
    owners = source_owners([one, two, bare])
    assert {slug: job["_id"] for slug, job in owners.items()} == {"a": "rj_1",
                                                                  "b": "rj_2"}


# -- planning a note ---------------------------------------------------------------


def source(url, title="A page"):
    return {"title": title, "url": url, "kind": "source", "status": "unverified",
            "research_job": "rj_1", "excerpts": ["…"]}


INBOX_SOURCES = {"museum-tea": source("https://museum.example/tea"),
                 "blog-tea": source("https://blog.example/tea?utm_source=x")}
BODY = ("Tea was whisked [[research-inbox/museum-tea]] in bowls "
        "[[research-inbox/blog-tea|a blog]]. See also [[sources/older]].")


def planned(**overrides):
    args = {"title": "Song tea", "body": BODY, "inbox_sources": dict(INBOX_SOURCES),
            "existing": None, "slug": None, "writer": WRITER, "saved_at": AT,
            "accepted_sources": {}, "taken_research": set(), "taken_sources": set()}
    return plan_note(**{**args, **overrides})


def test_a_new_note_cites_its_sources_from_sources():
    plan = planned()
    assert plan.slug == "song-tea"
    assert plan.document["body"] == (
        "Tea was whisked [[sources/museum-tea]] in bowls "
        "[[sources/blog-tea|a blog]]. See also [[sources/older]].")
    assert plan.document["sources"] == ["sources/museum-tea", "sources/blog-tea",
                                        "sources/older"]
    assert (plan.document["status"], plan.document["verified_by"]) == ("verified",
                                                                        WRITER)
    assert [(old, new) for old, new, _ in plan.moves] == [("museum-tea", "museum-tea"),
                                                          ("blog-tea", "blog-tea")]
    assert all(doc["status"] == "verified" for _, _, doc in plan.moves)
    validate_document(plan.document)


def test_a_source_already_accepted_is_relinked_not_moved():
    plan = planned(accepted_sources={"https://blog.example/tea": "the-blog"})
    assert plan.relinked == {"blog-tea": "the-blog"}
    assert [old for old, _, _ in plan.moves] == ["museum-tea"]
    assert "[[sources/the-blog|a blog]]" in plan.document["body"]
    assert plan.mapping == {"museum-tea": "museum-tea", "blog-tea": "the-blog"}


@pytest.mark.parametrize("taken_research,taken_sources,slug,moved_to", [
    (set(), set(), "song-tea", "museum-tea"),
    ({"song-tea"}, {"museum-tea"}, "song-tea-2", "museum-tea-2"),
])
def test_names_already_taken_are_avoided(taken_research, taken_sources, slug, moved_to):
    plan = planned(taken_research=taken_research, taken_sources=taken_sources)
    assert plan.slug == slug
    assert plan.moves[0][1] == moved_to


def test_updating_keeps_the_notes_other_fields_and_grows_its_sources():
    existing = {"title": "Tea", "body": "Old", "era": "Song",
                "sources": ["sources/older", "sources/elsewhere"]}
    plan = planned(existing=existing, slug="tea", title="Tea, revised")
    assert plan.slug == "tea"
    assert plan.document["era"] == "Song" and plan.document["title"] == "Tea, revised"
    assert plan.document["sources"] == ["sources/older", "sources/elsewhere",
                                        "sources/museum-tea", "sources/blog-tea"]
    assert "verified_by" not in plan.document


CITED = ["sources/museum-tea", "sources/blog-tea", "sources/older"]


@pytest.mark.parametrize("earlier,expected", [
    (None, CITED),
    ("sources/older", CITED),
    ([3, "sources/older"], ["sources/older", "sources/museum-tea", "sources/blog-tea"]),
])
def test_an_existing_sources_field_of_any_shape_is_survived(earlier, expected):
    plan = planned(existing={"title": "Tea", "sources": earlier}, slug="tea")
    assert plan.document["sources"] == expected


def test_moving_sources_keeps_free_slugs_and_reports_each_destination():
    moved = move_sources({"a": source("https://a.example/"),
                          "b": source("https://b.example/")},
                         writer=WRITER, accepted_at=AT,
                         accepted_sources={"https://b.example": "known-b"},
                         taken_sources={"a"})
    assert moved.mapping == {"a": "a-2", "b": "known-b"}
    assert moved.relinked == {"b": "known-b"}


# -- the drafts left open ----------------------------------------------------------


MAPPING = {"museum-tea": "museum-tea"}


@pytest.mark.parametrize("text,expected", [
    ("[[research-inbox/museum-tea]]", "[[sources/museum-tea]]"),
    ("[[research-inbox/museum-tea|label]]", "[[sources/museum-tea|label]]"),
    ("[[research-inbox/blog-tea]]", "[[research-inbox/blog-tea]]"),
    ("[[research-inbox/museum-tea-2]]", "[[research-inbox/museum-tea-2]]"),
])
def test_relinking_touches_only_the_sources_moved(text, expected):
    assert relink(text, MAPPING) == expected


def test_an_open_draft_is_relinked_to_what_a_note_accepted():
    draft = {"title": "Tea", "body": BODY,
             "sources": ["research-inbox/museum-tea", "research-inbox/blog-tea"]}
    relinked = relink_draft(draft, MAPPING)
    assert relinked["sources"] == ["sources/museum-tea", "research-inbox/blog-tea"]
    assert "[[sources/museum-tea]]" in relinked["body"]
    assert "[[research-inbox/blog-tea|a blog]]" in relinked["body"]


def test_the_job_details_follow_the_draft():
    details = {
        "facts": [{"text": "Whisked.", "check": "supported", "citations": [
            {"source": "research-inbox/museum-tea", "quote": "whisked"},
            {"source": "research-inbox/blog-tea", "quote": "froth"}]}],
        "sources": [{"key": "s1", "ref": "research-inbox/museum-tea", "new": True},
                    {"key": "s2", "ref": "research-inbox/blog-tea", "new": True},
                    {"key": "s3", "ref": "sources/older", "new": False}],
        "images": [{"source": "research-inbox/museum-tea", "url": "u"}],
        "verification": {"status": "checked"},
    }
    relinked = relink_details(details, MAPPING)
    assert [c["source"] for c in relinked["facts"][0]["citations"]] == [
        "sources/museum-tea", "research-inbox/blog-tea"]
    assert [(r["ref"], r["new"]) for r in relinked["sources"]] == [
        ("sources/museum-tea", False), ("research-inbox/blog-tea", True),
        ("sources/older", False)]
    assert relinked["images"][0]["source"] == "sources/museum-tea"
    assert relinked["verification"] == {"status": "checked"}
