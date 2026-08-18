"""Payload validation and parsing (design §3) -- pure, no I/O.

Turns raw request bodies into domain models, raising the *referential* errors
(which are hard, §8.1). Entity *existence* is not checked here -- that is the
``EntityGate``'s job; this module only checks structure. The resource id comes
from the URL, so it is passed in rather than read from the body.
"""

from typing import Any

from .calendar import TimeCodec
from .errors import (
    InvalidBook,
    InvalidCalendar,
    InvalidEvent,
    InvalidGoal,
    InvalidPlotline,
    InvalidTimeframe,
)
from .models import (
    DEFAULT_CALENDAR_ID,
    Book,
    CalendarAttachment,
    EntityRef,
    Event,
    Goal,
    LibraryCalendar,
    Plotline,
)


def _require_mapping(payload: Any, err) -> dict:
    if not isinstance(payload, dict):
        raise err("Request body must be a JSON object.")
    return payload


# An overview is prose, not an essay: this is a sanity bound, not a style rule.
# Unbounded free text goes straight into the stored document and back out in
# every listing, so a runaway paste (or a script) would bloat responses that
# nothing paginates by size.
MAX_OVERVIEW = 10_000


def _parse_prose(body: dict, field: str, err, maximum: int = MAX_OVERVIEW) -> str:
    """One of the writer's free-prose fields, bounded and never null.

    Optional, and absent means empty rather than null -- the model keeps one
    empty value, so nothing downstream has to tell "never written" apart from
    "cleared". The field name and error class are passed in because a book, a
    thread and a goal each spell theirs differently and report their own (§8.1).
    """
    text = body.get(field, "")
    if not isinstance(text, str):
        raise err(f"'{field}' must be a string.")
    if len(text) > maximum:
        raise err(
            f"'{field}' must be at most {maximum} characters.",
            evidence={"length": len(text), "max": maximum},
        )
    return text


def _parse_overview(body: dict, err) -> str:
    """The writer's free-prose summary of a book or a thread."""
    return _parse_prose(body, "overview", err)


def _parse_id_list(value: Any, field: str, err) -> list[str]:
    """A list of ids naming other records -- absent means none.

    Duplicates are refused rather than collapsed. A list of ids is a *set* in
    everything but spelling, so a repeat says the caller believes it means
    something; taking the silent union would hide the misunderstanding, and
    drawing the same chip twice would advertise it.
    """
    if value is None:
        return []
    if not isinstance(value, list):
        raise err(f"'{field}' must be a list of ids.")
    if not all(isinstance(item, str) and item for item in value):
        raise err(f"'{field}' must be a list of non-empty id strings.")
    duplicated = sorted({item for item in value if value.count(item) > 1})
    if duplicated:
        raise err(
            f"'{field}' names the same id more than once.",
            evidence={field: duplicated},
        )
    return list(value)


def parse_entity_ref(obj: Any, what: str = "entity") -> EntityRef:
    if not isinstance(obj, dict):
        raise InvalidEvent(f"Each {what} must be an object with database/collection/id.")
    try:
        database, collection, id_ = obj["database"], obj["collection"], obj["id"]
    except KeyError as missing:
        raise InvalidEvent(f"{what} reference is missing {missing}.")
    if not all(isinstance(v, str) and v for v in (database, collection, id_)):
        raise InvalidEvent(f"{what} reference fields must be non-empty strings.")
    return EntityRef(database, collection, id_)


def _parse_ref_list(value: Any, what: str) -> list[EntityRef]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise InvalidEvent(f"'{what}' must be a list of entity references.")
    return [parse_entity_ref(item, what) for item in value]


def _parse_tick(value: Any, field: str) -> int | None:
    """An integer tick, or None meaning "not scheduled yet"."""
    if value is None:
        return None
    # bool is an int subclass but is not a valid tick.
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidTimeframe(f"'{field}' must be an integer tick or null.")
    return value


def _parse_dated_timeframe(body: dict, codec: TimeCodec) -> tuple[int | None, int | None]:
    """A timeframe given as calendar dates rather than raw ticks.

    Each date names a *period* (see ``TimeCodec.span``), and the two ends take
    opposite halves of it: the start takes the period's first tick, the end the
    first tick after it. So the same date in both fields spans exactly that day
    -- which is how a writer means "this scene happens on Day 12", and it lands
    on the half-open ``[start, end)`` the rest of Chronos already assumes.
    """
    start_date, end_date = body.get("start_date"), body.get("end_date")
    start = None if start_date is None else codec.span(start_date)[0]
    end = None if end_date is None else codec.span(end_date)[1]
    return start, end


