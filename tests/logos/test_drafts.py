"""Named manuscript drafts, primary projection, and private writing aids."""

from visualizer.logos.services import DraftService

from .conftest import BOOK, SECTION, VOLUME, document, section_payload

SECTION_PATH = f"/books/{BOOK}/volumes/{VOLUME}/sections/{SECTION}"
DRAFTS = SECTION_PATH + "/drafts"


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
