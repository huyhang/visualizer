"""Tick <-> label translation (design §4.1) -- pure, no I/O.

Ticks are canonical everywhere; translation happens only at the API edge (parse
on input, format on output). A book's ``calendar`` descriptor selects a
``TimeCodec`` via ``codec_for``; each codec round-trips: ``parse(format(t)) == t``.
"""

from typing import Protocol

from .errors import InvalidTimeframe


class TimeCodec(Protocol):
    def format(self, tick: int) -> str: ...

    def parts(self, tick: int) -> list[str]: ...

    def parse(self, label: str) -> int: ...


class IdentityCodec:
    """The default: ticks display as their integer selves."""

    def format(self, tick: int) -> str:
        return str(tick)

    def parts(self, tick: int) -> list[str]:
        # A bare tick has no coarser structure -- a single component.
        return [self.format(tick)]

    def parse(self, label: str) -> int:
        try:
            return int(str(label).strip())
        except (TypeError, ValueError):
            raise InvalidTimeframe(f"Not an integer tick: {label!r}.")


class MixedRadixCodec:
    """A fictional calendar: a base unit plus nested, fixed-size cycles.

    ``cycles`` are ordered small-to-large, e.g. ``[{"name":"day","size":24},
    {"name":"month","size":30}, {"name":"year","size":12}]`` over a base unit of
    hours. ``format`` is repeated divmod; ``parse`` is the inverse composition.
    Day-like cycles (any cycle above the base) are shown 1-indexed; the base unit
    is shown 0-indexed (a clock reads 00:00, not 01:00).
    """

    def __init__(self, cycles: list[dict], base_unit: str = "tick", epoch_label: str = ""):
        if not cycles:
            raise InvalidTimeframe("A mixed-radix calendar needs at least one cycle.")
        self._names = [c["name"] for c in cycles]
        self._sizes = [int(c["size"]) for c in cycles]
        if any(s < 1 for s in self._sizes):
            raise InvalidTimeframe("Calendar cycle sizes must be >= 1.")
        self._base_unit = base_unit
        self._epoch = epoch_label

    def _components(self, tick: int) -> list[int]:
        """Least-significant first: base remainder, then each cycle."""
        parts = []
        value = tick
        for size in self._sizes:
            value, rem = divmod(value, size)
            parts.append(rem)
        parts.append(value)  # the open-ended top cycle
        return parts

    def parts(self, tick: int) -> list[str]:
        """The label's display components, coarse-to-fine: one per cycle (largest
        first), then the base-unit clock with the epoch appended.

        ``format`` is just these joined by ``", "``. Exposing the split lets a UI
        group and relabel on structured data instead of re-parsing the string --
        robust to any cycle names and any calendar depth (design §4.1).
        """
        base_rem, *cycle_parts = self._components(tick)
        # cycle_parts aligns with self._names (the last is the open top cycle).
        labelled = [
            f"{name.capitalize()} {part + 1}"
            for name, part in zip(reversed(self._names), reversed(cycle_parts))
        ]
        labelled.append(f"{base_rem:02d}:00 {self._epoch}".strip())
        return labelled

    def format(self, tick: int) -> str:
        return ", ".join(self.parts(tick))

    def parse(self, label: str) -> int:
        raise InvalidTimeframe(
            "Parsing calendar labels is not yet supported; send integer ticks."
        )


def codec_for(book) -> TimeCodec:
    """Build the codec a book's ``calendar`` descriptor selects (Identity if none).

    ``book`` may be a ``Book`` model or a plain dict (as read from the store).
    """
    calendar = getattr(book, "calendar", None)
    if calendar is None and isinstance(book, dict):
        calendar = book.get("calendar")
    if not calendar:
        return IdentityCodec()
    kind = calendar.get("kind", "mixed_radix")
    if kind == "identity":
        return IdentityCodec()
    return MixedRadixCodec(
        cycles=calendar.get("cycles", []),
        base_unit=calendar.get("base_unit", "tick"),
        epoch_label=calendar.get("epoch_label", ""),
    )
