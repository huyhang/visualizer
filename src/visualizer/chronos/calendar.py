"""Tick <-> date translation (design §4.1) -- pure, no I/O.

Ticks are canonical everywhere; translation happens only at the API edge (parse
on input, format on output). A book's attached calendars each select a
``TimeCodec`` via ``codec_for``.

A codec faces two ways. Outward, ``format``/``parts`` turn a tick into something
a reader recognises. Inward, ``components``/``span`` turn a *date* -- the numbers
a writer actually types -- back into ticks, so a scene can be scheduled as "Year
3, Month 4, Day 12" instead of ``19704``. The two directions are inverses, and
that is the property test: ``span(components(t)) == (t, t + 1)``.

``span`` returns a *range* rather than a point because a date names a period. A
writer who says only "Day 12" has named a whole day, and the half-open
``[start, end)`` convention the rest of Chronos uses says exactly how long that
is -- so the same date given as both ends of a timeframe yields a scene covering
that day and nothing more.

A book may carry **several** calendars at once -- different cultures reckoning
the same events differently -- so ``codec_for`` takes which one to read through.
They are parallel *labellings* of one canonical tick line, never parallel
timelines: no invariant, no ordering and no verdict can change with the choice.
"""

from typing import ClassVar, NamedTuple, Protocol

from .errors import CalendarNotFound, InvalidTimeframe


class TimeCodec(Protocol):
    def format(self, tick: int) -> str: ...

    def parts(self, tick: int) -> list[str]: ...

    def parse(self, label: str) -> int: ...

    def components(self, tick: int) -> dict[str, int] | None: ...

    def span(self, components: dict) -> tuple[int, int]: ...


class Unit(NamedTuple):
    """One place in a calendar's odometer, as a writer names it.

    ``origin`` is the number the writer gives for the zero digit: cycles read
    1-indexed ("Day 1" is the first day), the base unit 0-indexed (a clock reads
    00:00). ``limit`` is how many of this unit fit in the one above it, and is
    ``None`` for the open-ended top cycle -- which is what lets a story run past
    "Year 12" and, going the other way, lets Year 0 and below mean the
    pre-epoch ticks the odometer already prints.
    """

    name: str
    place: int  # how many ticks one of these is worth
    origin: int
    limit: int | None


def unit_table(names: list[str], sizes: list[int], base_unit: str) -> list[Unit]:
    """The calendar's places, coarsest first -- the order a date is written in.

    Built fine-to-coarse (that is the direction the sizes nest) and reversed,
    because every caller wants to read a date the way it is said: year, then
    month, then day.
    """
    units, place = [], 1
    for index, name in enumerate([base_unit, *names]):
        limit = sizes[index] if index < len(sizes) else None  # None -> the open top
        units.append(Unit(name, place, 0 if index == 0 else 1, limit))
        if limit is not None:
            place *= limit
    return list(reversed(units))


def read_date(raw, units: list[Unit]) -> dict[str, int]:
    """A writer's date, checked against these units and keyed by unit name.

    Three rules, each of them refusing to guess. Names are matched
    case-insensitively but must be ones this calendar keeps. Components must run
    **contiguously from the coarsest unit down**, so "Year 3, Month 4" is a date
    and a bare "Day 12" is not -- there is no honest way to supply the month.
    And every digit but the top one must fall inside its cycle: "Day 40" of a
    30-day month is a mistake to report, not one to silently roll forward.

    Finer units may be omitted; that is what makes a date name a period rather
    than an instant. See ``MixedRadixCodec.span``.
    """
    if not isinstance(raw, dict):
        raise InvalidTimeframe("A date must be an object of calendar components.")
    known = {unit.name.lower(): unit for unit in units}
    given: dict[str, int] = {}
    for key, value in raw.items():
        unit = known.get(str(key).strip().lower())
        if unit is None:
            raise InvalidTimeframe(
                f"This calendar has no '{key}'.",
                evidence={"unknown": key, "expected": [u.name for u in units]},
            )
        if unit.name in given:
            raise InvalidTimeframe(f"'{unit.name}' was given twice.")
        # bool is an int subclass but is not a valid component.
        if isinstance(value, bool) or not isinstance(value, int):
            raise InvalidTimeframe(f"'{unit.name}' must be a whole number.")
        given[unit.name] = value
    if not given:
        raise InvalidTimeframe(
            f"A date needs at least a '{units[0].name}'.",
            evidence={"expected": [u.name for u in units]},
        )
    _check_contiguous(given, units)
    _check_ranges(given, units)
    return given