def _parse_timeframe(body: dict, codec: TimeCodec) -> tuple[int | None, int | None]:
    """Both ends or neither -- a scene is fully scheduled or not at all.

    Half-known timing would multiply the cases every rule has to handle for
    little gain, so it is rejected rather than guessed at.

    A writer may say when a scene happens in either of two ways: raw ticks, or
    dates in the calendar being read through. Never both at once -- two answers
    to one question is a client bug, and picking a winner would hide it.
    """
    dated = [f for f in ("start_date", "end_date") if body.get(f) is not None]
    ticked = [f for f in ("start_tick", "end_tick") if body.get(f) is not None]
    if dated and ticked:
        raise InvalidTimeframe(
            "Give a timeframe as ticks or as calendar dates, not both.",
            evidence={"given": sorted(dated + ticked)},
        )
    if dated:
        start, end = _parse_dated_timeframe(body, codec)
        fields = ("start_date", "end_date")
    else:
        start = _parse_tick(body.get("start_tick"), "start_tick")
        end = _parse_tick(body.get("end_tick"), "end_tick")
        fields = ("start_tick", "end_tick")
    if (start is None) != (end is None):
        raise InvalidTimeframe(
            f"Give both '{fields[0]}' and '{fields[1]}', or neither (an "
            "unscheduled scene). A half-known timeframe is not supported.",
            evidence={"start_tick": start, "end_tick": end},
        )
    if start is not None and start > end:
        raise InvalidTimeframe(
            f"start_tick ({start}) must not be after end_tick ({end}).",
            evidence={"start_tick": start, "end_tick": end},
        )
    return start, end


def validate_timeframe_payload(payload: Any, codec: TimeCodec) -> tuple[int | None, int | None]:
    """Just the timing half of an event body, for the scene form's live echo.

    Shares ``_parse_timeframe`` with the real write rather than approximating
    it, so a date the preview accepts is one the save will accept -- the same
    bargain the plotline editor's preview strikes.
    """
    return _parse_timeframe(_require_mapping(payload, InvalidTimeframe), codec)


def validate_event_payload(event_id: str, payload: Any, codec: TimeCodec) -> Event:
    """Parse an event body into the model, in the calendar it was written in.

    The codec is passed in rather than looked up: this stays a pure function of
    its arguments, so it tests against a literal descriptor with no book, no
    store and no app. It is also the only reason validation knows calendars
    exist at all -- the ``Event`` it returns carries ticks, like everything
    downstream of here.
    """
    body = _require_mapping(payload, InvalidEvent)
    if "location" not in body:
        raise InvalidEvent("An event requires a 'location'.")
    location = parse_entity_ref(body["location"], "location")
    start, end = _parse_timeframe(body, codec)
    title = body.get("title")
    if title is not None and not isinstance(title, str):
        raise InvalidEvent("'title' must be a string.")
    description = body.get("description", "")
    if not isinstance(description, str):
        raise InvalidEvent("'description' must be a string.")
    return Event(
        id=event_id,
        location=location,
        start_tick=start,
        end_tick=end,
        title=title,
        description=description,
        characters=_parse_ref_list(body.get("characters"), "characters"),
        items=_parse_ref_list(body.get("items"), "items"),
    )


