"""Tick <-> label translation (design §4.1) -- pure, no I/O.

Ticks are canonical everywhere; translation happens only at the API edge (parse
on input, format on output). A book's attached calendars each select a
``TimeCodec`` via ``codec_for``; each codec round-trips: ``parse(format(t)) == t``.

A book may carry **several** calendars at once -- different cultures reckoning
the same events differently -- so ``codec_for`` takes which one to read through.
They are parallel *labellings* of one canonical tick line, never parallel
timelines: no invariant, no ordering and no verdict can change with the choice.
"""

from typing import Protocol

from .errors import CalendarNotFound, InvalidTimeframe


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


class EraCodec:
    """A reckoning that begins -- and may end -- partway along the tick line.

    A decorator over any other codec, and the whole of Chronos's answer to
    parallel calendars that do not span the whole story: a culture that starts
    counting at its founding, or stops when it is destroyed.

    Two things follow from ``from_tick``. Ticks are *offset* before they reach
    the inner codec, so a reckoning that begins mid-story genuinely reads "Year
    1" at its own beginning rather than inheriting the book's arithmetic. And a
    tick outside ``[from_tick, until_tick)`` gets no label at all: it formats as
    a plain marker, because inventing a date in a calendar nobody was keeping is
    worse than admitting there is none. The bound is half-open, matching
    ``timeline.overlaps`` -- ``until_tick`` is the first tick *not* covered.

    Everything downstream keeps calling ``format``/``parts`` and needs no idea
    this exists.
    """

    def __init__(self, inner: TimeCodec, from_tick=None, until_tick=None, label=""):
        self._inner = inner
        self._from = from_tick
        self._until = until_tick
        self._label = label or "this reckoning"

    def covers(self, tick: int) -> bool:
        """Whether this reckoning was being kept at ``tick``."""
        if self._from is not None and tick < self._from:
            return False
        return not (self._until is not None and tick >= self._until)

    def _marker(self, tick: int) -> str:
        # Which side of the era we fell off. ``from_tick`` may be absent -- a
        # reckoning that was always kept and simply stopped -- in which case the
        # only way out of range is past the end.
        before = self._from is not None and tick < self._from
        return f"{'before' if before else 'after'} {self._label}"

    def format(self, tick: int) -> str:
        if not self.covers(tick):
            return self._marker(tick)
        return self._inner.format(tick - (self._from or 0))

    def parts(self, tick: int) -> list[str]:
        # One component when out of era, so a UI that groups by the coarsest part
        # collects every such scene into a single honest band rather than
        # scattering them through years that were never counted.
        if not self.covers(tick):
            return [self._marker(tick)]
        return self._inner.parts(tick - (self._from or 0))

    def parse(self, label: str) -> int:
        """Inverse of ``format`` for in-era labels, so the round-trip survives
        the decoration wherever the inner codec supports it at all."""
        return self._inner.parse(label) + (self._from or 0)


def codec_for_descriptor(descriptor: dict | None) -> TimeCodec:
    """The codec a bare calendar descriptor selects (Identity when there is none)."""
    if not descriptor:
        return IdentityCodec()
    if descriptor.get("kind", "mixed_radix") == "identity":
        return IdentityCodec()
    return MixedRadixCodec(
        cycles=descriptor.get("cycles", []),
        base_unit=descriptor.get("base_unit", "tick"),
        epoch_label=descriptor.get("epoch_label", ""),
    )


def codec_for_attachment(attachment) -> TimeCodec:
    """The codec one of a book's attached calendars selects.

    Undecorated unless the attachment names an era -- a calendar that spans the
    whole story pays nothing for the ones that do not.
    """
    inner = codec_for_descriptor(attachment.descriptor)
    if attachment.from_tick is None and attachment.until_tick is None:
        return inner
    return EraCodec(
        inner, attachment.from_tick, attachment.until_tick, attachment.display_label
    )


def select_calendar(book, calendar_id: str | None = None):
    """Which of a book's calendars to read through, or None for plain ticks.

    Without a choice the book's *first* attachment wins: order is the writer's
    stated preference, so the default view needs no second field to record it.
    A named calendar that is not attached is refused rather than quietly falling
    back -- a stale bookmark should say so, not misreport every date on screen.
    """
    calendars = getattr(book, "calendars", None) or []
    if calendar_id is None:
        return calendars[0] if calendars else None
    for attachment in calendars:
        if attachment.id == calendar_id:
            return attachment
    raise CalendarNotFound(
        f"This book has no calendar '{calendar_id}'.",
        evidence={"calendar": calendar_id, "attached": [c.id for c in calendars]},
    )


def codec_for(book, calendar_id: str | None = None) -> TimeCodec:
    """Build the codec this book reads ticks through (Identity if it has none).

    Pure and I/O-free, which is exactly why a book *copies* the calendars it
    attaches rather than pointing at library records: this runs on every read,
    and a lookup here would put a database call under every formatted date.
    """
    attachment = select_calendar(book, calendar_id)
    if attachment is None:
        return IdentityCodec()
    return codec_for_attachment(attachment)
