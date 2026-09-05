"""Private annotations, bookmarks, checklists and optional position sync."""

from .conftest import BOOK, SECTION, VOLUME, section_payload

BOOK_URL = f"/books/{BOOK}"
ITEMS = f"{BOOK_URL}/me/items"
POSITION = f"{BOOK_URL}/me/position"


def _note(text="Remember this"):
    return {
        "kind": "note",
        "volume": VOLUME,
        "section": SECTION,
        "block": "p1",
        "text": text,
    }


def _spot(section=SECTION, progress=0.4):
    return {
        "volume": VOLUME,
        "section": section,
        "block": "p1",
        "offset": 12,
        "progress": progress,
    }


def _mark(progress=0.4):
    return {"volume": VOLUME, "section": SECTION, "progress": progress}


def test_a_reader_can_keep_private_items_on_a_readable_book(section, app, reader):
    created = reader.post(ITEMS, json=_note())
    assert created.status_code == 201
    assert created.get_json()["excerpt"] == "The gate was open."

    # The owner reads the same manuscript, but not Devi's note.
    assert section.get(ITEMS).get_json()["items"] == []
    assert [item["text"] for item in reader.get(ITEMS).get_json()["items"]] == [
        "Remember this"
    ]
    assert (
        section.delete(
            f"{ITEMS}/{created.get_json()['id']}", headers={"If-Match": '"1"'}
        ).status_code
        == 404
    )


def test_reader_items_validate_their_current_anchor_and_revision(section):
    missing = section.post(ITEMS, json={**_note(), "block": "gone"})
    assert missing.status_code == 400

    created = section.post(ITEMS, json=_note()).get_json()
    changed = section.put(
        f"{ITEMS}/{created['id']}",
        json={"text": "Changed"},
        headers={"If-Match": '"1"'},
    )
    assert changed.get_json()["rev"] == 2
    assert (
        section.delete(
            f"{ITEMS}/{created['id']}", headers={"If-Match": '"1"'}
        ).status_code
        == 409
    )


def test_notes_and_bookmarks_attach_only_to_paragraphs(volume):
    heading_document = {
        "version": 1,
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "id": "heading",
                "level": 1,
                "content": [{"type": "text", "text": "A heading"}],
            }
        ],
    }
    volume.post(
        f"/books/{BOOK}/volumes/{VOLUME}/sections/heading-only",
        json=section_payload(events=(), doc=heading_document),
    )
    response = volume.post(
        ITEMS,
        json={
            "kind": "note",
            "volume": VOLUME,
            "section": "heading-only",
            "block": "heading",
            "text": "Not a paragraph",
        },
    )
    assert response.status_code == 400


def test_book_and_section_checklists_and_bookmarks(section):
    book_item = section.post(
        ITEMS,
        json={"kind": "checklist", "scope": "book", "text": "Proof", "done": False},
    )
    section_item = section.post(
        ITEMS,
        json={
            "kind": "checklist",
            "scope": "section",
            "volume": VOLUME,
            "section": SECTION,
            "text": "Tighten",
            "done": True,
        },
    )
    bookmark_body = {
        "kind": "bookmark",
        "volume": VOLUME,
        "section": SECTION,
        "block": "p1",
        "text": "Gate",
    }
    bookmark = section.post(ITEMS, json=bookmark_body)
    same = section.post(ITEMS, json=bookmark_body)

    assert (
        book_item.status_code == section_item.status_code == bookmark.status_code == 201
    )
    assert same.get_json()["id"] == bookmark.get_json()["id"]
    assert len(section.get(ITEMS).get_json()["items"]) == 3


def test_position_sync_is_opt_in_and_furthest_never_regresses(section):
    assert section.get("/me/reader-settings").get_json() == {
        "sync_reading_position": False
    }
    assert (
        section.put(POSITION, json={"last": _spot(), "furthest": _mark()}).status_code
        == 400
    )

    enabled = section.put("/me/reader-settings", json={"sync_reading_position": True})
    assert enabled.get_json()["sync_reading_position"] is True
    section.put(
        POSITION, json={"last": _spot(progress=0.8), "furthest": _mark(progress=0.8)}
    )
    merged = section.put(
        POSITION, json={"last": _spot(progress=0.2), "furthest": _mark(progress=0.2)}
    ).get_json()["position"]
    assert merged["last"]["progress"] == 0.2
    assert merged["furthest"]["progress"] == 0.8

    section.put("/me/reader-settings", json={"sync_reading_position": False})
    assert section.get(POSITION).get_json()["position"] is None


def test_saving_a_position_reads_no_prose(section, logos_store, monkeypatch):
    """The hot path must not assemble the manuscript.

    A position is written on every scroll pause, and the two questions it asks --
    is the section still here, and which of two marks is further on -- are both
    answered by ordering records. Loading every section's document to answer them
    made a reader scrolling with sync on re-read the whole series several times a
    second.
    """
    section.put("/me/reader-settings", json={"sync_reading_position": True})

    def refuse(*_args, **_kwargs):
        raise AssertionError("saving a reading position loaded section prose")

    monkeypatch.setattr(logos_store, "list_sections", refuse)
    saved = section.put(POSITION, json={"last": _spot(), "furthest": _mark()})

    assert saved.status_code == 200
    assert saved.get_json()["position"]["last"]["progress"] == 0.4
    # Reading it back is just as hot: the library asks it of every book at once.
    assert section.get(POSITION).get_json()["position"]["last"]["progress"] == 0.4


def test_a_mark_in_a_deleted_section_is_dropped_on_save(section):
    section.put("/me/reader-settings", json={"sync_reading_position": True})
    section.put(POSITION, json={"last": _spot(), "furthest": _mark()})

    current = section.get(
        f"/books/{BOOK}/volumes/{VOLUME}/sections/{SECTION}"
    ).get_json()
    section.delete(
        f"/books/{BOOK}/volumes/{VOLUME}/sections/{SECTION}",
        headers={"If-Match": f'"{current["rev"]}"'},
    )

    assert section.get(POSITION).get_json()["position"] is None


def test_private_items_are_removed_with_the_manuscript(section, logos_store):
    section.post(ITEMS, json=_note())
    logos_store.purge_book(BOOK)
    assert logos_store.list_reader_items("mara", BOOK) == []