def validate_plotline_payload(plotline_id: str, payload: Any) -> Plotline:
    body = _require_mapping(payload, InvalidPlotline)
    events = body.get("events")
    if not isinstance(events, list) or not events:
        raise InvalidPlotline("A plotline needs a non-empty ordered 'events' list.")
    if not all(isinstance(e, str) and e for e in events):
        raise InvalidPlotline("'events' must be a list of event ids.")
    # Goal *ids*, and optional: a thread is often drafted before the writer has
    # decided what it is for. Whether those goals exist is referential and is
    # checked where the book's goals can be read (see ``PlotlineService``); that
    # a thread serves none at all is reported, not refused (see ``goal_rules``).
    goals = _parse_id_list(body.get("goals"), "goals", InvalidPlotline)
    title = body.get("title")
    if title is not None and not isinstance(title, str):
        raise InvalidPlotline("'title' must be a string.")
    continues_into = body.get("continues_into")
    if continues_into is not None and not (isinstance(continues_into, str) and continues_into):
        raise InvalidPlotline("'continues_into' must be a plotline id string.")
    if continues_into == plotline_id:
        raise InvalidPlotline("A plotline cannot continue into itself.")
    continues_into_at = body.get("continues_into_at")
    if continues_into_at is not None and not (isinstance(continues_into_at, str) and continues_into_at):
        raise InvalidPlotline("'continues_into_at' must be an event id string.")
    # Structural, so it is caught here rather than at the service layer: a join
    # point names a scene *within a continuation*, so without one it describes
    # nothing at all. Whether the scene actually exists on that thread's path is
    # a referential question, and belongs where the siblings can be read.
    if continues_into_at is not None and continues_into is None:
        raise InvalidPlotline(
            "'continues_into_at' says where to join a continuation, so it needs a "
            "'continues_into' target."
        )
    return Plotline(
        id=plotline_id, events=list(events), goals=list(goals),
        title=title, continues_into=continues_into, continues_into_at=continues_into_at,
        overview=_parse_overview(body, InvalidPlotline),
    )


def validate_goal_payload(goal_id: str, payload: Any) -> Goal:
    """Parse a goal body into the model. The id comes from the URL.

    Structure only, as everywhere in this module: whether the dependencies and
    the achieving scene *exist* is referential, and belongs where the rest of
    the book can be read (see ``GoalService``). The one relational rule that
    needs nothing but the payload is settled here -- a goal cannot depend on
    itself, which is the one-hop case of the loop ``GoalCycle`` refuses.
    """
    body = _require_mapping(payload, InvalidGoal)
    title = body.get("title")
    if title is not None and not isinstance(title, str):
        raise InvalidGoal("'title' must be a string.")
    depends_on = _parse_id_list(body.get("depends_on"), "depends_on", InvalidGoal)
    if goal_id in depends_on:
        raise InvalidGoal(
            "A goal cannot depend on itself.", evidence={"goal": goal_id}
        )
    achieved_at = body.get("achieved_at")
    if achieved_at is not None and not (isinstance(achieved_at, str) and achieved_at):
        raise InvalidGoal("'achieved_at' must be an event id string.")
    return Goal(
        id=goal_id,
        title=title,
        description=_parse_prose(body, "description", InvalidGoal),
        depends_on=depends_on,
        achieved_at=achieved_at,
    )


_CALENDAR_KINDS = ("identity", "mixed_radix")


def _check_cycle(raw: Any, position: int) -> None:
    where = f"Calendar cycle {position}"
    if not isinstance(raw, dict):
        raise InvalidBook(f"{where} must be an object with a 'name' and a 'size'.")
    name = raw.get("name")
    if not (isinstance(name, str) and name.strip()):
        raise InvalidBook(f"{where} needs a non-empty 'name'.")
    size = raw.get("size")
    # bool is an int subclass but is not a cycle length.
    if isinstance(size, bool) or not isinstance(size, int):
        raise InvalidBook(f"Cycle '{name}' needs an integer 'size'.")
    if size < 1:
        raise InvalidBook(
            f"Cycle '{name}' must have a 'size' of at least 1.",
            evidence={"cycle": name, "size": size},
        )


def _check_calendar(raw: Any) -> None:
    """Structure-check a book's calendar descriptor against the published schema.

    ``codec_for`` builds a codec from this on *every* read, so a descriptor it
    cannot build has to be refused here, at the write. Otherwise the book is
    stored and each later read fails with an ``INVALID_TIMEFRAME`` complaint out
    of the codec -- which is both the wrong code and the wrong moment: nothing is
    wrong with the timeframe, and the mistake was made pages ago.

    Checks only; the descriptor is stored exactly as sent (design §4.1 leaves the
    vocabulary of cycle names open, so there is nothing to normalise).
    """
    if not isinstance(raw, dict):
        raise InvalidBook("'calendar' must be an object.")
    kind = raw.get("kind", "mixed_radix")
    if kind not in _CALENDAR_KINDS:
        raise InvalidBook(
            f"Unknown calendar kind {kind!r}.", evidence={"known": list(_CALENDAR_KINDS)}
        )
    if kind == "identity":
        return  # ticks display as themselves; nothing else is read
    base_unit = raw.get("base_unit", "tick")
    if not (isinstance(base_unit, str) and base_unit.strip()):
        raise InvalidBook("'base_unit' must be a non-empty string.")
    epoch_label = raw.get("epoch_label", "")
    if not isinstance(epoch_label, str):
        raise InvalidBook("'epoch_label' must be a string.")
    cycles = raw.get("cycles")
    if not isinstance(cycles, list) or not cycles:
        raise InvalidBook(
            "A calendar needs a non-empty 'cycles' list, ordered smallest first."
        )
    for position, cycle in enumerate(cycles, start=1):
        _check_cycle(cycle, position)


