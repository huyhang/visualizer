"""Search spans current prose and publication structure across volumes."""

import pytest

from .conftest import BOOK, VOLUME, document, section_payload

SEARCH = f"/books/{BOOK}/search"


@pytest.fixture
def no_writes(logos_store, monkeypatch):
    """Fail the test if anything writes to the search projection."""

    def refuse(name):
        def guard(*_args, **_kwargs):
            raise AssertionError(f"search performed a write: {name}")

        return guard

    for name in ("replace_one", "delete_many", "insert_one", "insert_many"):
        monkeypatch.setattr(logos_store._search_blocks, name, refuse(name))
    return logos_store


def test_search_finds_text_and_returns_a_block_target(volume):
    volume.post(
        f"/books/{BOOK}/volumes/{VOLUME}/sections/one",
        json=section_payload(events=(), doc=document("A lantern crossed the harbour.")),
    )
    result = volume.get(f"/books/{BOOK}/search?q=lantern").get_json()

    assert result["total"] == 1
    assert result["results"][0]["block"] == "p1"
    assert "lantern" in result["results"][0]["snippet"]


def test_search_includes_volume_and_section_titles(volume):
    volume.post(
        f"/books/{BOOK}/volumes/{VOLUME}/sections/one",
        json=section_payload(title="Moonrise", events=(), doc=document("Quiet.")),
    )
    assert volume.get(f"/books/{BOOK}/search?q=ember+pact").get_json()["total"] == 1
    assert volume.get(f"/books/{BOOK}/search?q=moonrise").get_json()["total"] == 1


def test_search_crosses_volume_boundaries_in_reading_order(volume):
    volume.post(
        f"/books/{BOOK}/volumes/{VOLUME}/sections/one",
        json=section_payload(title="First", events=(), doc=document("shared phrase")),
    )
    volume.post(f"/books/{BOOK}/volumes/two", json={"title": "Second volume"})
    volume.post(
        f"/books/{BOOK}/volumes/two/sections/two",
        json=section_payload(title="Second", events=(), doc=document("shared phrase")),
    )

    results = volume.get(f"/books/{BOOK}/search?q=shared+phrase").get_json()["results"]
    assert [(row["volume"], row["section"]) for row in results] == [
        (VOLUME, "one"),
        ("two", "two"),
    ]


def test_search_requires_a_query_and_read_permission(volume, reader):
    assert volume.get(f"/books/{BOOK}/search").status_code == 400
    assert reader.get(f"/books/{BOOK}/search?q=quiet").status_code == 200


def test_searching_never_writes_to_the_shared_projection(section, no_writes, reader):
    """A read must stay a read.

    The projection is one document per section shared by every account. When a
    search rebuilt it, a reader holding nothing but ``read`` drove writes, and
    two searches racing from different manuscript snapshots could reinstate a
    section the writer had just deleted -- in everyone's results, not just the
    searcher's.
    """
    found = reader.get(f"{SEARCH}?q=gate")

    assert found.status_code == 200
    assert found.get_json()["total"] == 1


def test_the_projection_follows_prose_titles_and_order(volume):
    volume.post(
        f"/books/{BOOK}/volumes/{VOLUME}/sections/one",
        json=section_payload(title="Moonrise", events=(), doc=document("A lantern.")),
    )
    assert volume.get(f"{SEARCH}?q=lantern").get_json()["total"] == 1

    # Rewriting the prose retires the old text and indexes the new.
    current = volume.get(f"/books/{BOOK}/volumes/{VOLUME}/sections/one").get_json()
    volume.put(
        f"/books/{BOOK}/volumes/{VOLUME}/sections/one",
        json=section_payload(title="Moonrise", events=(), doc=document("A candle.")),
        headers={"If-Match": f'"{current["rev"]}"'},
    )
    assert volume.get(f"{SEARCH}?q=lantern").get_json()["total"] == 0
    assert volume.get(f"{SEARCH}?q=candle").get_json()["total"] == 1

    # A volume rename reaches every row that volume owns.
    volume_now = volume.get(f"/books/{BOOK}/volumes/{VOLUME}").get_json()
    volume.put(
        f"/books/{BOOK}/volumes/{VOLUME}",
        json={"title": "Salt and Ash"},
        headers={"If-Match": f'"{volume_now["rev"]}"'},
    )
    assert volume.get(f"{SEARCH}?q=salt+and+ash").get_json()["total"] == 1


def test_a_deleted_section_leaves_the_index(section):
    assert section.get(f"{SEARCH}?q=gate").get_json()["total"] == 1
    current = section.get(
        f"/books/{BOOK}/volumes/{VOLUME}/sections/the-broken-gate"
    ).get_json()
    removed = section.delete(
        f"/books/{BOOK}/volumes/{VOLUME}/sections/the-broken-gate",
        headers={"If-Match": f'"{current["rev"]}"'},
    )

    assert removed.status_code == 204
    assert section.get(f"{SEARCH}?q=gate").get_json()["total"] == 0


def test_results_page_through_the_database(volume):
    for index in range(7):
        volume.post(
            f"/books/{BOOK}/volumes/{VOLUME}/sections/s{index}",
            json=section_payload(
                title=f"Chapter {index}", events=(), doc=document("shared phrase")
            ),
        )
    first = volume.get(f"{SEARCH}?q=shared+phrase&limit=3").get_json()
    second = volume.get(f"{SEARCH}?q=shared+phrase&limit=3&offset=3").get_json()
    last = volume.get(f"{SEARCH}?q=shared+phrase&limit=3&offset=6").get_json()

    assert first["total"] == second["total"] == 7
    assert (first["next_offset"], second["next_offset"]) == (3, 6)
    assert last["next_offset"] is None
    assert len(first["results"]) == len(second["results"]) == 3
    assert [row["section"] for row in first["results"]] == ["s0", "s1", "s2"]
    assert [row["section"] for row in second["results"]] == ["s3", "s4", "s5"]


def test_search_excludes_editorial_overviews_and_private_notes(volume):
    volume.post(
        f"/books/{BOOK}/volumes/{VOLUME}/sections/one",
        json=section_payload(events=(), doc=document("Published words.")),
    )
    volume.post(
        f"/books/{BOOK}/me/items",
        json={
            "kind": "note",
            "volume": VOLUME,
            "section": "one",
            "block": "p1",
            "text": "privatephrase",
        },
    )

    assert volume.get(f"/books/{BOOK}/search?q=privatephrase").get_json()["total"] == 0
    assert volume.get(f"/books/{BOOK}/search?q=Lyra").get_json()["total"] == 0
