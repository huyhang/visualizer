"""Pure, DB-free document comparison.

Documents are flat (see ``validation``): a mapping of key -> scalar or flat
array of scalars. ``diff_documents`` turns a pair of them into a structured,
field-by-field comparison that the editor renders intuitively:

- ``added``     -- a field present only in the new version
- ``removed``   -- a field present only in the old version
- ``changed``   -- a field whose value differs
- ``unchanged`` -- a field with an equal value

For a *changed* pair of strings it also computes a word-level ``inline`` diff so
the UI can highlight exactly what text moved; for a *changed* pair of arrays it
reports which elements were ``added``/``removed``. Nothing here depends on Flask
or MongoDB, so it is unit tested in isolation.
"""

import re
from typing import Any

ADDED = "added"
REMOVED = "removed"
CHANGED = "changed"
UNCHANGED = "unchanged"

# Split a string into alternating word/whitespace tokens so a word-level diff
# can be reassembled losslessly (concatenating the tokens rebuilds the input).
_TOKEN_RE = re.compile(r"\S+|\s+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text)


def inline_diff(old: str, new: str) -> list[dict]:
    """Word-level diff of two strings as a list of ``{op, text}`` segments.

    ``op`` is one of ``equal``, ``insert`` (present only in ``new``) or
    ``delete`` (present only in ``old``). Concatenating the ``text`` of the
    ``equal``+``delete`` segments rebuilds ``old``; ``equal``+``insert`` rebuilds
    ``new``.
    """
    from difflib import SequenceMatcher

    old_tokens, new_tokens = _tokenize(old), _tokenize(new)
    segments: list[dict] = []
    matcher = SequenceMatcher(a=old_tokens, b=new_tokens, autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            segments.append({"op": "equal", "text": "".join(old_tokens[i1:i2])})
        else:  # replace / delete / insert
            if i1 != i2:
                segments.append({"op": "delete", "text": "".join(old_tokens[i1:i2])})
            if j1 != j2:
                segments.append({"op": "insert", "text": "".join(new_tokens[j1:j2])})
    return segments


def _array_delta(old: list, new: list) -> dict:
    """Elements added to / removed from a flat array (order-insensitive)."""
    return {
        "added": [v for v in new if v not in old],
        "removed": [v for v in old if v not in new],
    }


def _field_change(key: str, old: Any, new: Any) -> dict:
    """Describe a single changed field, enriching strings/arrays with detail."""
    change = {"key": key, "status": CHANGED, "old": old, "new": new}
    if isinstance(old, str) and isinstance(new, str):
        change["inline"] = inline_diff(old, new)
    elif isinstance(old, list) and isinstance(new, list):
        change["array"] = _array_delta(old, new)
    return change


def diff_documents(old: dict, new: dict) -> dict:
    """Compare two flat documents and return a structured, per-field diff.

    Returns ``{"fields": [...]}`` where each entry has a ``key`` and a
    ``status`` (``added``/``removed``/``changed``/``unchanged``), sorted by key
    for a stable, predictable rendering.
    """
    old = old or {}
    new = new or {}
    fields = []
    for key in sorted(set(old) | set(new)):
        in_old, in_new = key in old, key in new
        if in_old and not in_new:
            fields.append({"key": key, "status": REMOVED, "old": old[key]})
        elif in_new and not in_old:
            fields.append({"key": key, "status": ADDED, "new": new[key]})
        elif old[key] == new[key]:
            fields.append({"key": key, "status": UNCHANGED, "old": old[key], "new": new[key]})
        else:
            fields.append(_field_change(key, old[key], new[key]))
    return {"fields": fields}
