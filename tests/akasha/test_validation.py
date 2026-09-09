"""Unit tests for the pure validation helpers (no DB, no Flask)."""

import pytest

from visualizer.akasha.errors import InvalidDocument, InvalidSearch
from visualizer.akasha.validation import validate_document, validate_search_terms
from visualizer.auth import InvalidEmail, validate_email


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"a": 1},
        {"name": "Aragorn", "age": 87, "king": True, "note": None, "hp": 3.5},
        {"tags": ["a", "b", "c"]},  # a flat array of scalars is allowed
        {"tags": []},
    ],
)
def test_validate_document_accepts_flat_dicts(payload):
    assert validate_document(payload) is payload


@pytest.mark.parametrize("payload", [None, [], [1, 2], "text", 5, 3.14, True])
def test_validate_document_rejects_non_dicts(payload):
    with pytest.raises(InvalidDocument):
        validate_document(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"nested": {"x": 1}},  # nested object
        {"matrix": [[1, 2], [3, 4]]},  # array of arrays
        {"people": [{"name": "Frodo"}]},  # array of objects
    ],
)
def test_validate_document_rejects_nested_values(payload):
    with pytest.raises(InvalidDocument):
        validate_document(payload)


def test_validate_document_accepts_consistent_article_images():
    media_id = "a" * 32
    payload = {
        "body": f"{{{{image:{media_id}|right|40|Inline caption}}}}",
        "gallery": [f"{media_id}|Gallery caption|with a separator"],
        "profile_image": media_id,
    }
    assert validate_document(payload) is payload


@pytest.mark.parametrize(
    "payload",
    [
        # Field names belong to the writer. An article that used these two long
        # before images existed must keep saving; the reader claims them only
        # when they parse as image references.
        {"gallery": ["Denon wing", "Sully wing", "Richelieu wing"]},
        {"gallery": "the east hall"},
        {"profile_image": "commissioned 1387 by the guild"},
        # Internally inconsistent, but the reader degrades rather than breaking:
        # an unattached body image still renders, an unattached portrait is
        # simply not shown.
        {"gallery": [f"{'a' * 32}|one", f"{'a' * 32}|two"]},
        {"profile_image": "a" * 32, "gallery": []},
        {"body": f"{{{{image:{'a' * 32}|center|50|Unattached}}}}"},
    ],
)
def test_validate_document_does_not_police_the_image_fields(payload):
    assert validate_document(payload) is payload


@pytest.mark.parametrize(
    "raw,expected",
    [("a@b.co", "a@b.co"), ("  Alice@Example.COM ", "alice@example.com")],
)
def test_validate_email_accepts_and_normalises(raw, expected):
    assert validate_email(raw) == expected


@pytest.mark.parametrize("bad", [None, "", "   ", "nope", "a@b", "a b@c.com", 5])
def test_validate_email_rejects_bad_values(bad):
    with pytest.raises(InvalidEmail):
        validate_email(bad)


def test_validate_search_terms_requires_at_least_one():
    with pytest.raises(InvalidSearch):
        validate_search_terms(None, None)
    with pytest.raises(InvalidSearch):
        validate_search_terms("", "")


def test_validate_search_terms_normalises_empty_to_none():
    assert validate_search_terms("name", "") == ("name", None)
    assert validate_search_terms("", "hello") == (None, "hello")
    assert validate_search_terms("name", "hello") == ("name", "hello")
