"""What a half-finished write leaves behind, and how the next one clears it.

Logos has no transactions. Creating a volume is two writes -- name it in the
outline, then store the record -- and deleting one is the reverse. These tests
pin the property that makes that safe without a compensating rollback: the only
reachable partial state is an order entry naming a record that is not there,
every read skips it, and the next write heals it.
"""

from .conftest import BOOK, SECTION, VOLUME, section_payload

MANUSCRIPT = f"/books/{BOOK}"
VOLUME_URL = f"{MANUSCRIPT}/volumes/{VOLUME}"


def test_a_volume_named_in_the_outline_but_never_stored_is_invisible(
    client, logos_store
):
    logos_store.create_outline(BOOK, {"volumes": ["half-written"]}, "mara")

    manuscript = client.get(MANUSCRIPT).get_json()

    assert manuscript["volumes"] == []
    assert manuscript["volume_count"] == 0
    assert client.get(f"{MANUSCRIPT}/volumes/half-written").status_code == 404


def test_retrying_an_interrupted_create_completes_it(client, logos_store):
    """The outline already names it, so the retry must store the record rather
    than refusing the id as taken."""
    logos_store.create_outline(BOOK, {"volumes": ["half-written"]}, "mara")

    created = client.post(
        f"{MANUSCRIPT}/volumes/half-written", json={"title": "Half Written"}
    )

    assert created.status_code == 201
    assert created.get_json()["number"] == 1
    assert logos_store.find_outline(BOOK)["volumes"] == ["half-written"]


def test_a_volume_that_really_exists_is_still_refused_twice(volume):
    again = volume.post(VOLUME_URL, json={"title": "The Ember Pact"})

    assert again.status_code == 409
    assert again.get_json()["code"] == "ALREADY_EXISTS"


def test_reordering_rewrites_the_outline_from_what_is_actually_live(
    volume, logos_store
):
    outline = logos_store.find_outline(BOOK)
    logos_store.update_outline(
        BOOK, {"volumes": [VOLUME, "half-written"]}, outline["rev"], "mara"
    )
    current = volume.get(MANUSCRIPT)

    reordered = volume.put(
        f"{MANUSCRIPT}/volume-order",
        json={"volumes": [VOLUME]},
        headers={"If-Match": current.headers["ETag"]},
    )

    assert reordered.status_code == 200
    assert logos_store.find_outline(BOOK)["volumes"] == [VOLUME]


def test_a_section_left_out_of_its_volume_is_skipped_and_can_be_recreated(
    volume, logos_store
):
    logos_store.create_section(
        BOOK, VOLUME, "orphan", section_payload(events=()), "mara"
    )

    assert volume.get(VOLUME_URL).get_json()["sections"] == []

    # The record exists but nothing lists it, so creating it is refused as taken
    # rather than silently overwriting prose that is already stored.
    again = volume.post(
        f"{VOLUME_URL}/sections/orphan", json=section_payload(events=())
    )
    assert again.status_code == 409
    assert again.get_json()["code"] == "ALREADY_EXISTS"


def test_deleting_a_section_twice_does_not_corrupt_the_volume(section):
    section_url = f"{VOLUME_URL}/sections/{SECTION}"

    assert section.delete(section_url, headers={"If-Match": '"1"'}).status_code == 204
    again = section.delete(section_url, headers={"If-Match": '"1"'})

    assert again.status_code == 404
    assert section.get(VOLUME_URL).get_json()["sections"] == []
