"""The calendar library: a named calendar a writer keeps and attaches to books.

Three things are being pinned here, in rising order of how badly they would hurt
if they broke:

1. Ordinary CRUD through the seam and over HTTP.
2. **Per-owner identity.** Calendar names are generic, so two writers reaching
   for "imperial" must not collide -- and neither must learn of the other.
3. **Copies do not move.** Editing or deleting a library entry may never change
   what somebody's book says, because a book's dates are formatted from its own
   copy of the descriptor.
"""

import pytest
from werkzeug.security import generate_password_hash

from tests.chronos.conftest import WRITER
from visualizer.chronos.errors import CalendarNotFound, RevisionConflict

IMPERIAL = {
    "base_unit": "hour",
    "cycles": [{"name": "day", "size": 24}, {"name": "month", "size": 30}],
    "epoch_label": "AF",
}
ELVISH = {"base_unit": "bell", "cycles": [{"name": "moon", "size": 8}]}

OTHER = "brann"
OTHER_PASS = "brann-pass"


@pytest.fixture
def other_client(app, auth_store):
    """A second writer, to test that two libraries do not see each other."""
    auth_store.create_user(OTHER, generate_password_hash(OTHER_PASS), role="user")
    c = app.test_client()
    assert c.post("/login", json={"username": OTHER, "password": OTHER_PASS}).status_code == 200
    return c


def _body(name="Imperial Reckoning", descriptor=None, notes=""):
    return {"name": name, "descriptor": descriptor or IMPERIAL, "notes": notes}


def _create(client, owner, slug, **kw):
    return client.post(f"/calendars/{owner}/{slug}", json=_body(**kw))


# -- the store seam -----------------------------------------------------------


def test_store_round_trips_a_calendar(calendar_store):
    created = calendar_store.create("mara", "imperial", {"name": "Imperial"})
    assert (created["owner"], created["id"], created["rev"]) == ("mara", "imperial", 1)
    assert calendar_store.get("mara", "imperial")["name"] == "Imperial"


def test_store_refuses_a_stale_revision(calendar_store):
    calendar_store.create("mara", "imperial", {"name": "Imperial"})
    calendar_store.update("mara", "imperial", {"name": "Renamed"}, expected_rev=1)
    with pytest.raises(RevisionConflict):
        calendar_store.update("mara", "imperial", {"name": "Again"}, expected_rev=1)


def test_store_scopes_listing_to_one_owner(calendar_store):
    calendar_store.create("mara", "imperial", {"name": "Mara's"})
    calendar_store.create("brann", "imperial", {"name": "Brann's"})
    assert [c["name"] for c in calendar_store.list_owned_by("mara")] == ["Mara's"]
    assert len(calendar_store.list_all()) == 2


def test_store_reports_a_missing_calendar_as_such(calendar_store):
    with pytest.raises(CalendarNotFound):
        calendar_store.get("mara", "nope")


# -- the same slug, two writers (the collision case) --------------------------


def test_two_writers_may_each_keep_a_calendar_of_the_same_name(client, other_client):
    """The reason identity is ``(owner, slug)``. Calendar names are generic --
    "imperial", "lunar", "elvish" -- so a global namespace would let whoever
    registered the word first own it for everybody."""
    assert _create(client, WRITER, "imperial", name="Mara's Imperial").status_code == 201
    assert _create(other_client, OTHER, "imperial", name="Brann's Imperial").status_code == 201


def test_a_name_another_writer_uses_leaks_nothing(client, other_client):
    """Not merely that it is allowed: creating must not even hint that the other
    calendar exists. A refusal here would be an existence oracle over a library
    the caller cannot read."""
    _create(client, WRITER, "imperial")
    assert _create(other_client, OTHER, "imperial").status_code == 201
    mine = other_client.get("/calendars").get_json()["calendars"]
    assert [c["qualified_id"] for c in mine] == [f"{OTHER}/imperial"]


def test_a_writer_may_not_create_in_another_writers_library(client):
    assert _create(client, OTHER, "imperial").status_code == 403


def test_the_same_writer_still_cannot_reuse_their_own_slug(client):
    _create(client, WRITER, "imperial")
    assert _create(client, WRITER, "imperial").status_code == 409


# -- CRUD over HTTP -----------------------------------------------------------