def _check_contiguous(given: dict[str, int], units: list[Unit]) -> None:
    supplied = [unit.name in given for unit in units]
    depth = len(given) - 1
    if supplied[: depth + 1] != [True] * (depth + 1):
        missing = [u.name for u, has in zip(units, supplied[: depth + 1]) if not has]
        raise InvalidTimeframe(
            "A date has to start from the largest unit and leave no gaps: "
            f"name the {', '.join(missing)} too, or drop the finer components.",
            evidence={"missing": missing, "expected": [u.name for u in units]},
        )


def _check_ranges(given: dict[str, int], units: list[Unit]) -> None:
    for unit in units:
        if unit.name not in given or unit.limit is None:
            continue  # the top cycle is open-ended: any year, including Year 0
        value, last = given[unit.name], unit.origin + unit.limit - 1
        if not unit.origin <= value <= last:
            raise InvalidTimeframe(
                f"'{unit.name}' must be between {unit.origin} and {last} "
                "in this calendar.",
                evidence={"unit": unit.name, "value": value,
                          "min": unit.origin, "max": last},
            )


def depth_of(given: dict[str, int], units: list[Unit]) -> Unit:
    """The finest unit this date names -- the one that sets the period's length."""
    return units[len(given) - 1]


class IdentityCodec:
    """The default: ticks display as their integer selves."""

    # The one "unit" a bare tick line has, so a date in it is just {"tick": n}.
    _UNITS: ClassVar[list[Unit]] = [Unit("tick", 1, 0, None)]

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

    def components(self, tick: int) -> dict[str, int]:
        return {"tick": tick}

    def span(self, components: dict) -> tuple[int, int]:
        tick = read_date(components, self._UNITS)["tick"]
        return tick, tick + 1


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
        self._units = unit_table(self._names, self._sizes, base_unit)

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
            "Parsing calendar labels is not supported; send a date "
            f"({', '.join(u.name for u in self._units)}) or an integer tick."
        )

    def _nameable(self) -> bool:
        """Whether this calendar's units can be told apart by name.

        Repeated cycle names are legal -- they only read oddly -- but a date is
        keyed by name, so a calendar with two units called "cycle" has no
        vocabulary to write one in. Such a book keeps working; it just schedules
        in ticks.
        """
        names = [u.name.lower() for u in self._units]
        return len(set(names)) == len(names)

    def components(self, tick: int) -> dict[str, int] | None:
        """The numbers a writer would type for this tick, keyed by unit.

        The exact inverse of ``span``, and the same numbers ``parts`` prints --
        which is why a form can fill itself in from a tick without parsing the
        label it shows beside it.
        """
        if not self._nameable():
            return None
        base_rem, *cycle_parts = self._components(tick)
        digits = [*reversed(cycle_parts), base_rem]  # coarse-to-fine, like _units
        return {u.name: d + u.origin for u, d in zip(self._units, digits)}

    def span(self, components: dict) -> tuple[int, int]:
        """The half-open tick range a (possibly partial) date names.

        Every unit finer than the last one given is left at its own beginning,
        and the range runs one of *that* unit wide -- so "Year 3, Month 4, Day
        12" is the whole of that day, and "Year 3" is the whole of that year.
        """
        if not self._nameable():
            raise InvalidTimeframe(
                "This calendar names more than one unit the same, so a date "
                "cannot say which is meant. Schedule this scene in ticks.",
                evidence={"units": [u.name for u in self._units]},
            )
        given = read_date(components, self._units)
        tick = sum(u.place * (given.get(u.name, u.origin) - u.origin) for u in self._units)
        return tick, tick + depth_of(given, self._units).place


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

    def components(self, tick: int) -> dict[str, int] | None:
        """No date outside the era, matching ``parts``: there is nothing to
        prefill a form with when this reckoning was not being kept."""
        if not self.covers(tick):
            return None
        return self._inner.components(tick - (self._from or 0))

    def span(self, components: dict) -> tuple[int, int]:
        """The same offset ``format`` removes, added back.

        A date this reckoning was not keeping is refused rather than resolved:
        inventing a tick from a year nobody counted is the write-side twin of
        inventing a label for one. Only the *start* has to fall inside the era
        -- a scene may well begin under a reckoning and run past its end.
        """
        offset = self._from or 0
        start, end = self._inner.span(components)
        start, end = start + offset, end + offset
        if not self.covers(start):
            raise InvalidTimeframe(
                f"That date is outside {self._label}, so it names no tick.",
                evidence={"from_tick": self._from, "until_tick": self._until},
            )
        return start, end


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
