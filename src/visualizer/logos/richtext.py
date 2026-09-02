"""The structured rich-text document a section stores, and its rules.

A document is a list of *blocks*; a paragraph is one of them, and paragraphs are
what the manuscript is counted in. Blocks carry a stable ``id`` that survives
reordering and re-editing, so a future editor -- or a comment anchored to a
paragraph -- keeps pointing at the same prose after the text around it changes.

Every node type is validated exhaustively and unknown fields are refused, which
is what keeps the stored shape equal to the documented one. Validation returns
freshly built nodes rather than the caller's own dicts: nothing here mutates the
request body, and no stored document shares structure with it.

Node ids are checked more loosely than resource ids on purpose. A volume or
section id becomes a URL path segment; a paragraph id never leaves the document,
so it only has to be a short, unique, non-empty string.
"""

import json
from typing import Any

from .errors import InvalidDocument

DOCUMENT_VERSION = 1

BLOCK_TYPES = ("paragraph", "heading", "bullet_list", "ordered_list")
INLINE_TYPES = ("text", "hard_break", "link", "mention", "article_link")
MARK_TYPES = ("em", "strong", "strike", "code")
REFERENCE_TYPES = frozenset({"mention", "article_link"})
HEADING_LEVELS = (1, 2, 3)

MAX_NODE_ID_LENGTH = 128
MAX_TEXT_LENGTH = 10_000
MAX_HREF_LENGTH = 2_048
MAX_BLOCKS = 5_000
MAX_INLINE_PER_BLOCK = 500
MAX_DOCUMENT_CHARACTERS = 1_000_000
MAX_DOCUMENT_BYTES = 4 * 1024 * 1024

EMPTY_DOCUMENT = {"version": DOCUMENT_VERSION, "type": "doc", "content": []}


def validate_document(payload: Any) -> dict:
    """Return a normalised document, or raise ``InvalidDocument``."""
    body = _mapping(payload, "A rich-text document")
    _only(body, {"version", "type", "content"}, "document")
    if body.get("version") != DOCUMENT_VERSION:
        raise InvalidDocument(
            f"'version' must be {DOCUMENT_VERSION}.",
            evidence={"version": body.get("version")},
        )
    if body.get("type") != "doc":
        raise InvalidDocument("A rich-text document must have type 'doc'.")
    content = body.get("content")
    if not isinstance(content, list):
        raise InvalidDocument("A document's 'content' must be a list.")
    if len(content) > MAX_BLOCKS:
        raise InvalidDocument(
            f"A document may contain at most {MAX_BLOCKS} blocks.",
            evidence={"blocks": len(content), "max": MAX_BLOCKS},
        )
    seen: set[str] = set()
    blocks = [_block(node, index, seen) for index, node in enumerate(content)]
    document = {"version": DOCUMENT_VERSION, "type": "doc", "content": blocks}
    _check_size(document)
    return document


def blocks_of(document: dict, *, kind: str | None = None) -> list[dict]:
    blocks = document.get("content", [])
    if kind is None:
        return list(blocks)
    return [block for block in blocks if block.get("type") == kind]


def iter_inline(document: dict):
    """Every inline node in the document, lists included, in reading order."""
    for block in document.get("content", []):
        for node in block.get("content", []):
            if node.get("type") == "list_item":
                yield from node.get("content", [])
            else:
                yield node


def visible_text(document: dict):
    """Every string a reader actually sees, in reading order.

    A mention and a link render as prose, so their display text is manuscript
    words like any other. Counting only ``text`` nodes would quietly undercount
    a chapter written with the editor's linking features.
    """
    for node in iter_inline(document):
        text = node.get("text")
        if isinstance(text, str):
            yield text


def word_count(document: dict) -> int:
    return sum(len(text.split()) for text in visible_text(document))


def character_count(document: dict) -> int:
    return sum(len(text) for text in visible_text(document))


