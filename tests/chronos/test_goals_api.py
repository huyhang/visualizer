"""Goals end to end, through the real app (mongomock + fake gate).

The rules themselves are pinned in ``test_goal_rules``; this covers what only
the service and the routes can answer: what is refused and with which code, what
a delete does to the records pointing at it, and how a goal reads once the rest
of the book is around it.
"""

import pytest

from tests.chronos.conftest import ref

BOOK = "ember-pact"


@pytest.fixture
def seeded(app, fake_gate):
    fake_gate.add(ref("aldric"))
    fake_gate.add(ref("highkeep", "locations"))
    return app


def _scene(client, eid, start=0, end=10, title=None):
    body = {
        "location": ref("highkeep", "locations").to_dict(),
        "characters": [ref("aldric").to_dict()],
        "start_tick": start,
        "end_tick": end,
    }
    if title:
        body["title"] = title
    return client.post(f"/books/{BOOK}/events/{eid}", json=body)


def _goal(client, gid, **body):
    return client.post(f"/books/{BOOK}/goals/{gid}", json=body)


def _thread(client, pid, events, goals=()):
    return client.post(
        f"/books/{BOOK}/plotlines/{pid}",
        json={"events": list(events), "goals": list(goals)},
    )


@pytest.fixture
def book(seeded, client):
    client.post(f"/books/{BOOK}", json={"title": "The Ember Pact"})
    _scene(client, "the-claim", 0, 10, title="The Claim")
    _scene(client, "the-coronation", 40, 50, title="The Coronation")
    return client


# -- the record ---------------------------------------------------------------


def test_create_and_read_a_goal(book):
    resp = _goal(book, "crown", title="Aldric is crowned", description="In public.")
    assert resp.status_code == 201
    assert resp.headers["ETag"] == '"1"'
    body = resp.get_json()
    assert body["kind"] == "goal" and body["id"] == "crown" and body["book"] == BOOK
    assert body["name"] == "Aldric is crowned"
    assert body["status"]["state"] == "open"

    got = book.get(f"/books/{BOOK}/goals/crown").get_json()
    assert got["description"] == "In public."
    assert got["_links"]["self"] == f"/books/{BOOK}/goals/crown"


def test_an_untitled_goal_shows_its_id(book):
    assert _goal(book, "crown").get_json()["name"] == "crown"


def test_a_goal_is_replaced_whole_and_bumps_its_revision(book):
    rev = _goal(book, "crown", title="First").get_json()["rev"]
    resp = book.put(
        f"/books/{BOOK}/goals/crown", json={"title": "Second"}, headers={"If-Match": str(rev)}
    )
    assert resp.status_code == 200
    assert resp.get_json()["title"] == "Second" and resp.get_json()["rev"] == 2


def test_a_stale_edit_is_refused(book):
    _goal(book, "crown", title="First")
    book.put(f"/books/{BOOK}/goals/crown", json={"title": "Second"})
    stale = book.put(
        f"/books/{BOOK}/goals/crown", json={"title": "Third"}, headers={"If-Match": "1"}
    )
    assert stale.status_code == 409 and stale.get_json()["code"] == "REVISION_CONFLICT"


def test_goals_are_listed_whole_for_the_diagram(book):
    _goal(book, "claim")
    _goal(book, "crown", depends_on=["claim"])
    body = book.get(f"/books/{BOOK}/goals").get_json()
    assert [g["id"] for g in body["goals"]] == ["claim", "crown"]
    # Each read against the others: depth for the layout, the reverse edge that
    # nothing stores, and the verdict.
    assert [g["depth"] for g in body["goals"]] == [0, 1]
    # A name and whether it is met -- and no date. `required_by` is drawn as a
    # bare chip, so dating every edge in the graph would put a formatted scene
    # on the wire that no client reads (see `goal_ref` vs `dated_goal_ref`).
    assert body["goals"][0]["required_by"] == [
        {"id": "crown", "title": "crown", "achieved": False, "missing": False}
    ]


# -- what a write refuses -----------------------------------------------------


def test_a_dependency_that_is_not_in_the_book_is_refused(book):
    resp = _goal(book, "crown", depends_on=["ghost"])
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "INVALID_GOAL"
    assert resp.get_json()["evidence"]["unknown_goals"] == ["ghost"]


def test_a_goal_cannot_depend_on_itself(book):
    resp = _goal(book, "crown", depends_on=["crown"])
    assert resp.status_code == 400 and resp.get_json()["code"] == "INVALID_GOAL"


def test_a_dependency_that_would_loop_is_refused(book):
    _goal(book, "claim")
    _goal(book, "crown", depends_on=["claim"])
    resp = book.put(f"/books/{BOOK}/goals/claim", json={"depends_on": ["crown"]})
    assert resp.status_code == 422
    assert resp.get_json()["code"] == "GOAL_CYCLE"
    assert resp.get_json()["evidence"]["cycle"] == ["claim", "crown", "claim"]


