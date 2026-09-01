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

import re
from typing import ClassVar, NamedTuple, Protocol

from .errors import CalendarNotFound, InvalidTimeframe


class TimeCodec(Protocol):
    # Whether this codec already knows where it sits on the tick line. A
    # calendar handed an explicit origin does; one that simply counts from
    # wherever its culture began does not, and borrows an era's ``from_tick``
    # for its zero. See ``EraCodec``.
    anchored: bool

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
    """A writer's date, checked against these fixed-size units.

    ``read_components`` does everything that is the same in every calendar; the
    only rule left here is how far each cycle counts, which a fixed-size unit
    knows from its own ``limit``.
    """
    given = read_components(raw, [unit.name for unit in units])
    _check_ranges(given, units)
    return given


def read_components(raw, names: list[str]) -> dict[str, int]:
    """A writer's date, checked against these unit names and keyed by them.

    Two rules, each of them refusing to guess. Names are matched
    case-insensitively but must be ones this calendar keeps. Components must run
    **contiguously from the coarsest unit down**, so "Year 3, Month 4" is a date
    and a bare "Day 12" is not -- there is no honest way to supply the month.

    A third rule -- that every digit falls inside its unit, so "Day 40" of a
    30-day month is a mistake to report rather than one to silently roll forward
    -- is left to the caller, because it is the one that is not the same
    everywhere: a fixed cycle knows its own length, while a Gregorian February
    is 29 days one year and 28 the next. Keeping the rest here is what lets a
    writer move between a fantasy calendar and Earth and be told off in the same
    words.

    Finer units may be omitted; that is what makes a date name a period rather
    than an instant. See ``MixedRadixCodec.span``.
    """
    if not isinstance(raw, dict):
        raise InvalidTimeframe("A date must be an object of calendar components.")
    known = {name.lower(): name for name in names}
    given: dict[str, int] = {}
    for key, value in raw.items():
        name = known.get(str(key).strip().lower())
        if name is None:
            raise InvalidTimeframe(
                f"This calendar has no '{key}'.",
                evidence={"unknown": key, "expected": list(names)},
            )
        if name in given:
            raise InvalidTimeframe(f"'{name}' was given twice.")
        # bool is an int subclass but is not a valid component.
        if isinstance(value, bool) or not isinstance(value, int):
            raise InvalidTimeframe(f"'{name}' must be a whole number.")
        given[name] = value
    if not given:
        raise InvalidTimeframe(
            f"A date needs at least a '{names[0]}'.",
            evidence={"expected": list(names)},
        )
    _check_contiguous(given, names)
    return given


def _check_contiguous(given: dict[str, int], names: list[str]) -> None:
    supplied = [name in given for name in names]
    depth = len(given) - 1
    if supplied[: depth + 1] != [True] * (depth + 1):
        missing = [n for n, has in zip(names, supplied[: depth + 1]) if not has]
        raise InvalidTimeframe(
            "A date has to start from the largest unit and leave no gaps: "
            f"name the {', '.join(missing)} too, or drop the finer components.",
            evidence={"missing": missing, "expected": list(names)},
        )


def _check_ranges(given: dict[str, int], units: list[Unit]) -> None:
    for unit in units:
        if unit.limit is None:
            continue  # the top cycle is open-ended: any year, including Year 0
        _check_bound(given, unit.name, unit.origin, unit.origin + unit.limit - 1)


def _check_bound(given: dict[str, int], name: str, low: int, high: int) -> None:
    """How far one unit counts, said the same way whatever set the ceiling.

    Shared so that "'day' must be between 1 and 29 in this calendar" reads
    identically whether the 29 came from a fixed cycle or from February 2024.
    """
    if name not in given:
        return
    value = given[name]
    if not low <= value <= high:
        raise InvalidTimeframe(
            f"'{name}' must be between {low} and {high} in this calendar.",
            evidence={"unit": name, "value": value, "min": low, "max": high},
        )


def depth_of(given: dict[str, int], units: list[Unit]) -> Unit:
    """The finest unit this date names -- the one that sets the period's length."""
    return units[len(given) - 1]


