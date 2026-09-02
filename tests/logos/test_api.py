"""The Logos API: hierarchy, derived numbering, concurrency and permissions."""

from .conftest import BOOK, SECTION, VOLUME, document, mention, section_payload

MANUSCRIPT = f"/books/{BOOK}"
VOLUME_URL = f"{MANUSCRIPT}/volumes/{VOLUME}"
SECTION_URL = f"{VOLUME_URL}/sections/{SECTION}"


def test_health_is_public(app):
    assert app.test_client().get("/health").get_json() == {
        "status": "ok",
        "service": "logos",
    }


def test_an_unauthenticated_api_read_answers_json_not_a_login_page(app):
    response = app.test_client().get(
        MANUSCRIPT, headers={"Accept": "application/json"}
    )
    assert response.status_code == 401
    assert response.is_json


def test_the_shared_login_page_assets_are_served(app):
    assert app.test_client().get("/static/shared/service-nav.css").status_code == 200


def test_an_existing_chronos_book_starts_with_an_empty_manuscript(client):
    response = client.get(MANUSCRIPT)
    body = response.get_json()

    assert response.status_code == 200
    assert body["title"] == "The Ember Pact"
    assert body["volumes"] == []
    assert body["rev"] == 0
    # Nothing to quote back, so no precondition is offered.
    assert "ETag" not in response.headers
    assert body["permissions"] == {"write": True, "delete": True}


def test_logos_never_invents_a_chronos_book(client, auth_store):
    """A book you hold no grant on is indistinguishable from one that is not
    there; only once you are entitled to it does the API admit it is missing."""
    assert client.get("/books/ghost").status_code == 403

    auth_store.grant_owner(
        "mara", "ghost", None, None, ["read", "write"], resource_type="book"
    )

    assert client.get("/books/ghost").status_code == 404
    created = client.post("/books/ghost/volumes/one", json={"title": "One"})
    assert created.status_code == 404
    assert created.get_json()["code"] == "BOOK_NOT_FOUND"


def test_chapters_are_numbered_from_their_order_and_other_kinds_are_not(volume):
    prologue = volume.post(
        f"{VOLUME_URL}/sections/before",
        json=section_payload("prologue", "Before", ()),
    )
    first = volume.post(SECTION_URL, json=section_payload())
    second = volume.post(
        f"{VOLUME_URL}/sections/the-oath",
        json=section_payload("chapter", "The Oath", ("climax",)),
    )

    assert prologue.get_json()["number"] is None
    assert first.get_json()["number"] == 1
    assert second.get_json()["number"] == 2

    manuscript = volume.get(MANUSCRIPT).get_json()
    assert manuscript["volumes"][0]["number"] == 1
    assert manuscript["volumes"][0]["section_count"] == 3
    assert manuscript["word_count"] == 12


def test_reordering_sections_renumbers_the_chapters(volume):
    for section_id in ("one", "two"):
        assert volume.post(
            f"{VOLUME_URL}/sections/{section_id}",
            json=section_payload("chapter", section_id.title(), ()),
        ).status_code == 201
    current = volume.get(VOLUME_URL)

    reordered = volume.put(
        f"{VOLUME_URL}/section-order",
        json={"sections": ["two", "one"]},
        headers={"If-Match": current.headers["ETag"]},
    )

    assert reordered.status_code == 200
    assert [
        (row["id"], row["number"]) for row in reordered.get_json()["sections"]
    ] == [("two", 1), ("one", 2)]


def test_reordering_volumes_renumbers_them(volume):
    assert volume.post(
        f"{MANUSCRIPT}/volumes/second", json={"title": "Second"}
    ).status_code == 201
    current = volume.get(MANUSCRIPT)

    reordered = volume.put(
        f"{MANUSCRIPT}/volume-order",
        json={"volumes": ["second", VOLUME]},
        headers={"If-Match": current.headers["ETag"]},
    )

    assert reordered.status_code == 200
    assert [
        (row["id"], row["number"]) for row in reordered.get_json()["volumes"]
    ] == [("second", 1), (VOLUME, 2)]


def test_a_volume_update_cannot_rearrange_or_drop_its_prose(section):
    before = section.get(VOLUME_URL).get_json()

    updated = section.put(
        VOLUME_URL,
        json={"title": "Renamed", "overview": ""},
        headers={"If-Match": f'"{before["rev"]}"'},
    )

    assert updated.status_code == 200
    assert updated.get_json()["title"] == "Renamed"
    assert [row["id"] for row in updated.get_json()["sections"]] == [SECTION]


def test_every_mutation_needs_the_revision_the_caller_read(section):
    payload = section_payload()

    assert section.put(SECTION_URL, json=payload).status_code == 428
    assert section.put(
        SECTION_URL, json=payload, headers={"If-Match": '"*"'}
    ).status_code == 400
    assert section.put(
        SECTION_URL, json=payload, headers={"If-Match": '"1"'}
    ).status_code == 200

    stale = section.put(SECTION_URL, json=payload, headers={"If-Match": '"1"'})
    assert stale.status_code == 409
    assert stale.get_json()["code"] == "REVISION_CONFLICT"