def test_the_same_dependency_twice_is_refused_rather_than_collapsed(book):
    _goal(book, "claim")
    resp = _goal(book, "crown", depends_on=["claim", "claim"])
    assert resp.status_code == 400 and resp.get_json()["code"] == "INVALID_GOAL"


def test_an_achieving_scene_must_be_in_the_book(book):
    resp = _goal(book, "crown", achieved_at="not-a-scene")
    assert resp.status_code == 400
    assert resp.get_json()["evidence"]["achieved_at"] == "not-a-scene"


def test_an_achieved_goal_names_its_scene_and_dates_it(book):
    body = _goal(book, "crown", achieved_at="the-coronation").get_json()
    assert body["achieved_scene"]["title"] == "The Coronation"
    assert body["achieved_scene"]["when"] == "40 → 50"
    assert body["_links"]["achieved_at"] == f"/books/{BOOK}/events/the-coronation"


# -- deleting -----------------------------------------------------------------


def test_a_goal_a_thread_serves_is_not_deleted_out_from_under_it(book):
    _goal(book, "crown")
    _thread(book, "road", ["the-claim"], goals=["crown"])
    resp = book.delete(f"/books/{BOOK}/goals/crown")
    assert resp.status_code == 409
    assert resp.get_json()["code"] == "GOAL_IN_USE"
    assert resp.get_json()["evidence"]["plotlines"] == ["road"]


def test_a_goal_another_goal_rests_on_is_not_deleted_out_from_under_it(book):
    _goal(book, "claim")
    _goal(book, "crown", depends_on=["claim"])
    resp = book.delete(f"/books/{BOOK}/goals/claim")
    assert resp.status_code == 409
    assert resp.get_json()["evidence"]["goals"] == ["crown"]


def test_detach_unpicks_every_reference_then_deletes(book):
    _goal(book, "claim")
    _goal(book, "crown", depends_on=["claim"])
    _thread(book, "road", ["the-claim"], goals=["claim", "crown"])

    assert book.delete(f"/books/{BOOK}/goals/claim?detach=true").status_code == 204

    assert book.get(f"/books/{BOOK}/goals/claim").status_code == 404
    assert book.get(f"/books/{BOOK}/goals/crown").get_json()["depends_on"] == []
    assert book.get(f"/books/{BOOK}/plotlines/road").get_json()["goals"] == ["crown"]


def test_a_goal_nothing_points_at_is_simply_deleted(book):
    _goal(book, "crown")
    assert book.delete(f"/books/{BOOK}/goals/crown").status_code == 204


def test_deleting_the_book_takes_its_goals_with_it(book, story_store):
    _goal(book, "crown")
    assert book.delete(f"/books/{BOOK}").status_code == 204
    assert story_store.list_goals(BOOK) == []


# -- the scene a goal lands on ------------------------------------------------


def test_a_scene_that_achieves_a_goal_is_not_deleted_without_a_word(book):
    _goal(book, "crown", achieved_at="the-coronation")
    resp = book.delete(f"/books/{BOOK}/events/the-coronation")
    assert resp.status_code == 409
    assert resp.get_json()["code"] == "EVENT_IN_USE"
    assert resp.get_json()["evidence"]["goals"] == ["crown"]


def test_detaching_a_scene_leaves_the_goal_waiting_for_another_one(book):
    _goal(book, "crown", achieved_at="the-coronation")
    assert book.delete(f"/books/{BOOK}/events/the-coronation?detach=true").status_code == 204
    body = book.get(f"/books/{BOOK}/goals/crown").get_json()
    assert body["achieved_at"] is None and body["status"]["state"] == "open"


# -- threads and their goals --------------------------------------------------


def test_a_thread_may_only_serve_goals_the_book_has(book):
    resp = _thread(book, "road", ["the-claim"], goals=["Deliver the Seal"])
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "INVALID_PLOTLINE"
    assert resp.get_json()["evidence"]["unknown_goals"] == ["Deliver the Seal"]


def test_a_thread_may_serve_no_goal_at_all(book):
    """A thread drafted before the writer has decided what it is for. The book
    report says so; the write does not stand in the way."""
    assert _thread(book, "road", ["the-claim"]).status_code == 201


def test_a_thread_names_the_goals_it_serves(book):
    _goal(book, "crown", title="Aldric is crowned")
    _thread(book, "road", ["the-claim"], goals=["crown"])
    body = book.get(f"/books/{BOOK}/plotlines/road").get_json()
    assert body["goals"] == ["crown"]
    assert body["goal_refs"][0]["title"] == "Aldric is crowned"


