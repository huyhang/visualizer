"""docker/merge_category.py: folding a category into the one it reads like.

Akasha now refuses ``Characters`` beside ``characters``, but worlds made before
that may hold both. The script is run by hand against a live database, so it is
pinned here against mongomock: what moves, which links change, and above all
that nobody's access to an article changes behind their back.
"""

import importlib.util
from pathlib import Path

import pytest

from visualizer.akasha.store import DocumentStore
from visualizer.auth import AuthStore

_SCRIPT = Path(__file__).resolve().parents[2] / "docker" / "merge_category.py"

WORLD = "ember-pact"


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("merge_category", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # importing is side-effect free; main() is guarded
    return module


@pytest.fixture
def docs(mongo_client):
    """A world split the way Akasha used to allow: `characters` and `Characters`."""
    store = DocumentStore(mongo_client)
    store.create_collection(WORLD, "characters")
    store.create_collection(WORLD, "locations")
    # The twin cannot be made through the store any more -- which is the point.
    mongo_client[WORLD].create_collection("Characters")
    store.create(WORLD, "characters", "aldric", {"title": "Sir Aldric"})
    store.create(WORLD, "Characters", "lyra", {"title": "Lyra", "body": "Sails with [[aldric]] and [[Characters/mara]]."})
    store.update(WORLD, "Characters", "lyra", {"title": "Lyra Vane", "body": "Knows [[Characters/mara]]."})
    store.create(WORLD, "Characters", "mara", {"title": "Mara"})
    store.create(WORLD, "Characters", "ghost", {"title": "Gone"})
    store.delete(WORLD, "Characters", "ghost")
    return store


@pytest.fixture
def auth(mongo_client):
    return AuthStore(mongo_client)


def _merge(script, client, apply=True):
    return script.merge(client, WORLD, "Characters", "characters", apply=apply)


# -- what moves --------------------------------------------------------------


def test_every_article_moves_with_its_history_and_the_twin_goes(script, mongo_client, docs):
    report = _merge(script, mongo_client)
    assert not report.blocked, report.lines
    assert docs.list_collections(WORLD) == ["characters", "locations"]
    lyra = docs.get(WORLD, "characters", "lyra")
    assert lyra["document"]["title"] == "Lyra Vane"
    assert sorted(s["rev"] for s in docs.history(WORLD, "characters", "lyra")) == [1, 2]
    assert docs.get(WORLD, "characters", "mara")["document"] == {"title": "Mara"}


def test_a_deleted_article_moves_too_so_its_history_is_not_lost(script, mongo_client, docs):
    _merge(script, mongo_client)
    ghost = mongo_client[WORLD]["characters"].find_one({"_id": "ghost"})
    assert ghost["_deleted"] is True
    assert ghost["_history"]


def test_a_dry_run_writes_nothing(script, mongo_client, docs, auth):
    auth.add_grant("wren", WORLD, "Characters", None, ["read"], granted_by="mara")
    before = {
        name: list(mongo_client[WORLD][name].find())
        for name in mongo_client[WORLD].list_collection_names()
    }
    grants = auth.all_grants()
    report = _merge(script, mongo_client, apply=False)
    assert not report.blocked
    assert any("would move" in line for line in report.lines)
    after = {
        name: list(mongo_client[WORLD][name].find())
        for name in mongo_client[WORLD].list_collection_names()
    }
    assert after == before
    assert auth.all_grants() == grants


# -- links -------------------------------------------------------------------


def test_links_into_the_twin_are_rewritten_including_old_versions(script, mongo_client, docs):
    docs.create(WORLD, "locations", "emberport", {"title": "Emberport", "body": "Home of [[Characters/lyra|Lyra]]."})
    docs.create_collection("second-age", "notes")
    docs.create("second-age", "notes", "n1", {"body": "See [[ember-pact/Characters/mara]]; not [[Characters/x]]."})
    _merge(script, mongo_client)

    assert docs.get(WORLD, "locations", "emberport")["document"]["body"] == (
        "Home of [[characters/lyra|Lyra]]."
    )
    # Another world's two-part link names *its own* world's category: untouched.
    assert docs.get("second-age", "notes", "n1")["document"]["body"] == (
        "See [[ember-pact/characters/mara]]; not [[Characters/x]]."
    )
    lyra = mongo_client[WORLD]["characters"].find_one({"_id": "lyra"})
    assert lyra["body"] == "Knows [[characters/mara]]."
    # Old versions too, so restoring one does not bring the twin back; a bare
    # link moved with its neighbours, so it is left as written.
    first = next(s for s in docs.history(WORLD, "characters", "lyra") if s["rev"] == 1)
    assert first["document"]["body"] == "Sails with [[aldric]] and [[characters/mara]]."


@pytest.mark.parametrize(("text", "home", "expected"), [
    ("[[Characters/a]]", WORLD, "[[characters/a]]"),
    ("[[Characters/a|Ann]]", WORLD, "[[characters/a|Ann]]"),
    ("[[ember-pact/Characters/a]]", "elsewhere", "[[ember-pact/characters/a]]"),
    ("[[Characters/a]]", "elsewhere", "[[Characters/a]]"),
    ("[[other/Characters/a]]", WORLD, "[[other/Characters/a]]"),
    ("[[characters/a]] [[a]] [[cite:s1]]", WORLD, "[[characters/a]] [[a]] [[cite:s1]]"),
])
def test_relink(script, text, home, expected):
    assert script.relink(text, home, WORLD, "Characters", "characters") == expected


# -- what stops it -----------------------------------------------------------


def test_an_id_in_both_stops_the_run_before_anything_is_written(script, mongo_client, docs):
    docs.create(WORLD, "characters", "mara", {"title": "Another Mara"})
    report = _merge(script, mongo_client)
    assert report.blocked
    assert any("'mara' is in both" in line for line in report.lines)
    assert "Characters" in docs.list_collections(WORLD)


def test_a_chronos_scene_naming_the_twin_stops_the_run(script, mongo_client, docs):
    mongo_client["_chronos"]["events"].insert_one({
        "id": "meet", "book": "b",
        "location": {"database": WORLD, "collection": "locations", "id": "x"},
        "characters": [{"database": WORLD, "collection": "Characters", "id": "lyra"}],
    })
    report = _merge(script, mongo_client)
    assert report.blocked
    assert any("Chronos scene 'meet'" in line for line in report.lines)


def test_logos_prose_naming_the_twin_stops_the_run(script, mongo_client, docs):
    mention = {"type": "mention", "ref": {"database": WORLD, "collection": "Characters", "id": "lyra"}}
    mongo_client["_logos"]["draft_revisions"].insert_one({
        "book": "b", "section": "s1",
        "body": {"document": [{"type": "paragraph", "content": [mention]}]},
    })
    report = _merge(script, mongo_client)
    assert report.blocked
    assert any("Logos section 's1'" in line for line in report.lines)


def test_an_article_linked_to_a_logos_section_stops_the_run(script, mongo_client, docs):
    mongo_client["_logos"]["section_revisions"].insert_one({
        "book": "b", "section": "s2",
        "body": {"articles": [{"database": WORLD, "collection": "Characters", "id": "lyra"}],
                 "document": {"type": "doc", "content": []}},
    })
    report = _merge(script, mongo_client)
    assert report.blocked
    assert any("Logos section 's2'" in line for line in report.lines)


def test_a_run_that_stopped_half_way_finishes(script, mongo_client, docs):
    """A copy already in place, identical to what the move would write, is the
    previous run's -- not a second article under the same id."""
    lyra = mongo_client[WORLD]["Characters"].find_one({"_id": "lyra"})
    mongo_client[WORLD]["characters"].insert_one(
        script.relinked(lyra, WORLD, WORLD, "Characters", "characters")
    )
    report = _merge(script, mongo_client)
    assert not report.blocked, report.lines
    assert "Characters" not in docs.list_collections(WORLD)


# -- sharing -----------------------------------------------------------------


def _perms(auth, who, doc_id, collection="characters"):
    from visualizer.auth.authz import effective_perms

    return effective_perms(auth.grants_for(who), WORLD, collection, doc_id)


def test_an_owner_of_both_simply_loses_the_redundant_grant(script, mongo_client, docs, auth):
    for name in ("characters", "Characters"):
        auth.grant_owner("mara", WORLD, name, None, ["read", "write", "delete"])
    _merge(script, mongo_client)
    assert [(g["collection"], g["doc_id"]) for g in auth.grants_for("mara")] == [
        ("characters", None)
    ]


def test_someone_shared_only_the_twin_keeps_exactly_those_articles(script, mongo_client, docs, auth):
    auth.add_grant("wren", WORLD, "Characters", None, ["read", "write"], granted_by="mara")
    _merge(script, mongo_client)
    assert _perms(auth, "wren", "lyra") == {"read", "write"}
    assert _perms(auth, "wren", "aldric") == set()        # never shared with them
    assert all(g["collection"] == "characters" for g in auth.grants_for("wren"))


def test_a_lesser_role_on_the_twin_is_kept_on_its_articles(script, mongo_client, docs, auth):
    auth.add_grant("wren", WORLD, "Characters", None, ["read"], granted_by="mara")
    auth.add_grant("wren", WORLD, "characters", None, ["read", "write"], granted_by="mara")
    _merge(script, mongo_client)
    assert _perms(auth, "wren", "lyra") == {"read"}
    assert _perms(auth, "wren", "aldric") == {"read", "write"}


def test_a_grant_on_one_article_follows_it(script, mongo_client, docs, auth):
    auth.add_grant("wren", WORLD, "Characters", "mara", ["read"], granted_by="mara")
    _merge(script, mongo_client)
    assert _perms(auth, "wren", "mara") == {"read"}
    assert _perms(auth, "wren", "lyra") == set()


def test_access_the_merge_cannot_withhold_is_named_before_it_happens(script, mongo_client, docs, auth):
    auth.add_grant("wren", WORLD, "characters", None, ["read"], granted_by="mara")
    report = _merge(script, mongo_client, apply=False)
    assert any(line.startswith("!!") and "wren" in line for line in report.lines)
