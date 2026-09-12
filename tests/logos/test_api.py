"""The Logos API: hierarchy, derived numbering, concurrency and permissions."""

import pytest

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


def test_moving_a_section_preserves_its_history_and_drafts(section, logos_store):
    section.post(f"{MANUSCRIPT}/volumes/two", json={"title": "Volume Two"})
    current = section.get(SECTION_URL).get_json()
    revised = section.put(
        SECTION_URL,
        json=section_payload(doc=document("A revised opening.")),
        headers={"If-Match": f'"{current["rev"]}"'},
    ).get_json()
    alternate = section.post(
        SECTION_URL + "/drafts", json={"name": "Alternate"}
    ).get_json()

    moved = section.put(
        SECTION_URL + "/placement",
        json={"target_volume": "two", "before": None},
        headers={"If-Match": f'"{revised["rev"]}"'},
    )

    assert moved.status_code == 200
    assert section.get(SECTION_URL).status_code == 404
    target = f"{MANUSCRIPT}/volumes/two/sections/{SECTION}"
    assert section.get(target).get_json()["document"] == document(
        "A revised opening."
    )
    # Filing a chapter is not editing it: the version list is the one the
    # writer built, with no entry for the move and nothing evicted to make
    # room for one.
    assert [
        row["rev"] for row in section.get(target + "/versions").get_json()["versions"]
    ] == [2, 1]
    assert section.get(target).get_json()["rev"] == revised["rev"]
    drafts = section.get(target + "/drafts").get_json()["drafts"]
    assert {row["id"] for row in drafts} == {"draft-1", alternate["id"]}
    draft_history = section.get(target + "/drafts/draft-1/versions").get_json()
    assert [row["rev"] for row in draft_history["versions"]] == [2, 1]
    search = section.get(f"{MANUSCRIPT}/search?q=revised").get_json()
    assert [(row["volume"], row["section"]) for row in search["results"]] == [
        ("two", SECTION)
    ]
    assert [
        (row["volume"], row["section"])
        for row in logos_store.sections_referencing(BOOK, "opening")
    ] == [("two", SECTION)]
    assert moved.get_json()["section_aliases"] == [
        {
            "source_volume": VOLUME,
            "target_volume": "two",
            "section": SECTION,
        }
    ]


def test_a_name_freed_by_a_move_can_be_used_again(section):
    """A writer who moves 'Arrival' out of a volume may write a new one there.

    The alias left behind is a convenience for stale links, and it must never
    outrank a real section: reusing the address retires it rather than locking
    the name out of the volume forever.
    """
    section.post(f"{MANUSCRIPT}/volumes/two", json={"title": "Volume Two"})
    current = section.get(SECTION_URL).get_json()
    section.put(
        SECTION_URL + "/placement",
        json={"target_volume": "two", "before": None},
        headers={"If-Match": f'"{current["rev"]}"'},
    )

    reused = section.post(SECTION_URL, json=section_payload(title="A New One"))

    assert reused.status_code == 201
    assert section.get(SECTION_URL).get_json()["title"] == "A New One"
    # The moved section is untouched, and the now-ambiguous alias is gone.
    target = f"{MANUSCRIPT}/volumes/two/sections/{SECTION}"
    assert section.get(target).status_code == 200
    assert section.get(MANUSCRIPT).get_json()["section_aliases"] == []


def test_a_name_cannot_be_reused_while_its_move_is_unfinished(
    section, logos_store, monkeypatch
):
    section.post(f"{MANUSCRIPT}/volumes/two", json={"title": "Volume Two"})
    current = section.get(SECTION_URL).get_json()

    def interrupt(*_args, **_kwargs):
        raise RuntimeError("simulated interruption")

    monkeypatch.setattr(logos_store, "relocate_draft", interrupt)
    with pytest.raises(RuntimeError):
        section.put(
            SECTION_URL + "/placement",
            json={"target_volume": "two", "before": None},
            headers={"If-Match": f'"{current["rev"]}"'},
        )

    blocked = section.post(SECTION_URL, json=section_payload(title="A New One"))

    assert blocked.status_code == 409
    assert "Finish that move" in blocked.get_json()["error"]


def test_a_round_trip_leaves_one_alias_and_never_a_self_alias(section):
    """Aliases are bounded by where a section has lived, not by how often it moved.

    Coming home keeps the alias for the volume it visited -- a bookmark made
    there still resolves -- but the row naming its own home is meaningless and
    goes, so filing a chapter back and forth cannot grow the table.
    """
    section.post(f"{MANUSCRIPT}/volumes/two", json={"title": "Volume Two"})
    away = section.put(
        SECTION_URL + "/placement",
        json={"target_volume": "two", "before": None},
        headers={"If-Match": f'"{section.get(SECTION_URL).get_json()["rev"]}"'},
    ).get_json()
    assert len(away["section_aliases"]) == 1
    target = f"{MANUSCRIPT}/volumes/two/sections/{SECTION}"

    home = section.put(
        target + "/placement",
        json={"target_volume": VOLUME, "before": None},
        headers={"If-Match": f'"{section.get(target).get_json()["rev"]}"'},
    ).get_json()

    assert home["section_aliases"] == [
        {"source_volume": "two", "target_volume": VOLUME, "section": SECTION}
    ]
    assert section.get(SECTION_URL).status_code == 200
    # A second round trip adds nothing: the table tracks places, not journeys.
    for destination in ("two", VOLUME):
        at = SECTION_URL if destination == "two" else target
        last = section.put(
            at + "/placement",
            json={"target_volume": destination, "before": None},
            headers={"If-Match": f'"{section.get(at).get_json()["rev"]}"'},
        ).get_json()
    assert len(last["section_aliases"]) == 1


