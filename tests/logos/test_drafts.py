"""Named manuscript drafts, primary projection, and private writing aids."""

import pytest

from visualizer.logos.errors import ReviewUnavailable, VolumeNotFound
from visualizer.logos.models import Volume
from visualizer.logos.services import DraftService, ManuscriptService
from visualizer.logos.writing import RuleBasedWritingAdvisor, SeriesWritingReview

from .conftest import BOOK, SECTION, VOLUME, document, section_payload

SECTION_PATH = f"/books/{BOOK}/volumes/{VOLUME}/sections/{SECTION}"
DRAFTS = SECTION_PATH + "/drafts"


def _manuscripts(store, chronos, articles):
    """The same service the app builds, over the same fixtures' store."""
    return ManuscriptService(store, chronos, articles)


def test_a_section_starts_with_one_primary_draft(section):
    payload = section.get(DRAFTS).get_json()

    assert payload["primary_draft_id"] == "draft-1"
    assert [(row["id"], row["name"], row["primary"]) for row in payload["drafts"]] == [
        ("draft-1", "Draft 1", True)
    ]


def test_opening_a_legacy_section_materializes_its_first_draft(
    volume, logos_store, chronos_gateway, article_gateway
):
    legacy = "written-before-drafts"
    logos_store.create_section(
        BOOK, VOLUME, legacy, section_payload(), "mara"
    )
    service = DraftService(logos_store, chronos_gateway, article_gateway)

    payload = service.list(BOOK, VOLUME, legacy, "mara")

    assert payload["primary_draft_id"] == "draft-1"
    assert payload["drafts"][0]["id"] == "draft-1"
    assert logos_store.get_draft(BOOK, VOLUME, legacy, "draft-1")["document"] == (
        section_payload()["document"]
    )


def test_an_alternate_clones_the_source_without_changing_the_reader(section):
    before = section.get(SECTION_PATH).get_json()
    created = section.post(
        DRAFTS, json={"name": "Lean opening", "source": "draft-1"}
    ).get_json()

    changed = section.put(
        f"{DRAFTS}/{created['id']}",
        json={"name": created["name"], "document": document("A leaner opening.")},
        headers={"If-Match": str(created["rev"])},
    )

    assert changed.status_code == 200
    assert changed.get_json()["document"] == document("A leaner opening.")
    assert section.get(SECTION_PATH).get_json()["document"] == before["document"]


def test_designating_a_draft_changes_the_primary_reader_projection(section):
    created = section.post(DRAFTS, json={"name": "Second pass"}).get_json()
    changed = section.put(
        f"{DRAFTS}/{created['id']}",
        json={"name": "Second pass", "document": document("The stronger opening.")},
        headers={"If-Match": str(created["rev"])},
    ).get_json()
    section_rev = section.get(SECTION_PATH).get_json()["rev"]

    promoted = section.put(
        SECTION_PATH + "/primary-draft",
        json={"draft": created["id"]},
        headers={"If-Match": str(section_rev)},
    )

    assert promoted.status_code == 200
    assert promoted.get_json()["primary_draft_id"] == created["id"]
    primary = section.get(SECTION_PATH).get_json()
    assert primary["document"] == changed["document"]
    assert primary["primary_draft_id"] == created["id"]
    assert section.get(f"/books/{BOOK}/search?q=stronger").get_json()["total"] == 1


def test_section_metadata_can_change_without_replacing_a_draft(section):
    before = section.get(f"{DRAFTS}/draft-1").get_json()
    current = section.get(SECTION_PATH).get_json()

    response = section.put(
        SECTION_PATH + "/metadata",
        json={"title": "A Better Title"},
        headers={"If-Match": str(current["rev"])},
    )

    assert response.status_code == 200
    assert response.get_json()["title"] == "A Better Title"
    after = section.get(f"{DRAFTS}/draft-1").get_json()
    assert after["document"] == before["document"]
    assert after["rev"] == before["rev"]


def test_a_primary_draft_cannot_be_deleted(section):
    draft = section.get(f"{DRAFTS}/draft-1").get_json()
    response = section.delete(
        f"{DRAFTS}/draft-1", headers={"If-Match": str(draft["rev"])}
    )

    assert response.status_code == 409
    assert response.get_json()["code"] == "PRIMARY_DRAFT_CONFLICT"


def test_deleting_a_section_also_tombstones_its_drafts(section, logos_store):
    current = section.get(SECTION_PATH).get_json()
    response = section.delete(
        SECTION_PATH, headers={"If-Match": str(current["rev"])}
    )

    assert response.status_code == 204
    assert logos_store.list_drafts(BOOK, VOLUME, SECTION) == []