def article_refs(document: dict) -> list[dict]:
    """The distinct Akasha references the prose makes, in reading order."""
    found: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for node in iter_inline(document):
        if node.get("type") not in REFERENCE_TYPES:
            continue
        ref = node["ref"]
        key = (ref["database"], ref["collection"], ref["id"])
        if key not in seen:
            seen.add(key)
            found.append(dict(ref))
    return found


# -- blocks ------------------------------------------------------------------


def _block(value: Any, index: int, seen: set[str]) -> dict:
    where = f"Block {index + 1}"
    node = _mapping(value, where)
    block_type = node.get("type")
    if block_type not in BLOCK_TYPES:
        raise InvalidDocument(
            f"{where} has an unsupported block type.",
            evidence={"type": block_type, "supported": list(BLOCK_TYPES)},
        )
    if block_type == "heading":
        _only(node, {"type", "id", "level", "content"}, where)
        return {
            "type": "heading",
            "id": _node_id(node, where, seen),
            "level": _level(node, where),
            "content": _inline_list(node, where),
        }
    if block_type in ("bullet_list", "ordered_list"):
        _only(node, {"type", "id", "content"}, where)
        return {
            "type": block_type,
            "id": _node_id(node, where, seen),
            "content": _list_items(node, where),
        }
    _only(node, {"type", "id", "content"}, where)
    return {
        "type": "paragraph",
        "id": _node_id(node, where, seen),
        "content": _inline_list(node, where),
    }


def _level(node: dict, where: str) -> int:
    level = node.get("level")
    if level not in HEADING_LEVELS:
        raise InvalidDocument(
            f"{where} must have a heading level of 1, 2 or 3.",
            evidence={"level": level},
        )
    return level


def _list_items(node: dict, where: str) -> list[dict]:
    items = node.get("content", [])
    if not isinstance(items, list):
        raise InvalidDocument(f"{where} content must be a list.")
    if len(items) > MAX_INLINE_PER_BLOCK:
        raise InvalidDocument(
            f"{where} may contain at most {MAX_INLINE_PER_BLOCK} items.",
            evidence={"items": len(items), "max": MAX_INLINE_PER_BLOCK},
        )
    return [_list_item(item, where, position) for position, item in enumerate(items)]


def _list_item(value: Any, where: str, position: int) -> dict:
    place = f"{where}, item {position + 1}"
    item = _mapping(value, place)
    if item.get("type") != "list_item":
        raise InvalidDocument(
            f"{place} must be a 'list_item'.", evidence={"type": item.get("type")}
        )
    _only(item, {"type", "content"}, place)
    return {"type": "list_item", "content": _inline_list(item, place)}


def _inline_list(node: dict, where: str) -> list[dict]:
    content = node.get("content", [])
    if not isinstance(content, list):
        raise InvalidDocument(f"{where} content must be a list.")
    if len(content) > MAX_INLINE_PER_BLOCK:
        raise InvalidDocument(
            f"{where} may contain at most {MAX_INLINE_PER_BLOCK} inline nodes.",
            evidence={"nodes": len(content), "max": MAX_INLINE_PER_BLOCK},
        )
    return [_inline(item, where, index) for index, item in enumerate(content)]


# -- inline ------------------------------------------------------------------


def _inline(value: Any, where: str, position: int) -> dict:
    place = f"{where}, node {position + 1}"
    node = _mapping(value, place)
    node_type = node.get("type")
    if node_type not in INLINE_TYPES:
        raise InvalidDocument(
            f"{place} has an unsupported inline node type.",
            evidence={"type": node_type, "supported": list(INLINE_TYPES)},
        )
    if node_type == "hard_break":
        _only(node, {"type"}, place)
        return {"type": "hard_break"}
    if node_type == "link":
        _only(node, {"type", "href", "text"}, place)
        return {
            "type": "link",
            "href": _href(node.get("href"), place),
            "text": _text(node.get("text"), place),
        }
    if node_type in REFERENCE_TYPES:
        _only(node, {"type", "ref", "text"}, place)
        return {
            "type": node_type,
            "ref": _reference(node.get("ref"), place),
            "text": _text(node.get("text"), place),
        }
    _only(node, {"type", "text", "marks"}, place)
    result = {"type": "text", "text": _text(node.get("text"), place)}
    marks = _marks(node.get("marks", []), place)
    if marks:
        result["marks"] = marks
    return result


