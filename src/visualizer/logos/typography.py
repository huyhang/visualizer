"""Pure manuscript typography normalization.

``curl_text`` looks both ways to tell an opening quote from a closing one,
which is the right rule for prose that already exists -- every API write comes
through here. The browser mirrors it in ``static/js/typography.js`` and adds a
backwards-only rule for the caret, where nothing follows the mark yet; keep the
two files in step. ``fix_elisions`` is the shared correction that lets the
cheap rule catch up: a leading apostrophe cannot be told from an opening single
quote until its word arrives.

Only visible prose is touched. Code spans keep their literal characters, and a
link's destination is a separate field this never reads.
"""

import re
from copy import deepcopy

OPENING_CONTEXT = frozenset("([{—–‘“")

# Words that begin with an elided letter, and decades written '90s. Anchored on
# the curl rather than the straight mark so it can correct an earlier guess.
LEADING_ELISION = re.compile(
    r"‘(?=(?:cause|em|n|round|til|tis|twas)\b|\d\ds\b)", re.IGNORECASE
)


def curl_quotes(document: dict) -> dict:
    """Return a deep-copied document with straight prose quotes normalized."""
    result = deepcopy(document)
    for block in result.get("content", []):
        if block.get("type") in {"bullet_list", "ordered_list"}:
            groups = [item.get("content", []) for item in block.get("content", [])]
        else:
            groups = [block.get("content", [])]
        for nodes in groups:
            _curl_nodes(nodes)
    return result


def fix_elisions(text: str) -> str:
    """Re-curl a leading apostrophe that was guessed as an opening quote."""
    return LEADING_ELISION.sub("’", text) if "‘" in text else text


def curl_typed_mark(before: str, mark: str) -> str:
    """The mark just typed, decided from the text behind the caret alone."""
    previous = before[-1:] if before else ""
    opening = not previous or previous.isspace() or previous in OPENING_CONTEXT
    if mark == '"':
        return "“" if opening else "”"
    return "‘" if opening else "’"


def curl_text(text: str, before: str = "", after: str = "") -> str:
    """Normalize one text run using adjacent visible text as context."""
    if not text:
        return text
    straight = bool({"'", '"'} & set(text))
    return fix_elisions(_convert(text, before, after) if straight else text)


def _convert(text: str, before: str, after: str) -> str:
    result: list[str] = []
    for index, character in enumerate(text):
        previous = result[-1] if result else before[-1:] or ""
        following = text[index + 1 : index + 2] or after[:1]
        if character == '"':
            result.append("“" if _opens(previous, following) else "”")
        elif character == "'":
            result.append(_single_quote(previous, following))
        else:
            result.append(character)
    return "".join(result)


def _curl_nodes(nodes: list[dict]) -> None:
    textual = [node for node in nodes if isinstance(node.get("text"), str)]
    for index, node in enumerate(textual):
        if _is_code(node):
            continue
        before = _nearest_text(textual, index, -1)
        after = _nearest_text(textual, index, 1)
        node["text"] = curl_text(node["text"], before, after)


def _nearest_text(nodes: list[dict], index: int, direction: int) -> str:
    cursor = index + direction
    while 0 <= cursor < len(nodes):
        text = nodes[cursor].get("text", "")
        if text:
            return text[-1:] if direction < 0 else text[:1]
        cursor += direction
    return ""


def _is_code(node: dict) -> bool:
    return any(mark.get("type") == "code" for mark in node.get("marks", []))


def _opens(previous: str, following: str) -> bool:
    return bool(following and not following.isspace()) and (
        not previous or previous.isspace() or previous in OPENING_CONTEXT
    )


def _single_quote(previous: str, following: str) -> str:
    if previous.isalnum() and following.isalnum():
        return "’"
    return "‘" if _opens(previous, following) else "’"
