"""The fourth whole-book check: scenes pointing at articles that are gone.

Akasha's deletes are soft and it holds no back-reference to Chronos, so nothing
warns a writer that a timeline names the article they are removing. Chronos
refuses an unknown reference on *write*, which means a dangling one can only
appear underneath a finished scene -- and until this check existed, the only
symptom was that editing the scene months later failed for no visible reason.

The pure half is tested directly; the rest goes through the real Akasha store so
that "delete an article, look at the book" is exercised end to end.
"""

import pytest

from tests.chronos.conftest import ref
from visualizer.chronos.calendar import IdentityCodec
from visualizer.chronos.entity_gate import InProcessEntityGate
from visualizer.chronos.models import Event
from visualizer.chronos.plotline_health import (
    conflict_count,
    conflict_counts,
    findings_for_path,
)
from visualizer.chronos.reports import (
    BookReport,
    build_report,
    dangling_references,
    entity_roles,
)


def scene(event_id, location="emberport", characters=(), items=()):
    return Event(
        id=event_id,
        title=event_id,
        location=ref(location, collection="locations"),
        start_tick=0,
        end_tick=1,
        characters=[ref(c) for c in characters],
        items=[ref(i, collection="items") for i in items],
    )


# -- pure --------------------------------------------------------------------


def test_roles_label_every_reference_a_scene_makes():
    roles = entity_roles(scene("s", characters=["aldric"], items=["seal"]))
    assert [role for role, _ in roles] == ["location", "character", "item"]


def test_nothing_missing_means_nothing_to_report():
    assert dangling_references([scene("s", characters=["aldric"])], []) == []


def test_a_deleted_article_is_reported_against_the_scene_that_names_it():
    events = [scene("a", characters=["aldric"]), scene("b", characters=["lyra"])]
    found = dangling_references(events, [ref("aldric")])
    assert [(m.event, m.role, m.ref.id) for m in found] == [("a", "character", "aldric")]


def test_a_missing_location_is_reported_as_a_location():
    found = dangling_references([scene("a", location="ruins")], [ref("ruins", "locations")])
    assert [(m.event, m.role) for m in found] == [("a", "location")]


def test_every_scene_naming_it_is_reported():
    """One deletion can break several scenes, and each has to be found."""
    events = [scene("b", characters=["aldric"]), scene("a", characters=["aldric"])]
    found = dangling_references(events, [ref("aldric")])
    assert [m.event for m in found] == ["a", "b"]  # ordered, so the report is stable


def test_a_dangling_reference_makes_the_book_conflicted():
    events = [scene("a", characters=["aldric"])]
    assert build_report(events, [], terminus=None).ok is True
    report = build_report(events, [], terminus=None, missing_refs=[ref("aldric")])
    assert report.ok is False
    assert BookReport().ok is True


# -- the per-scene finding ---------------------------------------------------


def test_the_scene_gets_a_finding_naming_what_is_gone():
    events = {"a": scene("a", characters=["aldric", "lyra"])}
    findings = findings_for_path(
        ["a"], events, {"p": ["a"]}, IdentityCodec(),
        missing_refs=[ref("aldric")],
    )
    [finding] = [f for f in findings["a"] if f.code == "MISSING_ENTITY"]
    assert finding.severity == "conflict"
    assert "'aldric'" in finding.message      # quoted, so a client can swap the title in
    assert "'lyra'" not in finding.message    # lyra is fine
    assert finding.refs == (ref("aldric"),)


def test_several_missing_refs_on_one_scene_are_one_finding():
    events = {"a": scene("a", characters=["aldric", "lyra"])}
    findings = findings_for_path(
        ["a"], events, {"p": ["a"]}, IdentityCodec(),
        missing_refs=[ref("aldric"), ref("lyra")],
    )
    missing = [f for f in findings["a"] if f.code == "MISSING_ENTITY"]
    assert len(missing) == 1
    assert "are named here" in missing[0].message


def test_the_thread_count_agrees_with_the_findings():
    """The table counts the whole book at once; it must reach the same answer."""
    events = {"a": scene("a", characters=["aldric"]), "b": scene("b")}
    paths = {"p": ["a", "b"]}
    findings = findings_for_path(
        paths["p"], events, paths, IdentityCodec(), missing_refs=[ref("aldric")]
    )
    assert conflict_counts(paths, events, [ref("aldric")]) == {
        "p": conflict_count(findings)
    }


# -- end to end, against the real Akasha store -------------------------------


