"""Identifier, metadata and ordering rules -- pure, no database, no app."""

import pytest

from visualizer.logos.errors import (
    InvalidIdentifier,
    InvalidOrder,
    InvalidSection,
    InvalidVolume,
)
from visualizer.logos.validation import (
    validate_identifier,
    validate_order,
    validate_section_payload,
    validate_volume_payload,
)

from .conftest import document, section_payload


def test_a_volume_holds_only_a_title_and_an_overview():
    volume = validate_volume_payload(
        "eye-of-the-world", {"title": "  The Eye of the World  ", "overview": "One."}
    )

    assert volume.title == "The Eye of the World"
    assert volume.overview == "One."
    assert volume.sections == []


def test_a_volume_needs_a_title_and_refuses_metadata_it_does_not_own():
    with pytest.raises(InvalidVolume, match="'title'"):
        validate_volume_payload("one", {})
    with pytest.raises(InvalidVolume, match="'title'"):
        validate_volume_payload("one", {"title": "   "})
    # Ordering is the volume's own; a title edit must not carry a section list.
    with pytest.raises(InvalidVolume, match="unsupported fields"):
        validate_volume_payload("one", {"title": "One", "sections": ["a"]})
    with pytest.raises(InvalidVolume, match="unsupported fields"):
        validate_volume_payload("one", {"title": "One", "status": "draft"})


@pytest.mark.parametrize(
    "value", ["", "bad id", ".hidden", "-lead", "a/b", "a::b", "x" * 129, None, 7]
)
def test_resource_ids_stay_safe_url_path_segments(value):
    with pytest.raises(InvalidIdentifier):
        validate_identifier(value, "section")


@pytest.mark.parametrize("kind", ["prologue", "chapter", "epilogue", "glossary"])
def test_every_supported_section_kind_round_trips(kind):
    section = validate_section_payload("s", section_payload(kind=kind, events=()))
    assert section.kind == kind


def test_a_section_names_its_kind_and_carries_a_document():
    with pytest.raises(InvalidSection, match="supported section kind"):
        validate_section_payload("s", {"kind": "afterword", "document": document()})
    with pytest.raises(InvalidSection, match="requires a 'document'"):
        validate_section_payload("s", {"kind": "chapter"})


def test_a_blank_section_title_reads_as_no_title():
    section = validate_section_payload(
        "s", section_payload(title="   ", events=())
    )
    assert section.title is None


def test_event_ids_are_a_list_of_distinct_ids():
    section = validate_section_payload(
        "s", section_payload(events=("opening", "climax"))
    )
    assert section.event_ids == ["opening", "climax"]
    with pytest.raises(InvalidSection, match="duplicate ids"):
        validate_section_payload("s", section_payload(events=("a", "b", "a")))
    with pytest.raises(InvalidSection, match="non-empty ids"):
        validate_section_payload("s", section_payload(events=("a", "")))


def test_reordering_must_name_every_current_id_exactly_once():
    assert validate_order({"volumes": ["b", "a"]}, "volumes", ["a", "b"]) == ["b", "a"]

    with pytest.raises(InvalidOrder) as dropped:
        validate_order({"volumes": ["a"]}, "volumes", ["a", "b"])
    assert dropped.value.evidence == {"missing": ["b"], "unknown": []}

    with pytest.raises(InvalidOrder) as invented:
        validate_order({"volumes": ["a", "b", "c"]}, "volumes", ["a", "b"])
    assert invented.value.evidence == {"missing": [], "unknown": ["c"]}

    with pytest.raises(InvalidOrder, match="duplicate ids"):
        validate_order({"volumes": ["a", "a"]}, "volumes", ["a", "b"])


def test_validation_builds_a_fresh_record_and_leaves_the_request_alone():
    payload = section_payload(events=("opening",))
    before = {key: value for key, value in payload.items()}

    section = validate_section_payload("s", payload)

    assert payload == before
    assert section.event_ids is not payload["event_ids"]
    assert section.document is not payload["document"]
