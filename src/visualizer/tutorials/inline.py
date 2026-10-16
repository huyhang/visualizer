"""The three marks a lesson's text may carry, and nothing else.

    `＋ New article`      something on screen: drawn as a small key cap
    **Title**             emphasis
    {world}               a word the glossary defines: a link to it
    {worlds|world}        the same, shown as "worlds"

Everything is escaped before a mark is looked for, so a lesson cannot put
markup on a page; the marks are the whole vocabulary.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from markupsafe import Markup, escape

_MARKS = re.compile(r"`([^`]+)`|\*\*([^*]+)\*\*|\{([^{}|]+)(?:\|([^{}|]+))?\}")
_LABEL = re.compile(r"`([^`]+)`")
_TERM = re.compile(r"\{([^{}|]+)(?:\|([^{}|]+))?\}")
_SENTENCE_END = re.compile(r"[.!?…](?=\s|$)")

TermHref = Callable[[str], str | None]


def render_inline(text: str, term_href: TermHref) -> Markup:
    """``text`` as markup: escaped, then its marks drawn.

    ``term_href`` says where a glossary word links, or ``None`` for a word the
    glossary does not have -- which is then shown as plain text.
    """

    def draw(match: re.Match) -> str:
        label, bold, shown, term = match.groups()
        if label is not None:
            return f'<span class="ui">{label}</span>'
        if bold is not None:
            return f"<strong>{bold}</strong>"
        href = term_href(term or shown)
        return shown if href is None else f'<a class="term" href="{href}">{shown}</a>'

    return Markup(_MARKS.sub(draw, str(escape(text))))


def labels_in(text: str) -> tuple[str, ...]:
    """The on-screen labels a passage quotes."""
    return tuple(_LABEL.findall(text))


def terms_in(text: str) -> tuple[str, ...]:
    """The glossary words a passage links, as the glossary spells them."""
    return tuple(term or shown for shown, term in _TERM.findall(text))


def plain(text: str) -> str:
    """A passage as a reader hears it: the marks gone, their words kept."""
    text = _LABEL.sub(r"\1", text).replace("**", "")
    return _TERM.sub(lambda match: match.group(1), text)


def sentence_count(text: str) -> int:
    """Roughly how many sentences a passage has -- enough to keep steps short.

    A label's own dots ("Search titles…") end nothing, so labels count as a word.
    """
    words = plain(_LABEL.sub("label", text)).strip()
    return max(1, len(_SENTENCE_END.findall(words)))


def word_count(text: str) -> int:
    return len(plain(text).split())