# A book keeps a handful of parallel reckonings, not an archive of them. Every
# attachment is copied into the document and returned in every book response, so
# the list is bounded for the same reason ``overview`` is.
MAX_CALENDARS = 8


def _check_era(raw: dict, where: str) -> tuple[int | None, int | None]:
    """The span of ticks a reckoning was kept in -- both ends optional."""
    bounds = []
    for field in ("from_tick", "until_tick"):
        value = raw.get(field)
        # bool is an int subclass but is not a tick.
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            raise InvalidBook(f"{where}: '{field}' must be an integer tick or null.")
        bounds.append(value)
    start, end = bounds
    if start is not None and end is not None and start >= end:
        raise InvalidBook(
            f"{where}: the calendar would end before it began.",
            evidence={"from_tick": start, "until_tick": end},
        )
    return start, end


def _check_source(raw: Any, where: str) -> dict:
    """Which library calendar this attachment takes its descriptor from.

    Required, and the whole of what a client may say about a calendar's
    *content*: the library is where calendars are authored, and a book chooses
    from it rather than inventing one inline. The descriptor itself is resolved
    server-side (see ``BookService._resolve_attachments``), so a book can never
    hold a calendar that is not in somebody's library, and never one that
    disagrees with the entry it claims to come from.

    Owner-qualified, because library ids are unique per writer: an unqualified
    pointer would let one writer's ``imperial`` be mistaken for another's.

    ``rev`` says which of two things the caller wants, and is never taken as
    fact: omit it to take the calendar as it stands, or send the revision this
    book already holds to keep that copy (see ``_resolve_attachments``). Either
    way the service stamps the revision it actually read.
    """
    if not isinstance(raw, dict):
        raise InvalidBook(
            f"{where}: needs a 'source' naming a calendar in the library. "
            "Books choose a calendar rather than describing one."
        )
    owner, calendar = raw.get("owner"), raw.get("calendar")
    if not (isinstance(owner, str) and owner and isinstance(calendar, str) and calendar):
        raise InvalidBook(f"{where}: 'source' needs an 'owner' and a 'calendar'.")
    rev = raw.get("rev")
    if rev is not None and (isinstance(rev, bool) or not isinstance(rev, int)):
        raise InvalidBook(f"{where}: 'source.rev' must be an integer or null.")
    return {"owner": owner, "calendar": calendar, "rev": rev}


def _parse_attachment(raw: Any, position: int, seen: set[str]) -> CalendarAttachment:
    where = f"Calendar {position}"
    if not isinstance(raw, dict):
        raise InvalidBook(f"{where} must be an object.")
    attachment_id = raw.get("id")
    if not (isinstance(attachment_id, str) and attachment_id.strip()):
        raise InvalidBook(f"{where} needs a non-empty 'id'.")
    attachment_id = attachment_id.strip()
    # Unique within the book: the id is what a read names to pick a reckoning,
    # so a duplicate would make that choice ambiguous rather than merely untidy.
    if attachment_id in seen:
        raise InvalidBook(
            f"Two calendars share the id '{attachment_id}'.",
            evidence={"calendar": attachment_id},
        )
    seen.add(attachment_id)
    label = raw.get("label", "")
    if not isinstance(label, str):
        raise InvalidBook(f"{where}: 'label' must be a string.")
    # A client names a library calendar; it does not describe one. Refused
    # rather than ignored: a body carrying a descriptor was written by someone
    # who expected it to be used, and silently substituting a different one is
    # worse than saying no. "Plain numbers" is not a calendar to describe --
    # it is a book with no attachments at all.
    if "descriptor" in raw:
        raise InvalidBook(
            f"{where}: a book cannot define a calendar inline. Name one from the "
            "library with 'source', or attach none at all for plain ticks.",
            evidence={"calendar": attachment_id},
        )
    from_tick, until_tick = _check_era(raw, where)
    return CalendarAttachment(
        id=attachment_id,
        # Filled in by the service from the library entry ``source`` names.
        descriptor=None,
        label=label,
        source=_check_source(raw.get("source"), where),
        from_tick=from_tick,
        until_tick=until_tick,
    )