def test_an_alias_chain_collapses_to_the_current_home(section):
    section.post(f"{MANUSCRIPT}/volumes/two", json={"title": "Two"})
    section.post(f"{MANUSCRIPT}/volumes/three", json={"title": "Three"})
    at = SECTION_URL
    for destination in ("two", "three"):
        rev = section.get(at).get_json()["rev"]
        moved = section.put(
            at + "/placement",
            json={"target_volume": destination, "before": None},
            headers={"If-Match": f'"{rev}"'},
        ).get_json()
        at = f"{MANUSCRIPT}/volumes/{destination}/sections/{SECTION}"

    # Two hops, two aliases -- and both point at where the section is now,
    # so a stale link resolves in one step rather than walking the chain.
    assert sorted(
        (row["source_volume"], row["target_volume"])
        for row in moved["section_aliases"]
    ) == [(VOLUME, "three"), ("two", "three")]


def test_a_moved_section_can_be_inserted_between_target_sections(section):
    section.post(f"{MANUSCRIPT}/volumes/two", json={"title": "Volume Two"})
    for section_id in ("first", "last"):
        section.post(
            f"{MANUSCRIPT}/volumes/two/sections/{section_id}",
            json=section_payload(title=section_id.title(), events=()),
        )
    current = section.get(SECTION_URL).get_json()

    moved = section.put(
        SECTION_URL + "/placement",
        json={"target_volume": "two", "before": "last"},
        headers={"If-Match": f'"{current["rev"]}"'},
    ).get_json()

    target = next(volume for volume in moved["volumes"] if volume["id"] == "two")
    assert [(row["id"], row["number"]) for row in target["sections"]] == [
        ("first", 1),
        (SECTION, 2),
        ("last", 3),
    ]


def test_retrying_the_same_section_move_is_safe(section):
    section.post(f"{MANUSCRIPT}/volumes/two", json={"title": "Volume Two"})
    current = section.get(SECTION_URL).get_json()
    request = {
        "json": {"target_volume": "two", "before": None},
        "headers": {"If-Match": f'"{current["rev"]}"'},
    }

    first = section.put(SECTION_URL + "/placement", **request)
    retry = section.put(SECTION_URL + "/placement", **request)

    assert first.status_code == retry.status_code == 200
    assert [
        row["id"]
        for volume in retry.get_json()["volumes"]
        for row in volume["sections"]
    ] == [SECTION]


def test_a_section_can_move_back_through_a_previous_location(section):
    for volume_id in ("two", "three"):
        section.post(
            f"{MANUSCRIPT}/volumes/{volume_id}", json={"title": volume_id.title()}
        )

    current = section.get(SECTION_URL).get_json()
    first = section.put(
        SECTION_URL + "/placement",
        json={"target_volume": "two", "before": None},
        headers={"If-Match": f'"{current["rev"]}"'},
    ).get_json()
    in_two = next(
        row
        for volume in first["volumes"]
        if volume["id"] == "two"
        for row in volume["sections"]
    )
    second = section.put(
        f"{MANUSCRIPT}/volumes/two/sections/{SECTION}/placement",
        json={"target_volume": VOLUME, "before": None},
        headers={"If-Match": f'"{in_two["rev"]}"'},
    ).get_json()
    back = next(
        row
        for volume in second["volumes"]
        if volume["id"] == VOLUME
        for row in volume["sections"]
    )

    moved_again = section.put(
        SECTION_URL + "/placement",
        json={"target_volume": "three", "before": None},
        headers={"If-Match": f'"{back["rev"]}"'},
    )

    assert moved_again.status_code == 200
    assert section.get(
        f"{MANUSCRIPT}/volumes/three/sections/{SECTION}"
    ).status_code == 200


def test_moving_a_singleton_to_a_volume_that_has_one_is_blocked(volume):
    volume.post(f"{MANUSCRIPT}/volumes/two", json={"title": "Volume Two"})
    source = volume.post(
        f"{VOLUME_URL}/sections/before",
        json=section_payload("prologue", "Before", ()),
    ).get_json()
    volume.post(
        f"{MANUSCRIPT}/volumes/two/sections/other-before",
        json=section_payload("prologue", "Other", ()),
    )

    moved = volume.put(
        f"{VOLUME_URL}/sections/before/placement",
        json={"target_volume": "two", "before": None},
        headers={"If-Match": f'"{source["rev"]}"'},
    )

    assert moved.status_code == 409
    assert moved.get_json()["code"] == "SECTION_KIND_IN_USE"
    assert volume.get(f"{VOLUME_URL}/sections/before").status_code == 200


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
        SECTION_URL + "/placement",
        json={"target_volume": "somewhere", "before": None},
    ).status_code == 428
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
    assert reader.put(
        SECTION_URL + "/placement",
        json={"target_volume": "second", "before": None},
        headers={"If-Match": '"1"'},
    ).status_code == 403


def test_the_book_list_shows_only_books_the_caller_can_read(client, chronos_gateway):
    chronos_gateway.add_book("private", "Someone Else's")

    body = client.get("/books").get_json()

    assert [row["book"] for row in body["books"]] == [BOOK]
    assert body["books"][0]["has_manuscript"] is False


def test_the_book_list_counts_volumes_once_a_manuscript_exists(volume):
    body = volume.get("/books").get_json()["books"][0]

    assert body["has_manuscript"] is True
    assert body["volume_count"] == 1
