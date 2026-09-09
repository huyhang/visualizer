"""What the media library stores, independent of what produced it.

The library began as an image library and is now also a diorama library. Rather
than grow a second store beside it — duplicating world scoping, grant-aware
visibility, the reference scan that guards deletion, and the storage accounting
that hangs off all three — the store was taught to hold an *asset*: a named set
of blobs plus whatever facts its kind cares about.

The store deliberately does not know what those facts mean. An image reports
``format``/``width``/``height``; a diorama reports its vertex and texture
counts. Both are carried through to the API surface unchanged, which is why
adding a kind does not touch persistence at all.
"""

from dataclasses import dataclass, field

IMAGE = "image"
DIORAMA = "diorama"


@dataclass(frozen=True)
class AssetBlob:
    """One stored file: the bytes, how to serve them, and how to recognise them."""

    data: bytes
    mime_type: str
    sha256: str
    facts: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Asset:
    """A library entry as the store sees it: a kind, a name, facts, and blobs."""

    kind: str
    filename: str
    facts: dict
    variants: dict[str, AssetBlob]
