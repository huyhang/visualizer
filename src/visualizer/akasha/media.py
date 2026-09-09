"""Pure parsing and validation for images attached to an article."""

import re
from dataclasses import dataclass

from .errors import InvalidImage

ALIGNMENTS = ("left", "center", "right", "full")
MIN_WIDTH = 10
MAX_WIDTH = 100

# Image directives occupy a line of their own. The caption is deliberately the
# final field, so it may contain ``|`` without becoming a second mini-language.
_DIRECTIVE = re.compile(
    r"^\s*\{\{image:(?P<id>[a-f0-9]{32})\|"
    r"(?P<align>left|center|right|full)\|(?P<width>\d{1,3})\|"
    r"(?P<caption>.*?)\}\}\s*$"
)
_MEDIA_ID = re.compile(r"^[a-f0-9]{32}$")
_GALLERY_ITEM = re.compile(r"^(?P<id>[a-f0-9]{32})\|(?P<caption>.*)$")


@dataclass(frozen=True)
class ImagePlacement:
    media_id: str
    align: str
    width: int
    caption: str


@dataclass(frozen=True)
class GalleryItem:
    media_id: str
    caption: str


def parse_image_directive(line: str) -> ImagePlacement | None:
    """Parse one complete image line; malformed directives remain plain text."""
    match = _DIRECTIVE.fullmatch(line)
    if match is None:
        return None
    width = int(match.group("width"))
    if not MIN_WIDTH <= width <= MAX_WIDTH:
        return None
    align = match.group("align")
    if align == "full" and width != MAX_WIDTH:
        return None
    return ImagePlacement(
        media_id=match.group("id"),
        align=align,
        width=width,
        caption=match.group("caption"),
    )


def image_ids(text: str | None) -> set[str]:
    """Return the distinct media ids referenced by valid directives."""
    return {
        placement.media_id
        for line in str(text or "").splitlines()
        if (placement := parse_image_directive(line)) is not None
    }


def is_media_id(value) -> bool:
    """Return whether ``value`` is a canonical opaque media identifier."""
    return isinstance(value, str) and _MEDIA_ID.fullmatch(value) is not None


def parse_gallery_item(value) -> GalleryItem | None:
    """Parse the flat ``media-id|caption`` representation used by articles."""
    if not isinstance(value, str):
        return None
    match = _GALLERY_ITEM.fullmatch(value)
    if match is None:
        return None
    return GalleryItem(match.group("id"), match.group("caption"))


def document_image_ids(document: dict | None) -> set[str]:
    """Return valid inline, gallery and profile references from a document."""
    document = document or {}
    found = image_ids(document.get("body"))
    gallery = document.get("gallery")
    for value in gallery if isinstance(gallery, list) else ():
        if item := parse_gallery_item(value):
            found.add(item.media_id)
    profile = document.get("profile_image")
    if is_media_id(profile):
        found.add(profile)
    return found


def validate_alt_text(value) -> str:
    """Require concise alternative text for every library image."""
    if not isinstance(value, str) or not value.strip():
        raise InvalidImage("Alternative text is required.")
    alt = " ".join(value.split())
    if len(alt) > 300:
        raise InvalidImage("Alternative text must be at most 300 characters.")
    return alt