def test_draft_saves_require_the_revision_the_writer_read(section):
    draft = section.get(f"{DRAFTS}/draft-1").get_json()
    first = section.put(
        f"{DRAFTS}/draft-1",
        json={"name": draft["name"], "document": document("First tab.")},
        headers={"If-Match": str(draft["rev"])},
    )
    stale = section.put(
        f"{DRAFTS}/draft-1",
        json={"name": draft["name"], "document": document("Second tab.")},
        headers={"If-Match": str(draft["rev"])},
    )

    assert first.status_code == 200
    assert stale.status_code == 409
    assert section.get(f"{DRAFTS}/draft-1").get_json()["document"] == document(
        "First tab."
    )
    assert section.get(SECTION_PATH).get_json()["document"] == document("First tab.")


def test_saving_a_draft_normalizes_straight_quotes(section):
    draft = section.get(f"{DRAFTS}/draft-1").get_json()

    saved = section.put(
        f"{DRAFTS}/draft-1",
        json={"name": draft["name"], "document": document('"Don\'t go," she said.')},
        headers={"If-Match": str(draft["rev"])},
    ).get_json()

    assert saved["document"]["content"][0]["content"][0]["text"] == (
        "\u201cDon\u2019t go,\u201d she said."
    )


def test_a_draft_revision_can_be_restored_without_rewinding_history(section):
    draft = section.get(f"{DRAFTS}/draft-1").get_json()
    changed = section.put(
        f"{DRAFTS}/draft-1",
        json={"name": draft["name"], "document": document("New wording.")},
        headers={"If-Match": str(draft["rev"])},
    ).get_json()

    versions = section.get(f"{DRAFTS}/draft-1/versions").get_json()["versions"]
    restored = section.post(
        f"{DRAFTS}/draft-1/versions/1/restore",
        headers={"If-Match": str(changed["rev"])},
    )

    assert [item["rev"] for item in versions] == [2, 1]
    assert restored.status_code == 200
    assert restored.get_json()["rev"] == 3
    assert restored.get_json()["document"] == draft["document"]
    assert section.get(SECTION_PATH).get_json()["document"] == draft["document"]


def test_alternate_drafts_are_writer_only(section, reader):
    assert reader.get(DRAFTS).status_code == 403


def test_selected_text_can_find_an_akasha_entity(section):
    response = section.get(f"/books/{BOOK}/ui/entities?q=lyra")

    assert response.status_code == 200
    assert response.get_json()["entities"][0] == {
        "database": "ember",
        "database_title": "Ember",
        "collection": "characters",
        "collection_title": "Characters",
        "id": "lyra",
        "title": "Lyra",
        "fields": [],
    }


def test_the_dialect_choice_changes_what_the_advisor_reports(section):
    """The US/UK control has to earn its place in the panel.

    It was wired end to end -- persisted, sent, validated, echoed -- while the
    advisor ignored it, so flipping it changed nothing a writer could see.
    """
    prose = document("The colour of the harbour, and the theater beyond it.")

    def spellings(dialect):
        response = section.post(
            f"/books/{BOOK}/ui/writing-review",
            json={"document": prose, "dialect": dialect},
        )
        assert response.status_code == 200
        return {
            (issue["excerpt"], issue["replacement"])
            for issue in response.get_json()["issues"]
            if issue["category"] == "spelling"
        }

    assert spellings("en-US") == {("colour", "color"), ("harbour", "harbor")}
    assert spellings("en-GB") == {("theater", "theatre")}


def test_the_advisor_leaves_words_that_only_look_like_dialect_variants(section):
    """A pattern rule would flag these; the curated pair list must not."""
    response = section.post(
        f"/books/{BOOK}/ui/writing-review",
        json={
            "document": document("Four hours later the sun would rise again."),
            "dialect": "en-GB",
        },
    )

    assert [
        issue for issue in response.get_json()["issues"]
        if issue["category"] == "spelling"
    ] == []


