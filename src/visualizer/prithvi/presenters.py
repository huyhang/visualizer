"""Pure shaping for the browser UI: rows in, display dictionaries out.

Nothing here touches Flask, Mongo or grants. The route decides *who may see
what* and hands these functions an already-filtered list; these functions
decide only *how it reads*. That split is what lets the picker's ranking and
the pin card's excerpt be tested as arithmetic, with no app and no fixtures.

The excerpt is flattened to plain text on this side of the wire on purpose.
The map page renders it with ``textContent``, so there is no wikitext parser
and no ``innerHTML`` in the browser at all -- one less way for an article body
to become markup.
"""

import re
from urllib.parse import quote

from visualizer.akasha.labels import derive_title

CHOICE_LIMIT = 20
_PREVIEW_FACTS = 6
_PREVIEW_CHARS = 360
_ELLIPSIS = "…"

# ``[[locations/ember-road|the Ember Road]]`` -> ``the Ember Road``; a link with
# no label falls back to its last path segment (``ember-road``).
_WIKILINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
# Bold/italic quotes, and heading or bullet markers at either end of a line.
_WIKITEXT_MARKS = re.compile(r"'{2,3}|^\s*[=*#:]+\s*|\s*=+\s*$", re.MULTILINE)
_WHITESPACE = re.compile(r"\s+")


def article_choices(rows, query: str = "", limit: int = CHOICE_LIMIT) -> list[dict]:
    """The pin picker's list: matching articles, best match first, capped.

    Ranking is by *where* the query matched -- an exact id or title before a
    prefix before a substring -- then alphabetically, so an unfiltered list is
    still in a predictable order and a filtered one leads with what was meant.
    """
    needle = query.strip().lower()
    choices = [_choice(row) for row in rows]
    if needle:
        choices = [choice for choice in choices if needle in _haystack(choice)]
    choices.sort(key=lambda choice: _sort_key(choice, needle))
    return choices[:limit]


def article_preview(ref, found: dict, akasha_url: str) -> dict:
    """One article as the card beside the map: title, excerpt, a few facts."""
    document = found.get("document") or {}
    return {
        "database": ref.world,
        "collection": ref.collection,
        "collection_title": derive_title(ref.collection),
        "id": ref.article_id,
        "title": str(document.get("title") or ref.article_id),
        "excerpt": excerpt(document.get("body")),
        "facts": _facts(document),
        "url": article_url(akasha_url, ref.world, ref.collection, ref.article_id),
    }


def excerpt(body, limit: int = _PREVIEW_CHARS) -> str:
    """A body reduced to one paragraph of plain, unmarked prose."""
    if not isinstance(body, str) or not body.strip():
        return ""
    plain = _WIKILINK.sub(_link_label, body)
    plain = _WIKITEXT_MARKS.sub(" ", plain)
    plain = _WHITESPACE.sub(" ", plain).strip()
    if len(plain) <= limit:
        return plain
    return plain[: limit - 1].rstrip() + _ELLIPSIS


def article_url(base: str, database: str, collection: str, article_id: str) -> str:
    """Where Akasha shows this article, safe to drop straight into an ``href``."""
    path = "/".join(quote(part, safe="") for part in (database, collection, article_id))
    return f"{base.rstrip('/')}/#/{path}"


def _choice(row: dict) -> dict:
    document = row.get("document") or {}
    article_id = str(row["id"])
    collection = str(row["collection"])
    return {
        "database": str(row["database"]),
        "collection": collection,
        "collection_title": derive_title(collection),
        "id": article_id,
        "title": str(document.get("title") or article_id),
    }


def _haystack(choice: dict) -> str:
    return " ".join(
        (
            choice["title"], choice["id"],
            choice["collection"], choice["collection_title"],
        )
    ).lower()


def _sort_key(choice: dict, needle: str) -> tuple:
    return (_rank(choice, needle), choice["title"].lower(), choice["id"])


def _rank(choice: dict, needle: str) -> int:
    if not needle:
        return 0
    names = (choice["title"].lower(), choice["id"].lower())
    if needle in names:
        return 0
    if any(name.startswith(needle) for name in names):
        return 1
    if any(needle in name for name in names):
        return 2
    return 3  # matched only the collection


def _facts(document: dict) -> list[dict]:
    """The document's other fields, as label/value pairs a card can print."""
    return [
        {"key": derive_title(str(key)), "value": _fact_value(value)}
        for key, value in document.items()
        if key not in ("title", "body") and _has_value(value)
    ][:_PREVIEW_FACTS]


def _has_value(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str | list | tuple):
        return len(value) > 0
    return True


def _fact_value(value) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, list | tuple):
        return ", ".join(str(item) for item in value)
    return str(value)


def _link_label(match: re.Match) -> str:
    return match.group(2) or match.group(1).split("/")[-1]