def _text(value: Any, place: str) -> str:
    if not isinstance(value, str) or not value:
        raise InvalidDocument(f"{place} text must be a non-empty string.")
    if len(value) > MAX_TEXT_LENGTH:
        raise InvalidDocument(
            f"{place} text may be at most {MAX_TEXT_LENGTH} characters.",
            evidence={"characters": len(value), "max": MAX_TEXT_LENGTH},
        )
    return value


def _href(value: Any, place: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidDocument(f"{place} href must be a non-empty string.")
    href = value.strip()
    if len(href) > MAX_HREF_LENGTH:
        raise InvalidDocument(f"{place} href is too long.")
    if not href.startswith(("http://", "https://", "/")):
        raise InvalidDocument(
            f"{place} href must be http, https, or a site-relative path.",
            evidence={"href": href},
        )
    return href


def _reference(value: Any, place: str) -> dict:
    ref = _mapping(value, f"{place} ref")
    _only(ref, {"database", "collection", "id"}, f"{place} ref")
    for field in ("database", "collection", "id"):
        part = ref.get(field)
        if not isinstance(part, str) or not part.strip():
            raise InvalidDocument(
                f"{place} ref.{field} must be a non-empty string.",
                evidence={field: part},
            )
    return {
        "database": ref["database"].strip(),
        "collection": ref["collection"].strip(),
        "id": ref["id"].strip(),
    }


def _marks(value: Any, place: str) -> list[dict]:
    if not isinstance(value, list):
        raise InvalidDocument(f"{place} marks must be a list.")
    kinds = []
    for mark in value:
        node = _mapping(mark, f"{place} mark")
        _only(node, {"type"}, f"{place} mark")
        if node.get("type") not in MARK_TYPES:
            raise InvalidDocument(
                f"{place} has an unsupported mark.",
                evidence={"type": node.get("type"), "supported": list(MARK_TYPES)},
            )
        kinds.append(node["type"])
    if len(kinds) != len(set(kinds)):
        raise InvalidDocument(f"{place} repeats the same mark.")
    return [{"type": kind} for kind in kinds]


# -- shared ------------------------------------------------------------------


def _node_id(node: dict, where: str, seen: set[str]) -> str:
    value = node.get("id")
    if not isinstance(value, str) or not value.strip():
        raise InvalidDocument(f"{where} must carry a non-empty 'id'.")
    node_id = value.strip()
    if len(node_id) > MAX_NODE_ID_LENGTH:
        raise InvalidDocument(
            f"{where} id may be at most {MAX_NODE_ID_LENGTH} characters."
        )
    if node_id in seen:
        raise InvalidDocument(
            f"{where} repeats a block id used earlier in the document.",
            evidence={"id": node_id},
        )
    seen.add(node_id)
    return node_id


def _check_size(document: dict) -> None:
    characters = character_count(document)
    if characters > MAX_DOCUMENT_CHARACTERS:
        raise InvalidDocument(
            f"A section may hold at most {MAX_DOCUMENT_CHARACTERS} characters.",
            evidence={"characters": characters, "max": MAX_DOCUMENT_CHARACTERS},
        )
    size = len(json.dumps(document, ensure_ascii=False).encode("utf-8"))
    if size > MAX_DOCUMENT_BYTES:
        raise InvalidDocument(
            f"A section document may occupy at most {MAX_DOCUMENT_BYTES} bytes.",
            evidence={"bytes": size, "max": MAX_DOCUMENT_BYTES},
        )


def _mapping(value: Any, what: str) -> dict:
    if not isinstance(value, dict):
        raise InvalidDocument(f"{what} must be a JSON object.")
    return value


def _only(body: dict, allowed: set[str], what: str) -> None:
    unexpected = sorted(set(body) - allowed)
    if unexpected:
        raise InvalidDocument(
            f"{what} contains unsupported fields.",
            evidence={"unexpected": unexpected},
        )
