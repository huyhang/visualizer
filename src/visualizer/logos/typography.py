"""Pure manuscript typography normalization.

The editor gives immediate feedback, while this module is the canonical save
boundary for browser and API clients alike.  It only touches visible prose;
code spans and link destinations retain their literal characters.
"""

from copy import deepcopy

OPENING_CONTEXT = frozenset("([{\u2014\u2013\u2018\u201c")
ELISIONS = ("'cause", "'em", "'round", "'til", "'tis", "'twas")


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


def curl_text(text: str, before: str = "", after: str = "") -> str:
    """Normalize one text run using adjacent visible text as context."""
    if not text or not ({"'", '"'} & set(text)):
        return text
    result: list[str] = []
    for index, character in enumerate(text):
        previous = result[-1] if result else before[-1:] or ""
        following = text[index + 1 : index + 2] or after[:1]
        if character == '"':
            result.append("\u201c" if _opens(previous, following) else "\u201d")
        elif character == "'":
            result.append(_single_quote(text, index, previous, following))
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


def _single_quote(text: str, index: int, previous: str, following: str) -> str:
    if previous.isalnum() and following.isalnum():
        return "\u2019"
    tail = text[index:].casefold()
    if any(tail.startswith(word) for word in ELISIONS) or (
        following.isdigit() and (not previous or previous.isspace())
    ):
        return "\u2019"
    return "\u2018" if _opens(previous, following) else "\u2019"
