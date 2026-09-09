"""Pure validation helpers.

These functions have no dependency on Flask or MongoDB so they can be unit
tested in isolation.
"""

from typing import Any

from .errors import InvalidDocument, InvalidSearch
from .media import image_ids, is_media_id, parse_gallery_item

# A document value must be a scalar or a flat array of scalars. ``bool`` is a
# subclass of ``int`` and is intentionally allowed as a scalar.
_SCALAR_TYPES = (str, int, float, bool, type(None))


def _is_scalar(value: Any) -> bool:
    return isinstance(value, _SCALAR_TYPES)


def _is_flat_array(value: Any) -> bool:
    return isinstance(value, list) and all(_is_scalar(v) for v in value)


def validate_document(payload: Any) -> dict:
    """Return ``payload`` if it is a valid, *flat* JSON dictionary.

    A document must be a JSON object (mapping) whose every value is either a
    scalar (``str``, ``int``, ``float``, ``bool``, ``null``) or a flat array of
    scalars. Nested objects and nested arrays are rejected -- this keeps the
    article editor and the version diff simple and intuitive. Anything that is
    not a mapping (``None`` from a body that failed to parse, a list, a string,
    a number) is rejected too.
    """
    if not isinstance(payload, dict):
        raise InvalidDocument("Document must be a valid JSON dictionary.")
    for key, value in payload.items():
        if not (_is_scalar(value) or _is_flat_array(value)):
            raise InvalidDocument(
                f"Field '{key}' must be a scalar or a flat array of scalars; "
                "nested objects and nested arrays are not allowed."
            )
    _validate_article_images(payload)
    return payload


def _validate_article_images(document: dict) -> None:
    """Keep the reserved profile/gallery fields internally consistent."""
    raw_gallery = document.get("gallery", [])
    if not isinstance(raw_gallery, list):
        raise InvalidDocument("Field 'gallery' must be a flat array of image entries.")

    gallery = [parse_gallery_item(value) for value in raw_gallery]
    if any(item is None for item in gallery):
        raise InvalidDocument(
            "Every gallery entry must contain a valid media id and caption."
        )
    gallery_ids = [item.media_id for item in gallery]
    if len(gallery_ids) != len(set(gallery_ids)):
        raise InvalidDocument("Field 'gallery' cannot contain the same image twice.")

    profile = document.get("profile_image")
    if profile is not None:
        if not is_media_id(profile):
            raise InvalidDocument("Field 'profile_image' must be a valid media id.")
        if profile not in gallery_ids:
            raise InvalidDocument("The profile image must also be attached to the gallery.")

    unattached = image_ids(document.get("body")) - set(gallery_ids)
    if unattached:
        raise InvalidDocument(
            "Every image used in the article body must also be attached to the gallery."
        )


def validate_search_terms(key: str | None, text: str | None) -> tuple[str | None, str | None]:
    """Normalise and validate search terms.

    At least one of ``key`` or ``text`` must be a non-empty value. Empty strings
    are treated as "not provided".
    """
    key = key or None
    text = text or None
    if key is None and text is None:
        raise InvalidSearch("Provide at least one of 'key' or 'text'.")
    return key, text