def test_a_section_keeps_a_restorable_history(section):
    revised = section_payload(doc=document("A completely different draft."))
    updated = section.put(SECTION_URL, json=revised, headers={"If-Match": '"1"'})
    assert updated.get_json()["document"] == revised["document"]

    history = section.get(SECTION_URL + "/versions").get_json()["versions"]
    assert [item["rev"] for item in history] == [2, 1]

    original = section.get(SECTION_URL + "/versions/1").get_json()
    assert original["document"] == section_payload()["document"]

    restored = section.post(SECTION_URL + "/restore/1", headers={"If-Match": '"2"'})
    assert restored.status_code == 200
    assert restored.get_json()["rev"] == 3
    assert restored.get_json()["document"] == section_payload()["document"]


def test_a_volume_holds_at_most_one_prologue_epilogue_or_glossary(volume):
    first = volume.post(
        f"{VOLUME_URL}/sections/before", json=section_payload("prologue", "One", ())
    )
    assert first.status_code == 201

    second = volume.post(
        f"{VOLUME_URL}/sections/earlier", json=section_payload("prologue", "Two", ())
    )
    assert second.status_code == 409
    assert second.get_json()["code"] == "SECTION_KIND_IN_USE"


def test_a_section_may_only_name_scenes_that_exist(volume):
    response = volume.post(
        f"{VOLUME_URL}/sections/missing",
        json=section_payload(events=("not-a-scene",)),
    )

    assert response.status_code == 422
    assert response.get_json()["code"] == "CHRONOS_EVENT_NOT_FOUND"
    assert response.get_json()["evidence"] == {"events": ["not-a-scene"]}


def test_a_mention_of_a_deleted_article_is_reported_not_refused(
    volume, article_gateway
):
    created = volume.post(
        f"{VOLUME_URL}/sections/mentions",
        json=section_payload(events=(), doc=mention("lyra", "Lyra")),
    )
    assert created.status_code == 201
    assert created.get_json()["missing_refs"] == []

    article_gateway.remove("ember", "characters", "lyra")

    read = volume.get(f"{VOLUME_URL}/sections/mentions").get_json()
    assert read["missing_refs"] == [
        {"database": "ember", "collection": "characters", "id": "lyra"}
    ]
    # The prose itself is untouched -- only the report changes.
    assert read["document"] == mention("lyra", "Lyra")


def test_the_book_report_counts_progress_and_lists_dangling_mentions(
    volume, article_gateway
):
    volume.post(
        f"{VOLUME_URL}/sections/mentions",
        json=section_payload(events=(), doc=mention("lyra", "Lyra")),
    )
    article_gateway.remove("ember", "characters", "lyra")

    report = volume.get(MANUSCRIPT + "/report").get_json()

    assert report["volume_count"] == 1
    assert report["section_count"] == 1
    assert report["word_count"] == 1
    assert report["sections_with_missing_refs"] == [
        {
            "volume": VOLUME,
            "section": "mentions",
            "missing_refs": [
                {"database": "ember", "collection": "characters", "id": "lyra"}
            ],
        }
    ]


def test_deleting_a_volume_or_manuscript_that_holds_prose_needs_cascade(
    section, logos_store
):
    current = section.get(VOLUME_URL).get_json()
    refused = section.delete(VOLUME_URL, headers={"If-Match": f'"{current["rev"]}"'})
    assert refused.status_code == 409
    assert refused.get_json()["code"] == "CASCADE_REQUIRED"

    removed = section.delete(
        VOLUME_URL + "?cascade=true", headers={"If-Match": f'"{current["rev"]}"'}
    )
    assert removed.status_code == 204
    assert section.get(VOLUME_URL).status_code == 404
    assert section.get(MANUSCRIPT).get_json()["volumes"] == []
    # The manuscript itself outlives its last volume until deleted explicitly,
    # which is what keeps the Chronos book protected in the meantime.
    assert logos_store.has_content(BOOK)


def test_an_explicit_manuscript_delete_purges_the_retained_prose(
    section, logos_store
):
    manuscript = section.get(MANUSCRIPT)

    response = section.delete(
        MANUSCRIPT + "?cascade=true", headers={"If-Match": manuscript.headers["ETag"]}
    )

    assert response.status_code == 204
    assert not logos_store.has_content(BOOK)
    assert logos_store.list_volumes(BOOK) == []
    assert logos_store.list_sections(BOOK) == []


def test_a_deleted_section_leaves_the_volume_consistent(section):
    volume_before = section.get(VOLUME_URL).get_json()

    removed = section.delete(SECTION_URL, headers={"If-Match": '"1"'})

    assert removed.status_code == 204
    after = section.get(VOLUME_URL).get_json()
    assert after["sections"] == []
    assert after["section_count"] == 0
    assert after["rev"] > volume_before["rev"]


def test_a_reader_may_read_everything_and_write_nothing(reader, section):
    readable = reader.get(VOLUME_URL)
    assert readable.status_code == 200
    assert readable.get_json()["permissions"] == {"write": False, "delete": False}

    assert reader.post(
        f"{MANUSCRIPT}/volumes/second", json={"title": "Second"}
    ).status_code == 403
    assert reader.delete(SECTION_URL, headers={"If-Match": '"1"'}).status_code == 403


def test_the_book_list_shows_only_books_the_caller_can_read(client, chronos_gateway):
    chronos_gateway.add_book("private", "Someone Else's")

    body = client.get("/books").get_json()

    assert [row["book"] for row in body["books"]] == [BOOK]
    assert body["books"][0]["has_manuscript"] is False


def test_the_book_list_counts_volumes_once_a_manuscript_exists(volume):
    body = volume.get("/books").get_json()["books"][0]

    assert body["has_manuscript"] is True
    assert body["volume_count"] == 1