def test_create_read_update_delete(client):
    created = _create(client, WRITER, "imperial", notes="After the Founding.").get_json()
    assert created["qualified_id"] == f"{WRITER}/imperial"
    assert created["descriptor"] == IMPERIAL

    fetched = client.get(f"/calendars/{WRITER}/imperial").get_json()
    assert fetched["notes"] == "After the Founding."
    assert fetched["permissions"] == {"write": True, "delete": True}

    updated = client.put(
        f"/calendars/{WRITER}/imperial",
        json=_body(name="Renamed", descriptor=ELVISH),
        headers={"If-Match": str(fetched["rev"])},
    ).get_json()
    assert (updated["name"], updated["rev"]) == ("Renamed", 2)

    assert client.delete(f"/calendars/{WRITER}/imperial").status_code == 204
    # 403 rather than 404, and deliberately: the delete swept the grants, so the
    # caller no longer holds read on that name. Answering "not found" here would
    # make the route an existence oracle over every other writer's library --
    # the same leak per-owner identity exists to avoid.
    assert client.get(f"/calendars/{WRITER}/imperial").status_code == 403


def test_a_malformed_descriptor_is_refused_at_the_write(client):
    """The library faces exactly the rule a book's own calendar faces: one that
    stored an unbuildable descriptor would hand the writer a calendar that fails
    the moment they attach it."""
    bad = client.post(
        f"/calendars/{WRITER}/broken",
        json={"name": "Broken", "descriptor": {"cycles": [{"name": "day", "size": 0}]}},
    )
    assert bad.status_code == 400
    assert bad.get_json()["code"] == "INVALID_CALENDAR"


def test_a_calendar_needs_a_descriptor(client):
    """"Plain numbers" is not a library entry -- it is a book attaching nothing."""
    assert client.post(f"/calendars/{WRITER}/empty", json={"name": "Empty"}).status_code == 400


# -- sharing ------------------------------------------------------------------


def test_sharing_puts_a_calendar_in_the_other_writers_library(client, other_client):
    _create(client, WRITER, "imperial")
    assert client.put(
        f"/calendars/{WRITER}/imperial/collaborators/{OTHER}", json={"role": "reader"}
    ).status_code == 200

    theirs = other_client.get("/calendars").get_json()["calendars"]
    assert [c["qualified_id"] for c in theirs] == [f"{WRITER}/imperial"]
    # Readable, but not theirs to change.
    assert other_client.get(f"/calendars/{WRITER}/imperial").status_code == 200
    assert other_client.put(f"/calendars/{WRITER}/imperial", json=_body()).status_code == 403


def test_a_shared_calendar_sits_beside_a_same_named_one_of_your_own(client, other_client):
    """The collision the writer actually sees. Two records, distinguished by
    owner, so the library shows "imperial" and "mara/imperial" rather than
    refusing the share or silently shadowing one."""
    _create(client, WRITER, "imperial", name="Mara's")
    _create(other_client, OTHER, "imperial", name="Brann's")
    client.put(f"/calendars/{WRITER}/imperial/collaborators/{OTHER}", json={"role": "reader"})

    theirs = other_client.get("/calendars").get_json()["calendars"]
    assert sorted(c["qualified_id"] for c in theirs) == [
        f"{OTHER}/imperial", f"{WRITER}/imperial",
    ]
    assert sorted(c["name"] for c in theirs) == ["Brann's", "Mara's"]


def test_an_unshared_calendar_is_invisible_and_unreadable(client, other_client):
    _create(client, WRITER, "imperial")
    assert other_client.get("/calendars").get_json()["calendars"] == []
    assert other_client.get(f"/calendars/{WRITER}/imperial").status_code == 403


def test_another_writers_calendar_cannot_be_reached_through_a_book_you_own(
    client, other_client
):
    """The side door, not the front one.

    Refusing ``GET /calendars/<owner>/<id>`` is not enough on its own: if a view
    parameter named a *library* calendar, anyone could point their own book at
    someone else's id and have the server render with it. Two things stop that
    here, and this pins both.

    ``?calendar=`` names an attachment *inside the book* -- a different id space
    from the library entirely -- so there is nothing to traverse. And a book's
    dates are formatted from descriptors the book itself holds: ``codec_for`` is
    pure and cannot reach the calendar store at all, so no read path exists that
    a check could be forgotten on.
    """
    _create(client, WRITER, "imperial", name="Mara's private calendar")
    other_client.post("/books/theirs", json={"title": "Their own book"})

    # Every read that formats a tick, tried with the other writer's id both bare
    # and owner-qualified. ``GET /books/<book>`` is absent on purpose: it returns
    # descriptors rather than labels, so it takes no view parameter at all.
    for path in ("/books/theirs/validate", "/books/theirs/graph",
                 "/books/theirs/events", "/books/theirs/ui/plotlines",
                 "/books/theirs/ui/ticks?tick=200&"):
        for named in ("imperial", f"{WRITER}/imperial"):
            joiner = "" if path.endswith("&") else "?"
            got = other_client.get(f"{path}{joiner}calendar={named}")
            assert got.status_code == 404, f"{path} with {named}"
            assert got.get_json()["code"] == "CALENDAR_NOT_FOUND"