def test_a_goal_chip_on_a_thread_says_where_it_lands(book):
    """So the thread's timeline can put the goal on the scene that delivers it
    without fetching the book's goals a second time to find out where that is."""
    _goal(book, "crown", title="Aldric is crowned", achieved_at="the-coronation")
    _thread(book, "road", ["the-claim", "the-coronation"], goals=["crown"])
    ref = book.get(f"/books/{BOOK}/plotlines/road").get_json()["goal_refs"][0]
    assert ref["achieved_at"] == "the-coronation"
    assert ref["achieved_scene"] == {
        "id": "the-coronation", "title": "The Coronation", "when": "40 → 50",
    }


def test_a_goal_with_no_scene_says_so_on_the_chip_rather_than_going_quiet(book):
    """The timeline needs to tell "lands here" from "lands nowhere yet" -- the
    second is what the strip above the rail is for."""
    _goal(book, "crown")
    _thread(book, "road", ["the-claim"], goals=["crown"])
    ref = book.get(f"/books/{BOOK}/plotlines/road").get_json()["goal_refs"][0]
    assert ref["achieved_at"] is None and ref["achieved_scene"] is None


def test_the_lean_plotline_shape_stays_lean(book):
    """Only `?expand=events` carries the scene summaries a goal badge rides on.
    A field added to the expanded shape must not leak into the lean one, which
    is what the table and the editor read -- they want ids, not a book."""
    _goal(book, "crown", achieved_at="the-coronation")
    _thread(book, "road", ["the-claim", "the-coronation"], goals=["crown"])
    lean = book.get(f"/books/{BOOK}/plotlines/road").get_json()
    assert lean["effective_events"] == ["the-claim", "the-coronation"]
    assert all(isinstance(e, str) for e in lean["effective_events"])


def test_the_graph_carries_the_books_goals_and_which_thread_pursues_each(book):
    """The story map marks a goal on the scene it lands on, and lists the ones
    that land on no shown scene. Both come from one list read two ways."""
    _goal(book, "crown", title="Aldric is crowned", achieved_at="the-coronation")
    _goal(book, "peace", title="The Pact holds")  # no scene yet
    _thread(book, "road", ["the-claim", "the-coronation"], goals=["crown", "peace"])
    graph = book.get(f"/books/{BOOK}/graph").get_json()

    assert [g["id"] for g in graph["goals"]] == ["crown", "peace"]
    landed = {g["id"]: g["achieved_at"] for g in graph["goals"]}
    assert landed == {"crown": "the-coronation", "peace": None}
    assert graph["plotlines"][0]["goals"] == ["crown", "peace"]


def test_the_editor_preview_faces_the_same_goal_rule_as_the_save(book):
    resp = book.post(
        f"/books/{BOOK}/ui/plotline-preview",
        json={"events": ["the-claim"], "goals": ["ghost"]},
    )
    assert resp.status_code == 400 and resp.get_json()["code"] == "INVALID_PLOTLINE"


def test_a_thread_is_findable_by_the_name_of_the_goal_it_serves(book):
    _goal(book, "crown", title="Aldric is crowned")
    _thread(book, "road", ["the-claim"], goals=["crown"])
    rows = book.get(f"/books/{BOOK}/ui/plotlines?filter=crowned").get_json()["plotlines"]
    assert [r["id"] for r in rows] == ["road"]
    assert rows[0]["goals"] == [
        {
            "id": "crown", "title": "Aldric is crowned", "achieved": False,
            "missing": False, "achieved_at": None, "achieved_scene": None,
        }
    ]


# -- the book's verdict -------------------------------------------------------


def test_a_goal_the_story_never_reaches_makes_the_book_conflicted(book):
    """And the card and the report must say the same thing -- the invariant the
    scene rules already hold, now with a fourth source of faults."""
    _goal(book, "crown", achieved_at="the-coronation")
    _thread(book, "road", ["the-claim"], goals=["crown"])
    book.post(f"/books/{BOOK}/terminus/the-claim")

    assert book.get(f"/books/{BOOK}").get_json()["status"] == "conflicted"
    report = book.get(f"/books/{BOOK}/ui/issues").get_json()
    assert report["status"] == "conflicted"
    codes = [i["code"] for g in report["problems"] for i in g["issues"]]
    assert "GOAL_NOT_REACHED" in codes


def test_notes_about_goals_leave_the_book_consistent(book):
    """A goal nobody pursues yet is a draft state. A book in progress is full of
    them, and a report that called them faults would be ignored."""
    _goal(book, "crown")
    _thread(book, "road", ["the-claim"])
    book.post(f"/books/{BOOK}/terminus/the-claim")

    assert book.get(f"/books/{BOOK}").get_json()["status"] == "consistent"
    report = book.get(f"/books/{BOOK}/ui/issues").get_json()
    assert report["status"] == "consistent"
    assert "GOAL_UNSERVED" in [i["code"] for g in report["notes"] for i in g["issues"]]