def test_the_private_writing_advisor_reports_mechanics_and_flow(section):
    long_sentence = " ".join(["word"] * 41) + "."
    response = section.post(
        f"/books/{BOOK}/ui/writing-review",
        json={"document": document(f"She she waited  , then {long_sentence}")},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["private"] is True
    assert {issue["title"] for issue in payload["issues"]} >= {
        "Repeated word",
        "Space before punctuation",
        "Extra spaces",
        "Long sentence",
    }


def test_series_review_defaults_to_primary_and_can_include_alternates(section, reader):
    primary = section.get(f"{DRAFTS}/draft-1").get_json()
    section.put(
        f"{DRAFTS}/draft-1",
        json={"name": primary["name"], "document": document("Gate gate.")},
        headers={"If-Match": str(primary["rev"])},
    )
    alternate = section.post(DRAFTS, json={"name": "Quiet pass"}).get_json()
    section.put(
        f"{DRAFTS}/{alternate['id']}",
        json={"name": alternate["name"], "document": document("Wait wait.")},
        headers={"If-Match": str(alternate["rev"])},
    )

    primary_only = section.get(f"/books/{BOOK}/ui/writing-review").get_json()
    every = section.get(
        f"/books/{BOOK}/ui/writing-review?include_alternates=true"
    ).get_json()

    assert primary_only["reviewed_drafts"] == 1
    assert {issue["draft"] for issue in primary_only["issues"]} == {"draft-1"}
    assert every["reviewed_drafts"] == 2
    assert {issue["draft"] for issue in every["issues"]} == {
        "draft-1", alternate["id"]
    }
    alternate_issue = next(
        issue for issue in every["issues"] if issue["draft"] == alternate["id"]
    )
    assert alternate_issue["draft_name"] == "Quiet pass"
    assert alternate_issue["block"] == "p1"
    assert reader.get(f"/books/{BOOK}/ui/writing-review").status_code == 403


def test_a_clean_series_reports_nothing_and_still_says_what_it_read(section):
    payload = section.get(f"/books/{BOOK}/ui/writing-review").get_json()

    assert payload["issues"] == []
    assert payload["reviewed_drafts"] == 1
    assert payload["private"] is True
    assert payload["include_alternates"] is False


def test_the_series_review_dialect_follows_the_request(section):
    current = section.get(f"{DRAFTS}/draft-1").get_json()
    section.put(
        f"{DRAFTS}/draft-1",
        json={"name": current["name"], "document": document("The harbour was quiet.")},
        headers={"If-Match": str(current["rev"])},
    )

    british = section.get(
        f"/books/{BOOK}/ui/writing-review?dialect=en-GB"
    ).get_json()
    american = section.get(
        f"/books/{BOOK}/ui/writing-review?dialect=en-US"
    ).get_json()

    assert british["issues"] == []
    assert [issue["category"] for issue in american["issues"]] == ["spelling"]
    assert american["dialect"] == "en-US"
    assert section.get(
        f"/books/{BOOK}/ui/writing-review?dialect=en-AU"
    ).status_code == 400


def test_reviewing_a_section_written_before_drafts_materializes_nothing(
    volume, logos_store,
):
    """Reviewing reads. A section that predates named drafts has no draft
    record at all, and asking about it must not quietly create one."""
    legacy = "written-before-drafts"
    logos_store.create_section(BOOK, VOLUME, legacy, section_payload(), "mara")
    record = logos_store.get_volume(BOOK, VOLUME)
    outline = Volume.from_storage(record)
    outline.sections.append(legacy)
    logos_store.update_volume(
        BOOK, VOLUME, outline.to_storage(), record["rev"], "mara"
    )
    assert logos_store.list_drafts(BOOK, VOLUME, legacy) == []

    payload = volume.get(
        f"/books/{BOOK}/ui/writing-review?include_alternates=true"
    ).get_json()

    assert payload["reviewed_drafts"] == 1
    assert logos_store.list_drafts(BOOK, VOLUME, legacy) == []


def test_a_review_can_be_narrowed_to_one_volume(client, logos_store):
    """The cost of a review is the prose it reads, so on a ten-volume series
    the volume filter is not a convenience -- it is the difference between
    reading two million words and two hundred thousand."""
    for volume_id in ("one", "two"):
        assert client.post(
            f"/books/{BOOK}/volumes/{volume_id}",
            json={"title": volume_id, "overview": ""},
        ).status_code == 201
        assert client.post(
            f"/books/{BOOK}/volumes/{volume_id}/sections/{volume_id}-gate",
            json=section_payload(doc=document(f"The the {volume_id} gate.")),
        ).status_code == 201

    whole = client.get(f"/books/{BOOK}/ui/writing-review").get_json()
    just_one = client.get(
        f"/books/{BOOK}/ui/writing-review?volume=one"
    ).get_json()

    assert whole["reviewed_drafts"] == 2
    assert whole["volume"] is None
    assert {issue["volume"] for issue in whole["issues"]} == {"one", "two"}
    assert just_one["reviewed_drafts"] == 1
    assert just_one["volume"] == "one"
    assert {issue["volume"] for issue in just_one["issues"]} == {"one"}
    assert client.get(
        f"/books/{BOOK}/ui/writing-review?volume=never-written"
    ).status_code == 404


def test_asking_for_one_volume_s_prose_leaves_the_others_unread(
    client, logos_store, chronos_gateway, article_gateway,
):
    """`publication` totals itself up over every volume, so it cannot honestly
    be handed a subset -- hence a separate question. The volume still has to
    know its own number, which is its position in the *outline*, so the loop
    walks them all; ordering records carry no prose, which is why walking them
    costs nothing and loading them would cost everything.
    """
    for volume_id in ("one", "two", "three"):
        client.post(f"/books/{BOOK}/volumes/{volume_id}",
                    json={"title": volume_id.title(), "overview": ""})
        client.post(
            f"/books/{BOOK}/volumes/{volume_id}/sections/{volume_id}-gate",
            json=section_payload(doc=document(f"The {volume_id} gate.")),
        )
    manuscripts = _manuscripts(logos_store, chronos_gateway, article_gateway)

    everything = manuscripts.prose(BOOK)
    middle = manuscripts.prose(BOOK, "two")

    assert [entry["id"] for entry in everything] == ["one", "two", "three"]
    assert [entry["id"] for entry in middle] == ["two"]
    # Numbered by where it sits in the series, not by where it sits in the
    # answer -- a filtered second volume is still "Volume 2".
    assert middle[0]["number"] == 2
    assert middle[0]["sections"][0]["document"] == everything[1]["sections"][0][
        "document"
    ]
    with pytest.raises(VolumeNotFound):
        manuscripts.prose(BOOK, "never-written")


def test_a_review_returns_a_bounded_list_and_says_what_it_left_out(
    section, logos_store, chronos_gateway, article_gateway,
):
    """One consistent habit -- a manuscript written in the other dialect, say
    -- produces a finding per paragraph. The work is bounded by the prose, but
    the answer is bounded here, because nobody reads the ten-thousandth."""
    current = section.get(f"{DRAFTS}/draft-1").get_json()
    section.put(
        f"{DRAFTS}/draft-1",
        json={
            "name": current["name"],
            "document": document(*[f"The the gate {n}." for n in range(40)]),
        },
        headers={"If-Match": str(current["rev"])},
    )

    everything = section.get(f"/books/{BOOK}/ui/writing-review").get_json()
    found = everything["issue_count"]
    assert found > 10
    assert len(everything["issues"]) == found
    assert everything["truncated"] is False

    capped = SeriesWritingReview(
        logos_store, _manuscripts(logos_store, chronos_gateway, article_gateway),
        RuleBasedWritingAdvisor(),
        max_findings=10,
    ).review(BOOK)

    assert len(capped["issues"]) == 10
    # The count is what was found, not what was returned -- the UI says "first
    # 10 of N" off this, so truncating it too would hide the truncation.
    assert capped["issue_count"] == found
    assert capped["truncated"] is True


def test_a_third_concurrent_review_is_refused_rather_than_queued(
    section, logos_store, chronos_gateway, article_gateway,
):
    """Each review holds a whole series in memory. Two at once is a cost the
    container can carry; an unbounded queue of them is how one writer's click
    takes the database down with it."""
    review = SeriesWritingReview(
        logos_store, _manuscripts(logos_store, chronos_gateway, article_gateway),
        RuleBasedWritingAdvisor(),
        concurrent_reviews=2,
    )
    held = [review._slots.acquire(blocking=False) for _ in range(2)]
    assert held == [True, True]
    try:
        with pytest.raises(ReviewUnavailable) as refused:
            review.review(BOOK)
    finally:
        for _ in held:
            review._slots.release()

    assert refused.value.status_code == 503
    assert refused.value.code == "REVIEW_UNAVAILABLE"
    # The slot is given back, so the next caller is served.
    assert review.review(BOOK)["book"] == BOOK


def test_a_series_review_names_the_primary_even_without_a_draft_record(
    volume, logos_store,
):
    legacy = "no-draft-record"
    logos_store.create_section(
        BOOK, VOLUME, legacy,
        section_payload(doc=document("The the gate stood open.")), "mara",
    )
    record = logos_store.get_volume(BOOK, VOLUME)
    outline = Volume.from_storage(record)
    outline.sections.append(legacy)
    logos_store.update_volume(
        BOOK, VOLUME, outline.to_storage(), record["rev"], "mara"
    )

    (issue,) = volume.get(f"/books/{BOOK}/ui/writing-review").get_json()["issues"]

    assert issue["title"] == "Repeated word"
    assert issue["section"] == legacy
    assert issue["draft_name"] == "Primary draft"
    assert issue["primary"] is True
