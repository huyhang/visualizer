"""Unit tests for the pure document diff engine."""

from visualizer.akasha.diff import diff_documents, inline_diff


def _by_key(diff):
    return {f["key"]: f for f in diff["fields"]}


def test_added_removed_changed_unchanged():
    diff = diff_documents(
        {"name": "Aragorn", "race": "Man", "weapon": "sword"},
        {"name": "Elessar", "race": "Man", "realm": "Gondor"},
    )
    fields = _by_key(diff)
    assert fields["name"]["status"] == "changed"
    assert fields["race"]["status"] == "unchanged"
    assert fields["weapon"]["status"] == "removed"
    assert fields["realm"]["status"] == "added"
    assert fields["realm"]["new"] == "Gondor"
    assert fields["weapon"]["old"] == "sword"


def test_fields_sorted_by_key():
    diff = diff_documents({"b": 1, "a": 1}, {"c": 1, "a": 2})
    assert [f["key"] for f in diff["fields"]] == ["a", "b", "c"]


def test_changed_string_has_inline_diff():
    diff = diff_documents({"body": "the quick brown fox"}, {"body": "the slow brown fox"})
    field = _by_key(diff)["body"]
    assert field["status"] == "changed"
    assert "inline" in field
    # equal+delete rebuilds the old string; equal+insert rebuilds the new one.
    old = "".join(s["text"] for s in field["inline"] if s["op"] in ("equal", "delete"))
    new = "".join(s["text"] for s in field["inline"] if s["op"] in ("equal", "insert"))
    assert old == "the quick brown fox"
    assert new == "the slow brown fox"


def test_changed_array_reports_element_delta():
    diff = diff_documents({"tags": ["a", "b", "c"]}, {"tags": ["a", "c", "d"]})
    field = _by_key(diff)["tags"]
    assert field["status"] == "changed"
    assert field["array"] == {"added": ["d"], "removed": ["b"]}


def test_tombstone_diff_treats_none_body_as_empty():
    # Deleting everything: from a full doc to {} (a delete tombstone).
    diff = diff_documents({"name": "Aragorn"}, {})
    assert _by_key(diff)["name"]["status"] == "removed"


def test_inline_diff_identity():
    assert inline_diff("same", "same") == [{"op": "equal", "text": "same"}]
