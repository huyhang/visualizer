"""What a manuscript document may contain, and what it may not.

Every assertion names the specific error, never a bare ``Exception``: a
validator that crashes with a ``TypeError`` is a bug, not a passing test.
"""

import pytest

from visualizer.logos.errors import InvalidDocument
from visualizer.logos.richtext import (
    MAX_DOCUMENT_CHARACTERS,
    MAX_TEXT_LENGTH,
    article_refs,
    validate_document,
    word_count,
)

from .conftest import document, mention


def _doc(*blocks):
    return {"version": 1, "type": "doc", "content": list(blocks)}


def test_a_document_is_paragraphs_with_stable_ids():
    result = validate_document(document("One two three.", "Four."))

    assert [block["id"] for block in result["content"]] == ["p1", "p2"]
    assert word_count(result) == 4


def test_paragraph_ids_must_be_present_and_unique():
    with pytest.raises(InvalidDocument, match="non-empty 'id'"):
        validate_document(_doc({"type": "paragraph", "content": []}))
    duplicated = _doc(
        {"type": "paragraph", "id": "p1", "content": []},
        {"type": "paragraph", "id": "p1", "content": []},
    )
    with pytest.raises(InvalidDocument, match="repeats a block id"):
        validate_document(duplicated)


def test_headings_and_lists_are_supported_blocks():
    result = validate_document(
        _doc(
            {
                "type": "heading",
                "id": "h1",
                "level": 2,
                "content": [{"type": "text", "text": "Part One"}],
            },
            {
                "type": "bullet_list",
                "id": "l1",
                "content": [
                    {
                        "type": "list_item",
                        "content": [{"type": "text", "text": "a sword"}],
                    }
                ],
            },
        )
    )

    assert [block["type"] for block in result["content"]] == ["heading", "bullet_list"]
    # A list's words count towards the manuscript exactly as a paragraph's do.
    assert word_count(result) == 4


def test_a_heading_level_is_bounded():
    heading = _doc({"type": "heading", "id": "h1", "level": 9, "content": []})
    with pytest.raises(InvalidDocument, match="heading level"):
        validate_document(heading)


@pytest.mark.parametrize(
    "node",
    [
        {"type": "text", "text": "x", "colour": "red"},
        {"type": "bulletList"},
        {"type": "text"},
        {"type": "text", "text": ""},
    ],
)
def test_unknown_node_types_and_stray_fields_are_refused(node):
    """The hole this closes: anything accepted here is stored and served back."""
    with pytest.raises(InvalidDocument):
        validate_document(_doc({"type": "paragraph", "id": "p1", "content": [node]}))


def test_marks_are_allowlisted_and_may_not_repeat():
    marked = _doc(
        {
            "type": "paragraph",
            "id": "p1",
            "content": [
                {"type": "text", "text": "loud", "marks": [{"type": "strong"}]}
            ],
        }
    )
    assert validate_document(marked)["content"][0]["content"][0]["marks"] == [
        {"type": "strong"}
    ]
    for marks in ([{"type": "blink"}], [{"type": "em"}, {"type": "em"}]):
        bad = _doc(
            {
                "type": "paragraph",
                "id": "p1",
                "content": [{"type": "text", "text": "x", "marks": marks}],
            }
        )
        with pytest.raises(InvalidDocument):
            validate_document(bad)


def test_links_must_be_http_or_site_relative():
    def linked(href):
        return _doc(
            {
                "type": "paragraph",
                "id": "p1",
                "content": [{"type": "link", "href": href, "text": "here"}],
            }
        )

    assert validate_document(linked("https://example.test/a"))
    with pytest.raises(InvalidDocument, match="http, https"):
        validate_document(linked("javascript:alert(1)"))


def test_akasha_references_are_read_back_in_reading_order():
    result = validate_document(mention("lyra", "Lyra"))

    assert article_refs(result) == [
        {"database": "ember", "collection": "characters", "id": "lyra"}
    ]


def test_a_reference_needs_all_three_parts():
    broken = _doc(
        {
            "type": "paragraph",
            "id": "p1",
            "content": [
                {"type": "mention", "ref": {"database": "ember"}, "text": "Lyra"}
            ],
        }
    )
    with pytest.raises(InvalidDocument, match="ref.collection"):
        validate_document(broken)


def test_validation_never_mutates_or_aliases_the_caller_s_payload():
    payload = document("Hello.")
    original = {"version": 1, "type": "doc", "content": [
        {"type": "paragraph", "id": "p1",
         "content": [{"type": "text", "text": "Hello."}]}
    ]}

    result = validate_document(payload)

    assert payload == original
    assert result["content"] is not payload["content"]
    assert result["content"][0] is not payload["content"][0]


def test_a_document_that_is_not_a_document_is_refused():
    for payload in ([], "prose", {"version": 2, "type": "doc", "content": []},
                    {"version": 1, "type": "page", "content": []},
                    {"version": 1, "type": "doc", "content": {}}):
        with pytest.raises(InvalidDocument):
            validate_document(payload)


def test_a_document_has_a_character_ceiling_across_all_its_paragraphs():
    """Built from paragraphs that are each individually legal, so the ceiling
    under test is the whole-document one and not the per-node one."""
    chunk = "x" * MAX_TEXT_LENGTH
    paragraphs = MAX_DOCUMENT_CHARACTERS // MAX_TEXT_LENGTH + 1

    with pytest.raises(InvalidDocument, match="at most 1000000 characters"):
        validate_document(document(*([chunk] * paragraphs)))