class IdentityCodec:
    """The default: ticks display as their integer selves."""

    anchored = False

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

    # Its year 1 is wherever its culture started counting, so an era that says
    # when that was is also saying where this calendar's zero is.
    anchored = False

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


# -- Earth ---------------------------------------------------------------------
#
# Everything above rests on a unit being a fixed number of ticks, which is what
# lets ``unit_table`` give each place a ``place`` and ``span`` add them up. A
# Gregorian month is not fixed, and that single fact is why Earth is a codec of
# its own rather than another cycle table. Only the *labels* vary in length: a
# tick stays exactly one day, hour or minute, so nothing downstream learns that
# February is short -- ``span`` simply reports a shorter period for it.

GREGORIAN_TICK_UNITS = ("day", "hour", "minute")

# The date a writer types at each precision, coarsest first.
_GREGORIAN_NAMES = {
    "day": ("year", "month", "day"),
    "hour": ("year", "month", "day", "hour"),
    "minute": ("year", "month", "day", "hour", "minute"),
}

# The one scale factor the arithmetic below needs.
_TICKS_PER_DAY = {"day": 1, "hour": 24, "minute": 1440}

_MONTH_NAMES = (
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

# A date, or a date and a time with a fixed offset. Matched here rather than
# handed to ``datetime.fromisoformat`` because that caps at year 1, and a story
# whose Earth thread reaches antiquity should be able to start there.
_ORIGIN = re.compile(
    r"(?P<year>-?\d{1,6})-(?P<month>\d{2})-(?P<day>\d{2})"
    r"(?:[T ](?P<hour>\d{2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?"
    r"(?P<offset>[Zz]|[+-]\d{2}:\d{2}))?"
)


def _days_from_civil(year: int, month: int, day: int) -> int:
    """Days from 1970-01-01 to this proleptic Gregorian date.

    Howard Hinnant's algorithm. Shifting the year to start in March puts the
    leap day at the *end* of it, which turns the whole conversion into exact
    integer arithmetic with no month table and no special case -- and keeps it
    exact for negative years, which is what lets a story date itself BCE.
    """
    shifted = year - (month <= 2)
    era = shifted // 400
    year_of_era = shifted - era * 400
    march_month = (month + 9) % 12
    day_of_year = (153 * march_month + 2) // 5 + day - 1
    day_of_era = year_of_era * 365 + year_of_era // 4 - year_of_era // 100 + day_of_year
    return era * 146_097 + day_of_era - 719_468


def _civil_from_days(days: int) -> tuple[int, int, int]:
    """The exact inverse of ``_days_from_civil``."""
    days += 719_468
    era = days // 146_097
    day_of_era = days - era * 146_097
    year_of_era = (
        day_of_era - day_of_era // 1460 + day_of_era // 36_524 - day_of_era // 146_096
    ) // 365
    day_of_year = day_of_era - (365 * year_of_era + year_of_era // 4 - year_of_era // 100)
    march_month = (5 * day_of_year + 2) // 153
    day = day_of_year - (153 * march_month + 2) // 5 + 1
    month = (march_month + 2) % 12 + 1
    return year_of_era + era * 400 + (month <= 2), month, day


def _month_after(year: int, month: int) -> tuple[int, int, int]:
    return (year + 1, 1, 1) if month == 12 else (year, month + 1, 1)


def _month_length(year: int, month: int) -> int:
    """How many days this particular month has -- 28, 29, 30 or 31.

    Measured rather than tabulated, so the leap rule and its century exception
    are stated once, inside ``_days_from_civil``, and cannot drift from a table.
    """
    return _days_from_civil(*_month_after(year, month)) - _days_from_civil(year, month, 1)


def _year_length(year: int) -> int:
    return _days_from_civil(year + 1, 1, 1) - _days_from_civil(year, 1, 1)


def _year_label(year: int) -> str:
    """A year as a writer reads it.

    Before year 1 the count runs backwards, and it is said the way a history
    book says it. The *components* stay plain integers counting 0, -1, -2 back
    from 1 BCE -- a date is a map of numbers everywhere else in Chronos and
    stays one here -- but nobody is asked to read or type that spelling.
    """
    return str(year) if year > 0 else f"{1 - year} BCE"


def _offset_label(raw: str) -> str:
    """A fixed offset as it reads beside a time: "UTC", or "UTC-08:00"."""
    if raw.upper() == "Z":
        return "UTC"
    sign, hours, minutes = raw[0], int(raw[1:3]), int(raw[4:6])
    if hours > 23 or minutes > 59:
        raise InvalidTimeframe(
            f"{raw!r} is not a UTC offset -- they run from -23:59 to +23:59."
        )
    return "UTC" if not (hours or minutes) else f"UTC{sign}{hours:02d}:{minutes:02d}"


def read_origin(raw, tick_unit: str) -> tuple[int, str]:
    """Which Earth moment tick zero was: where it sits, and how its clock reads.

    A day-counting calendar needs only a date. Nothing finer is observable in
    one, so asking for a time of day and an offset would be asking for facts
    that never reach the page. Anything finer needs both.

    The offset does no arithmetic. Being fixed for the whole calendar, it
    cancels out of every conversion -- tick 0 lands on the same date whether the
    origin is written ``Z`` or ``-08:00``. What it does is say which wall clock
    these dates are told by, which is the difference between "the London scene
    at 14:00" and a bare number.
    """
    match = _origin_shape(raw)
    within, offset = _origin_time(match, tick_unit)
    return _origin_date(match) * _TICKS_PER_DAY[tick_unit] + within, offset


def _origin_shape(raw) -> re.Match:
    """That there is an origin at all, and that it is spelled like one."""
    if not isinstance(raw, str) or not raw.strip():
        raise InvalidTimeframe(
            "A Gregorian calendar needs an 'origin' -- the Earth date its tick 0 fell on."
        )
    match = _ORIGIN.fullmatch(raw.strip())
    if match is None:
        raise InvalidTimeframe(
            f"{raw.strip()!r} is not a date this calendar can start from. Write it as "
            "2024-02-27, or as 2024-02-27T06:00Z when ticks are finer than a day.",
            evidence={"origin": raw.strip()},
        )
    return match


def _origin_date(match: re.Match) -> int:
    """The day it names, counted from 1970 -- refusing one no month ever had."""
    year, month, day = (int(match[part]) for part in ("year", "month", "day"))
    if not 1 <= month <= 12 or not 1 <= day <= _month_length(year, month):
        raise InvalidTimeframe(
            f"{match[0]!r} names no real date.", evidence={"origin": match[0]}
        )
    return _days_from_civil(year, month, day)


def _origin_time(match: re.Match, tick_unit: str) -> tuple[int, str]:
    """How far into that day the origin falls, and how its clock reads.

    A day-counting calendar has neither, and may not carry either: nothing finer
    than the date is observable in one, so a time and an offset would be facts
    that never reach the page.
    """
    if match["hour"] is None:
        if tick_unit != "day":
            raise InvalidTimeframe(
                f"This calendar counts {tick_unit}s, so its 'origin' needs a time "
                "and a fixed offset, like 2024-02-27T06:00Z."
            )
        return 0, ""
    if tick_unit == "day":
        raise InvalidTimeframe(
            "This calendar counts whole days, so its 'origin' is a date like "
            "2024-02-27, with no time of day."
        )
    hour, minute = int(match["hour"]), int(match["minute"])
    if hour > 23 or minute > 59:
        raise InvalidTimeframe(
            f"{match[0]!r} names no real time of day.", evidence={"origin": match[0]}
        )
    if int(match["second"] or 0) or (tick_unit == "hour" and minute):
        raise InvalidTimeframe(
            f"This calendar counts whole {tick_unit}s, so its 'origin' must begin on one."
        )
    per_day = _TICKS_PER_DAY[tick_unit]
    return (hour * 60 + minute) * per_day // 1440, _offset_label(match["offset"])


class GregorianCodec:
    """Earth dates over the story's own tick line, with real month lengths.

    A reusable library entry fixes how long one tick is. Each book attachment
    says which Earth moment *its* tick zero was, because that alignment is the
    story's own -- two books sharing one Earth calendar may sit centuries apart.

    Years run in both directions. Before year 1 they read as "44 BCE" rather
    than as a negative number; see ``_year_label``.
    """

    # The origin already fixes this calendar on the tick line, so an era may
    # hide the ticks outside itself but must never move it. See ``EraCodec``.
    anchored = True

    def __init__(self, origin: str | None, tick_unit: str = "day"):
        if tick_unit not in GREGORIAN_TICK_UNITS:
            raise InvalidTimeframe(
                f"A Gregorian tick is a day, an hour or a minute, not {tick_unit!r}.",
                evidence={"tick_unit": tick_unit, "known": list(GREGORIAN_TICK_UNITS)},
            )
        self._unit = tick_unit
        self._names = _GREGORIAN_NAMES[tick_unit]
        self._per_day = _TICKS_PER_DAY[tick_unit]
        self._zero, self._offset = read_origin(origin, tick_unit)

    def _at(self, tick: int) -> tuple[int, int, int, int, int]:
        """The Earth date and time of day this tick falls on."""
        days, within = divmod(self._zero + tick, self._per_day)
        year, month, day = _civil_from_days(days)
        hour, minute = divmod(within * 1440 // self._per_day, 60)
        return year, month, day, hour, minute

    def format(self, tick: int) -> str:
        year, month, day, hour, minute = self._at(tick)
        label = f"{_MONTH_NAMES[month]} {day}, {_year_label(year)}"
        if self._unit == "day":
            return label
        return f"{label}, {hour:02d}:{minute:02d} {self._offset}"

    def parts(self, tick: int) -> list[str]:
        """The label's components, coarse to fine, for a UI that groups by year.

        Not simply ``format`` split up: prose says the month first and a column
        of dates has to sort by the year, so the two orders genuinely differ.
        The timeline rail bands scenes by the coarsest part, and should do that
        on structured data rather than by re-parsing a sentence.
        """
        year, month, day, hour, minute = self._at(tick)
        parts = [_year_label(year), _MONTH_NAMES[month], f"Day {day}"]
        if self._unit != "day":
            parts.append(f"{hour:02d}:{minute:02d} {self._offset}")
        return parts

    def parse(self, label: str) -> int:
        raise InvalidTimeframe(
            "Parsing calendar labels is not supported; send a date "
            f"({', '.join(self._names)}) or an integer tick."
        )

    def components(self, tick: int) -> dict[str, int]:
        """The numbers a writer would type for this tick, keyed by unit.

        The exact inverse of ``span``, so a form can fill itself in from a tick
        without parsing the label shown beside it.
        """
        values = dict(zip(("year", "month", "day", "hour", "minute"), self._at(tick)))
        return {name: values[name] for name in self._names}

    def span(self, components: dict) -> tuple[int, int]:
        """The half-open tick range a (possibly partial) date names.

        The same rule as everywhere else -- the period runs one of the finest
        unit given -- except that here "one month" is however many days that
        particular month has.
        """
        given = read_components(components, list(self._names))
        self._check_ranges(given)
        start = self._tick_of(given)
        return start, start + self._length_of(given)

    def _check_ranges(self, given: dict[str, int]) -> None:
        # The year is open-ended in both directions, like any top cycle. The
        # day's ceiling is the only one that is not a constant, and contiguity
        # has already guaranteed the year and month it depends on are present.
        _check_bound(given, "month", 1, 12)
        if "day" in given:
            _check_bound(given, "day", 1, _month_length(given["year"], given["month"]))
        _check_bound(given, "hour", 0, 23)
        _check_bound(given, "minute", 0, 59)

    def _tick_of(self, given: dict[str, int]) -> int:
        """The first tick of the period this date names."""
        days = _days_from_civil(given["year"], given.get("month", 1), given.get("day", 1))
        minutes = given.get("hour", 0) * 60 + given.get("minute", 0)
        return days * self._per_day + minutes * self._per_day // 1440 - self._zero

    def _length_of(self, given: dict[str, int]) -> int:
        """How many ticks that period covers -- where the variable months live."""
        finest = self._names[len(given) - 1]
        if finest == "year":
            return _year_length(given["year"]) * self._per_day
        if finest == "month":
            return _month_length(given["year"], given["month"]) * self._per_day
        if finest == "day":
            return self._per_day
        return self._per_day // 24 if finest == "hour" else 1


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

    anchored = True

    def __init__(self, inner: TimeCodec, from_tick=None, until_tick=None, label=""):
        self._inner = inner
        self._from = from_tick
        self._until = until_tick
        self._label = label or "this reckoning"
        # ``from_tick`` says two things at once, and only one of them is always
        # true. It always bounds what this reckoning covers. It *also* fixes
        # where the reckoning's own count begins -- but only for a calendar that
        # has no other way of knowing, which is any calendar whose year 1 is
        # simply wherever its culture started. A calendar handed an explicit
        # origin already knows, and moving it would silently re-date every scene
        # against the alignment the writer stated. So the codec decides.
        self._offset = 0 if getattr(inner, "anchored", False) else (from_tick or 0)

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
        return self._inner.format(tick - self._offset)

    def parts(self, tick: int) -> list[str]:
        # One component when out of era, so a UI that groups by the coarsest part
        # collects every such scene into a single honest band rather than
        # scattering them through years that were never counted.
        if not self.covers(tick):
            return [self._marker(tick)]
        return self._inner.parts(tick - self._offset)

    def parse(self, label: str) -> int:
        """Inverse of ``format`` for in-era labels, so the round-trip survives
        the decoration wherever the inner codec supports it at all."""
        return self._inner.parse(label) + self._offset

    def components(self, tick: int) -> dict[str, int] | None:
        """No date outside the era, matching ``parts``: there is nothing to
        prefill a form with when this reckoning was not being kept."""
        if not self.covers(tick):
            return None
        return self._inner.components(tick - self._offset)

    def span(self, components: dict) -> tuple[int, int]:
        """The same offset ``format`` removes, added back.

        A date this reckoning was not keeping is refused rather than resolved:
        inventing a tick from a year nobody counted is the write-side twin of
        inventing a label for one. Only the *start* has to fall inside the era
        -- a scene may well begin under a reckoning and run past its end.
        """
        offset = self._offset
        start, end = self._inner.span(components)
        start, end = start + offset, end + offset
        if not self.covers(start):
            raise InvalidTimeframe(
                f"That date is outside {self._label}, so it names no tick.",
                evidence={"from_tick": self._from, "until_tick": self._until},
            )
        return start, end


def codec_for_descriptor(descriptor: dict | None, origin: str | None = None) -> TimeCodec:
    """The codec a bare calendar descriptor selects (Identity when there is none).

    ``origin`` is the one fact a reusable descriptor cannot carry -- which Earth
    moment a *particular* book's tick 0 was -- so it arrives separately and only
    a Gregorian descriptor reads it.
    """
    if not descriptor:
        return IdentityCodec()
    kind = descriptor.get("kind", "mixed_radix")
    if kind == "identity":
        return IdentityCodec()
    if kind == "gregorian":
        return GregorianCodec(origin, descriptor.get("tick_unit", "day"))
    return MixedRadixCodec(
        cycles=descriptor.get("cycles", []),
        base_unit=descriptor.get("base_unit", "tick"),
        epoch_label=descriptor.get("epoch_label", ""),
    )


def codec_for_attachment(attachment) -> TimeCodec:
    """The codec one of a book's attached calendars selects.

    Undecorated unless the attachment names an era -- a calendar that spans the
    whole story pays nothing for the ones that do not. Whether that era also
    moves the calendar's zero is the codec's own answer, not this factory's:
    see ``EraCodec``.
    """
    inner = codec_for_descriptor(attachment.descriptor, attachment.origin)
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
