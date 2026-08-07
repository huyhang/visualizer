"""Readable names for namespaces, derived from their slugs.

A world and a category are addressed by name -- ``ember-pact``,
``characters`` -- and that name is load-bearing: it keys every grant, every
``[[wikilink]]`` and every chronos reference, so it cannot be prettied up
in place. What *can* be prettied up is how it is printed, which is all this
module does: ``ember-pact`` reads as "Ember Pact" on a card without anything
underneath it moving.

Nothing is stored. The title is a pure function of the slug, so it applies to
everything that already exists with no migration, and there is exactly one
implementation of it -- the browse endpoints ship the derived title alongside
the raw name, and the browser prints what it is given rather than deriving its
own (very slightly different) version.
"""

import re

# Words a title leaves in lower case unless they start or end it. Small enough
# to be obvious, which matters more here than being exhaustive.
_SMALL_WORDS = frozenset(
    {"a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "nor",
     "of", "on", "or", "the", "to", "vs", "with"}
)

_SEPARATORS = re.compile(r"[-_\s]+")


def derive_title(name: str) -> str:
    """A readable title for a slug.

    ``ember-pact`` -> ``Ember Pact``; ``lord-of-the-rings`` -> ``Lord of the
    Rings``. A name that already carries a capital is returned untouched: the
    writer chose that spelling, and second-guessing it is how ``McTavish``
    becomes ``Mctavish``.
    """
    if not name or any(character.isupper() for character in name):
        return name
    words = [word for word in _SEPARATORS.split(name) if word]
    if not words:
        return name
    last = len(words) - 1
    return " ".join(
        word if 0 < index < last and word in _SMALL_WORDS else _capitalise(word)
        for index, word in enumerate(words)
    )


def _capitalise(word: str) -> str:
    """Upper-case the first letter, leaving the rest alone (``2nd`` stays ``2nd``)."""
    return word[:1].upper() + word[1:]
