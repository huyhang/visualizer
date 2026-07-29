"""Unit tests for the pure validation helpers (no DB, no Flask)."""

import pytest

from visualizer.document_server.errors import (
    InvalidDocument,
    InvalidEmail,
    InvalidSearch,
)
from visualizer.document_server.validation import (
    validate_document,
    validate_email,
    validate_search_terms,
)


@pytest.mark.parametrize("payload", [{}, {"a": 1}, {"nested": {"x": [1, 2]}}])
def test_validate_document_accepts_dicts(payload):
    assert validate_document(payload) is payload


@pytest.mark.parametrize("payload", [None, [], [1, 2], "text", 5, 3.14, True])
def test_validate_document_rejects_non_dicts(payload):
    with pytest.raises(InvalidDocument):
        validate_document(payload)


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
