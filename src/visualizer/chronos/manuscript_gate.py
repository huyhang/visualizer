"""The narrow manuscript boundary Chronos consults before a destructive write.

Chronos owns the plan; Logos owns the prose written from it. Deleting a book or
a scene that prose still depends on is refused here, in the service, so the rule
holds for every entrypoint -- the combined gateway and the standalone Chronos
app alike -- rather than only where the route happens to be wired.

The seam is a ``Protocol``, and the default is the null implementation below, so
Chronos keeps working unchanged when no manuscript service is attached.
"""

from typing import Protocol


class ManuscriptGate(Protocol):
    def has_content(self, book: str) -> bool:
        """Whether any manuscript record exists for this book."""

    def sections_referencing(self, book: str, event: str) -> list[dict]:
        """The live sections naming this scene, as ``volume``/``section`` pairs."""


class NullManuscriptGate:
    """No manuscript service is attached; nothing to protect."""

    def has_content(self, book: str) -> bool:
        return False

    def sections_referencing(self, book: str, event: str) -> list[dict]:
        return []
