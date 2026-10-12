"""Akasha's shareable kinds, as the account page and the share routes see them.

The neutral descriptors live in ``visualizer.sharing``; these are the same
kinds dressed in Akasha's words and guarded against its reserved namespaces.
"""

from dataclasses import replace

from visualizer import sharing

from .routing import reject_reserved
from .terms import TERMS

# Akasha's three shareable kinds, tightened from the neutral descriptors: the
# writer-facing words from ``terms.py``, and the guard that keeps the reserved
# `_auth` / `_chronos` namespaces unshareable. The chronos two are taken as they
# come -- akasha needs them to *list* a book on the account page, and a grant is
# all that takes, so nothing here imports chronos.
AKASHA_WORLD = replace(
    sharing.WORLD,
    label=TERMS["database"]["One"], plural=TERMS["database"]["Many"],
    guard=lambda scope: reject_reserved(scope["database"]),
)
AKASHA_COLLECTION = replace(
    sharing.COLLECTION,
    label=TERMS["collection"]["One"], plural=TERMS["collection"]["Many"],
    guard=lambda scope: reject_reserved(scope["database"]),
)
AKASHA_ARTICLE = replace(
    sharing.ARTICLE,
    label=TERMS["document"]["One"], plural=TERMS["document"]["Many"],
    guard=lambda scope: reject_reserved(scope["database"]),
)
# The order the account page shows them in: this writer's own world first, then
# what they have built on top of it.
ACCOUNT_KINDS = (
    AKASHA_WORLD, AKASHA_COLLECTION, AKASHA_ARTICLE, sharing.BOOK, sharing.CALENDAR
)


def account_kinds(book_world) -> tuple:
    """The shareable kinds, with the book taught to bring its world along.

    The same cascade Chronos hangs on its own collaborator route, so the two
    spellings of "share this book" cannot drift apart -- which they did, once,
    and the account page is the spelling people actually use.
    """
    if book_world is None:
        return ACCOUNT_KINDS
    cascade = sharing.world_reader_cascade(book_world)
    return tuple(
        replace(kind, after_share=cascade) if kind is sharing.BOOK else kind
        for kind in ACCOUNT_KINDS
    )