def test_a_calendar_you_cannot_read_cannot_be_attached(client, other_client):
    """The other half of the side door.

    A book gets its calendar by *naming* one, and the server copies the
    descriptor in -- so naming is the only lever a caller has, and it is
    checked. Without this a writer could point their book at a calendar they
    have no business reading and have the server fetch it for them.
    """
    _create(client, WRITER, "imperial", name="Mara's private calendar")
    other_client.post("/books/theirs", json={"title": "Their own book"})
    rev = other_client.get("/books/theirs").get_json()["rev"]

    refused = other_client.put("/books/theirs", json={
        "title": "Their own book",
        "calendars": [{"id": "borrowed",
                       "source": {"owner": WRITER, "calendar": "imperial"}}],
    }, headers={"If-Match": str(rev)})
    assert refused.status_code == 403
    assert "imperial" in refused.get_json()["error"]


def test_a_book_may_not_describe_a_calendar_of_its_own(client):
    """The library is where calendars are authored. A body carrying a
    descriptor is refused rather than ignored: whoever sent it expected it to
    be used, and quietly substituting a different one is worse than saying no.
    """
    _create(client, WRITER, "imperial")
    refused = client.post("/books/inline", json={
        "title": "Inline", "calendars": [{"id": "mine", "descriptor": IMPERIAL}]})
    assert refused.status_code == 400
    assert refused.get_json()["code"] == "INVALID_BOOK"


def test_the_server_stamps_the_revision_it_actually_read(client):
    """A caller's claimed ``rev`` is never trusted -- which is what makes
    "the library has moved on" a fact rather than a guess, and why the copy
    needs no checksum stored beside it."""
    _create(client, WRITER, "imperial")
    client.put(f"/calendars/{WRITER}/imperial", json=_body(name="Second thoughts"),
               headers={"If-Match": "1"})
    saved = client.post("/books/stamped", json={
        "title": "Stamped",
        "calendars": [{"id": "imperial",
                       "source": {"owner": WRITER, "calendar": "imperial", "rev": 99}}],
    }).get_json()
    assert saved["calendars"][0]["source"]["rev"] == 2


def _resave(client, book, calendars):
    return client.put(f"/books/{book}", json={"title": "Retitled", "calendars": calendars},
                      headers={"If-Match": str(client.get(f"/books/{book}").get_json()["rev"])})


def test_an_unrelated_edit_does_not_adopt_a_library_change(client):
    """The subtle half of copying, and the one that would undo all of it.

    The server resolves descriptors from the library, so if it did that on every
    write, editing a book's *title* would quietly take whatever the library had
    become since. Sending back the revision the book already holds is how a
    caller says "keep mine" -- and it is what the form does on an ordinary save.
    """
    _create(client, WRITER, "imperial")
    _book_with_copy(client)
    client.put(f"/calendars/{WRITER}/imperial", json=_body(descriptor=ELVISH),
               headers={"If-Match": "1"})

    after = _resave(client, "ember-pact", [{
        "id": "imperial", "label": "Imperial Reckoning",
        "source": {"owner": WRITER, "calendar": "imperial", "rev": 1},
    }]).get_json()
    assert after["calendars"][0]["descriptor"] == IMPERIAL   # not ELVISH
    assert after["calendars"][0]["source"]["rev"] == 1
    assert after["title"] == "Retitled"                      # the edit landed


def test_omitting_the_revision_is_how_an_update_is_taken(client):
    """The other side of the same lever: no revision means "as it stands"."""
    _create(client, WRITER, "imperial")
    _book_with_copy(client)
    client.put(f"/calendars/{WRITER}/imperial", json=_body(descriptor=ELVISH),
               headers={"If-Match": "1"})

    after = _resave(client, "ember-pact", [{
        "id": "imperial", "label": "Imperial Reckoning",
        "source": {"owner": WRITER, "calendar": "imperial"},
    }]).get_json()
    assert after["calendars"][0]["descriptor"] == ELVISH
    assert after["calendars"][0]["source"]["rev"] == 2