@pytest.fixture
def linked_app(story_store, doc_store, auth_store, calendar_store):
    """A Chronos app whose entity checks hit a real Akasha store, as in production."""
    from visualizer.chronos.app import create_app

    application = create_app(
        story_store, InProcessEntityGate(doc_store), auth_store,
        calendar_store=calendar_store, secret_key="test-secret",
    )
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)
    return application


@pytest.fixture
def linked_client(linked_app, doc_store):
    from tests.chronos.conftest import WRITER, WRITER_PASS

    doc_store.create_collection("ember-pact", "characters")
    doc_store.create_collection("ember-pact", "locations")
    doc_store.create("ember-pact", "characters", "aldric", {"title": "Sir Aldric"})
    doc_store.create("ember-pact", "locations", "emberport", {"title": "Emberport"})

    c = linked_app.test_client()
    assert c.post("/login", json={"username": WRITER, "password": WRITER_PASS}).status_code == 200
    c.post("/books/ember-pact", json={"title": "The Ember Pact"})
    c.post("/books/ember-pact/events/the-meeting", json={
        "title": "The Meeting",
        "location": {"database": "ember-pact", "collection": "locations", "id": "emberport"},
        "characters": [{"database": "ember-pact", "collection": "characters", "id": "aldric"}],
        "start_tick": 0, "end_tick": 10,
    })
    c.post("/books/ember-pact/plotlines/main", json={
        "goals": ["reach the pact"], "events": ["the-meeting"],
    })
    # Without a terminus every thread fails convergence, and the book would be
    # conflicted before this check had anything to say.
    c.post("/books/ember-pact/terminus/the-meeting")
    return c


def test_a_healthy_book_reports_nothing_missing(linked_client):
    report = linked_client.get("/books/ember-pact/validate").get_json()
    assert report["missing_entities"] == []
    assert linked_client.get("/books/ember-pact").get_json()["status"] == "consistent"


def test_deleting_the_article_shows_up_in_the_report(linked_client, doc_store):
    doc_store.delete("ember-pact", "characters", "aldric", expected_rev=1)

    report = linked_client.get("/books/ember-pact/validate").get_json()
    assert report["missing_entities"] == [{
        "event": "the-meeting",
        "role": "character",
        "ref": {"database": "ember-pact", "collection": "characters", "id": "aldric"},
    }]
    assert report["status"] == "conflicted"


def test_the_book_and_the_thread_both_show_it(linked_client, doc_store):
    """A red book with every thread reporting "no problems" would be worse than
    saying nothing: the writer needs to be able to find it."""
    doc_store.delete("ember-pact", "characters", "aldric", expected_rev=1)

    assert linked_client.get("/books/ember-pact").get_json()["status"] == "conflicted"
    rows = linked_client.get("/books/ember-pact/ui/plotlines").get_json()["plotlines"]
    assert [r["conflicts"] for r in rows] == [1]

    plotline = linked_client.get("/books/ember-pact/plotlines/main?expand=events").get_json()
    codes = [
        f["code"]
        for scene_ in plotline["effective_events"]
        for f in scene_.get("findings", [])
    ]
    assert "MISSING_ENTITY" in codes


def test_restoring_the_article_clears_the_report(linked_client, doc_store):
    """Akasha deletes are soft, so this is recoverable — and the report has to
    agree once it has been."""
    doc_store.delete("ember-pact", "characters", "aldric", expected_rev=1)
    assert linked_client.get("/books/ember-pact/validate").get_json()["missing_entities"]

    doc_store.create("ember-pact", "characters", "aldric", {"title": "Sir Aldric"})
    report = linked_client.get("/books/ember-pact/validate").get_json()
    assert report["missing_entities"] == []
    assert report["status"] == "consistent"


def test_one_lookup_per_distinct_article_not_per_scene(linked_client, doc_store):
    """The check runs on every book read, so it must not scale with scene count."""
    for n in range(5):
        linked_client.post(f"/books/ember-pact/events/scene-{n}", json={
            "title": f"Scene {n}",
            "location": {"database": "ember-pact", "collection": "locations", "id": "emberport"},
            "characters": [{"database": "ember-pact", "collection": "characters", "id": "aldric"}],
            "start_tick": 100 + n * 10, "end_tick": 105 + n * 10,
        })

    reads = {"n": 0}
    original = doc_store.get

    def counting_get(*args, **kwargs):
        reads["n"] += 1
        return original(*args, **kwargs)

    doc_store.get = counting_get
    try:
        linked_client.get("/books/ember-pact/validate")
    finally:
        doc_store.get = original

    # Six scenes naming the same two articles: two lookups, not twelve.
    assert reads["n"] == 2