def test_the_report_names_the_goal_a_message_is_about(book):
    _goal(book, "crown", title="Aldric is crowned")
    issue = next(
        i
        for g in book.get(f"/books/{BOOK}/ui/issues").get_json()["notes"]
        for i in g["issues"]
        if i["code"] == "GOAL_UNSERVED"
    )
    assert issue["goal"] == {"id": "crown", "title": "Aldric is crowned"}


def test_validate_reports_goals_for_a_machine_too(book):
    _goal(book, "crown")
    body = book.get(f"/books/{BOOK}/validate").get_json()
    assert {f["code"] for f in body["goals"]} == {"GOAL_UNSERVED", "GOAL_UNACHIEVED"}
    assert all(f["goal"] == "crown" for f in body["goals"])


# -- authorization ------------------------------------------------------------


def test_goals_need_read_permission_on_the_book(book, app):
    """Goals carry no grants of their own: the book's are the whole answer."""
    from tests.chronos.conftest import ADMIN_PASS, ADMIN_USER, _login

    stranger = app.test_client()
    _login(stranger, ADMIN_USER, ADMIN_PASS)  # an admin holds no book grants
    assert stranger.get(f"/books/{BOOK}/goals").status_code == 403
    assert stranger.get(f"/books/{BOOK}/goals/crown").status_code == 403


def test_writing_a_goal_needs_write_permission(book, app, auth_store):
    from tests.chronos.conftest import ADMIN_PASS, ADMIN_USER, _login
    from visualizer.chronos.app import BOOK_RESOURCE

    _goal(book, "crown")
    auth_store.grant_owner(ADMIN_USER, BOOK, None, None, ["read"], resource_type=BOOK_RESOURCE)
    reader = app.test_client()
    _login(reader, ADMIN_USER, ADMIN_PASS)

    assert reader.get(f"/books/{BOOK}/goals/crown").status_code == 200
    assert reader.post(f"/books/{BOOK}/goals/other", json={}).status_code == 403
    assert reader.put(f"/books/{BOOK}/goals/crown", json={"title": "x"}).status_code == 403
    assert reader.delete(f"/books/{BOOK}/goals/crown").status_code == 403


@pytest.mark.parametrize("role,may_write,may_delete", [
    ("reader", False, False),
    ("editor", True, False),
    ("owner", True, True),
])
def test_sharing_a_book_shares_its_goals(book, app, role, may_write, may_delete):
    """Goals come with the book, at whatever role the invite carried.

    Nothing here is goal-specific -- that is the point of them being book-scoped
    with no grants of their own. Pinned end to end through the real sharing
    route anyway, because "it follows from the design" is exactly the kind of
    claim that stops being true when someone adds a resource kind.
    """
    from tests.chronos.conftest import ADMIN_PASS, ADMIN_USER, _login

    _goal(book, "crown", title="Aldric is crowned")
    invite = book.put(f"/books/{BOOK}/collaborators/{ADMIN_USER}", json={"role": role})
    assert invite.status_code == 200 and invite.get_json()["role"] == role

    mate = app.test_client()
    _login(mate, ADMIN_USER, ADMIN_PASS)

    listed = mate.get(f"/books/{BOOK}/goals")
    assert listed.status_code == 200
    assert [g["id"] for g in listed.get_json()["goals"]] == ["crown"]
    assert mate.get(f"/books/{BOOK}/goals/crown").status_code == 200

    wrote = mate.post(f"/books/{BOOK}/goals/second", json={"title": "Another"})
    assert wrote.status_code == (201 if may_write else 403)
    removed = mate.delete(f"/books/{BOOK}/goals/crown")
    assert removed.status_code == (204 if may_delete else 403)


def test_unsharing_a_book_takes_its_goals_back(book, app):
    from tests.chronos.conftest import ADMIN_PASS, ADMIN_USER, _login

    _goal(book, "crown")
    book.put(f"/books/{BOOK}/collaborators/{ADMIN_USER}", json={"role": "editor"})
    mate = app.test_client()
    _login(mate, ADMIN_USER, ADMIN_PASS)
    assert mate.get(f"/books/{BOOK}/goals").status_code == 200

    assert book.delete(f"/books/{BOOK}/collaborators/{ADMIN_USER}").status_code == 204
    assert mate.get(f"/books/{BOOK}/goals").status_code == 403


def test_goals_need_a_session(seeded):
    resp = seeded.test_client().get(f"/books/{BOOK}/goals")
    assert resp.status_code in (302, 401)