def test_a_revision_the_book_never_held_falls_back_to_the_current_one(client):
    """There is nothing to keep, so "keep mine" cannot be honoured. Reading the
    library is the only answer that leaves the book with a real calendar."""
    _create(client, WRITER, "imperial")
    saved = client.post("/books/fresh", json={"title": "Fresh", "calendars": [{
        "id": "imperial", "source": {"owner": WRITER, "calendar": "imperial", "rev": 47},
    }]}).get_json()
    assert saved["calendars"][0]["descriptor"] == IMPERIAL
    assert saved["calendars"][0]["source"]["rev"] == 1


def test_only_an_owner_may_share(client, other_client):
    _create(client, WRITER, "imperial")
    client.put(f"/calendars/{WRITER}/imperial/collaborators/{OTHER}", json={"role": "reader"})
    # A reader cannot pass the grant along.
    assert other_client.put(
        f"/calendars/{WRITER}/imperial/collaborators/someone", json={"role": "reader"}
    ).status_code == 403


def test_unsharing_takes_the_calendar_back(client, other_client):
    _create(client, WRITER, "imperial")
    client.put(f"/calendars/{WRITER}/imperial/collaborators/{OTHER}", json={"role": "reader"})
    assert client.delete(
        f"/calendars/{WRITER}/imperial/collaborators/{OTHER}"
    ).status_code == 204
    assert other_client.get("/calendars").get_json()["calendars"] == []


def test_deleting_a_calendar_sweeps_its_grants(client, other_client):
    """Ids may be recreated, so a grant left behind is a grant on a *name*: the
    next calendar under that slug would arrive silently pre-shared."""
    _create(client, WRITER, "imperial")
    client.put(f"/calendars/{WRITER}/imperial/collaborators/{OTHER}", json={"role": "reader"})
    client.delete(f"/calendars/{WRITER}/imperial")
    _create(client, WRITER, "imperial", name="A different calendar, same slug")
    assert other_client.get("/calendars").get_json()["calendars"] == []


# -- a library entry is never on a book's read path ---------------------------


def _book_with_copy(client):
    """A book that attached the library's imperial calendar.

    It names the calendar; the server copies the descriptor in and stamps the
    revision it actually read. The book never states the content itself.
    """
    return client.post("/books/ember-pact", json={
        "title": "The Ember Pact",
        "calendars": [{
            "id": "imperial", "label": "Imperial Reckoning",
            "source": {"owner": WRITER, "calendar": "imperial"},
        }],
    })


def test_editing_the_library_does_not_relabel_a_book(client):
    """The load-bearing consequence of copying. One writer's edit must never
    silently re-date another writer's story."""
    _create(client, WRITER, "imperial")
    _book_with_copy(client)
    before = client.get("/books/ember-pact").get_json()["calendars"][0]["descriptor"]

    client.put(f"/calendars/{WRITER}/imperial", json=_body(descriptor=ELVISH))

    after = client.get("/books/ember-pact").get_json()["calendars"][0]["descriptor"]
    assert after == before == IMPERIAL


def test_deleting_the_library_entry_leaves_the_book_readable(client):
    """Provenance goes dangling; the book does not. Same posture as a deleted
    Akasha article -- report it, do not break the story."""
    _create(client, WRITER, "imperial")
    _book_with_copy(client)
    client.delete(f"/calendars/{WRITER}/imperial")

    book = client.get("/books/ember-pact").get_json()
    assert book["calendars"][0]["descriptor"] == IMPERIAL
    # The pointer survives, so a UI can say *why* no update is being offered.
    assert book["calendars"][0]["source"]["calendar"] == "imperial"


def test_a_book_reader_needs_no_grant_on_the_library_entry(client, other_client, auth_store):
    """A book you can read, you can read the dates of. The labels are the book's
    own bytes -- the copy is what makes that true without a second grant."""
    _create(client, WRITER, "imperial")
    _book_with_copy(client)
    client.put("/books/ember-pact/collaborators/" + OTHER, json={"role": "reader"})

    book = other_client.get("/books/ember-pact").get_json()
    assert book["calendars"][0]["descriptor"] == IMPERIAL
    # ...while the library entry itself stays private.
    assert other_client.get(f"/calendars/{WRITER}/imperial").status_code == 403