def _parse_calendars(body: dict) -> list[CalendarAttachment]:
    """A book's attached reckonings, accepting the pre-library single field.

    Both spellings are read, but never together: a body carrying each is
    ambiguous about which the writer meant, and picking one silently is how a
    calendar goes missing without anything on screen to say so.
    """
    calendars, legacy = body.get("calendars"), body.get("calendar")
    if calendars is not None and legacy is not None:
        raise InvalidBook(
            "Send either 'calendars' or the older single 'calendar', not both."
        )
    if calendars is None:
        if legacy is None:
            return []
        _check_calendar(legacy)
        return [CalendarAttachment(id=DEFAULT_CALENDAR_ID, descriptor=legacy)]
    if not isinstance(calendars, list):
        raise InvalidBook("'calendars' must be a list.")
    if len(calendars) > MAX_CALENDARS:
        raise InvalidBook(
            f"A book may keep at most {MAX_CALENDARS} calendars.",
            evidence={"count": len(calendars), "max": MAX_CALENDARS},
        )
    seen: set[str] = set()
    return [_parse_attachment(raw, i, seen) for i, raw in enumerate(calendars, start=1)]


def validate_book_payload(book_id: str, payload: Any) -> Book:
    body = _require_mapping(payload, InvalidBook)
    title = body.get("title")
    if title is not None and not isinstance(title, str):
        raise InvalidBook("'title' must be a string.")
    terminus = body.get("terminus")
    if terminus is not None and not (isinstance(terminus, str) and terminus):
        raise InvalidBook("'terminus' must be an event id string.")
    calendars = _parse_calendars(body)
    world = body.get("world")
    if world is not None and not (isinstance(world, str) and world.strip()):
        raise InvalidBook("'world' must be an Akasha database name.")
    # Existence is *not* checked here. Whether the world is readable is the web
    # layer's business (it needs the request's identity), and a world that has
    # been renamed or revoked should leave the book readable with an empty
    # picker rather than un-loadable -- the same posture as a dangling EntityRef.
    return Book(
        id=book_id, title=title, terminus=terminus, calendars=calendars,
        world=world.strip() if world else None,
        overview=_parse_overview(body, InvalidBook),
    )


# -- the calendar library ----------------------------------------------------

MAX_CALENDAR_NAME = 200
MAX_CALENDAR_NOTES = 2_000


def validate_calendar_payload(calendar_id: str, payload: Any) -> LibraryCalendar:
    """A named, reusable calendar. The id comes from the URL; the owner from the
    session, so neither is read out of the body.

    The descriptor is checked by exactly the rule a book's own calendar faces
    (``_check_calendar``): a library that could store a descriptor no book could
    accept would hand the writer a calendar that fails when they try to use it.
    """
    body = _require_mapping(payload, InvalidCalendar)
    name = body.get("name")
    if not (isinstance(name, str) and name.strip()):
        raise InvalidCalendar("A calendar needs a non-empty 'name'.")
    if len(name) > MAX_CALENDAR_NAME:
        raise InvalidCalendar(f"'name' must be at most {MAX_CALENDAR_NAME} characters.")
    notes = body.get("notes", "")
    if not isinstance(notes, str):
        raise InvalidCalendar("'notes' must be a string.")
    if len(notes) > MAX_CALENDAR_NOTES:
        raise InvalidCalendar(f"'notes' must be at most {MAX_CALENDAR_NOTES} characters.")
    descriptor = body.get("descriptor")
    if descriptor is None:
        raise InvalidCalendar(
            "A library calendar needs a 'descriptor'. A book that wants plain "
            "numbers simply attaches no calendar."
        )
    try:
        _check_calendar(descriptor)
    except InvalidBook as bad:  # same rule, this resource's error code
        raise InvalidCalendar(bad.message, evidence=bad.evidence)
    return LibraryCalendar(
        id=calendar_id, name=name.strip(), descriptor=descriptor, notes=notes
    )
