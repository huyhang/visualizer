"""Payload validation and parsing (design §3) -- pure, no I/O.

Turns raw request bodies into domain models, raising the *referential* errors
(which are hard, §8.1). Entity *existence* is not checked here -- that is the
``EntityGate``'s job; this module only checks structure. The resource id comes
from the URL, so it is passed in rather than read from the body.
"""

from typing import Any

from .errors import InvalidBook, InvalidEvent, InvalidPlotline, InvalidTimeframe
from .models import Book, EntityRef, Event, Plotline


def _require_mapping(payload: Any, err) -> dict:
    if not isinstance(payload, dict):
        raise err("Request body must be a JSON object.")
    return payload


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


def _parse_timeframe(body: dict) -> tuple[int | None, int | None]:
    """Both ticks or neither -- a scene is fully scheduled or not at all.

    Half-known timing would multiply the cases every rule has to handle for
    little gain, so it is rejected rather than guessed at.
    """
    start = _parse_tick(body.get("start_tick"), "start_tick")
    end = _parse_tick(body.get("end_tick"), "end_tick")
    if (start is None) != (end is None):
        raise InvalidTimeframe(
            "Give both 'start_tick' and 'end_tick', or neither (an unscheduled "
            "scene). A half-known timeframe is not supported.",
            evidence={"start_tick": start, "end_tick": end},
        )
    if start is not None and start > end:
        raise InvalidTimeframe(
            f"start_tick ({start}) must not be after end_tick ({end}).",
            evidence={"start_tick": start, "end_tick": end},
        )
    return start, end


def validate_event_payload(event_id: str, payload: Any) -> Event:
    body = _require_mapping(payload, InvalidEvent)
    if "location" not in body:
        raise InvalidEvent("An event requires a 'location'.")
    location = parse_entity_ref(body["location"], "location")
    start, end = _parse_timeframe(body)
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
    goals = body.get("goals")
    if not isinstance(goals, list) or not goals:
        raise InvalidPlotline("A plotline needs a non-empty set of 'goals'.")
    if not all(isinstance(g, str) and g for g in goals):
        raise InvalidPlotline("'goals' must be a list of non-empty strings.")
    title = body.get("title")
    if title is not None and not isinstance(title, str):
        raise InvalidPlotline("'title' must be a string.")
    continues_into = body.get("continues_into")
    if continues_into is not None and not (isinstance(continues_into, str) and continues_into):
        raise InvalidPlotline("'continues_into' must be a plotline id string.")
    if continues_into == plotline_id:
        raise InvalidPlotline("A plotline cannot continue into itself.")
    return Plotline(
        id=plotline_id, events=list(events), goals=list(goals),
        title=title, continues_into=continues_into,
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


def validate_book_payload(book_id: str, payload: Any) -> Book:
    body = _require_mapping(payload, InvalidBook)
    title = body.get("title")
    if title is not None and not isinstance(title, str):
        raise InvalidBook("'title' must be a string.")
    terminus = body.get("terminus")
    if terminus is not None and not (isinstance(terminus, str) and terminus):
        raise InvalidBook("'terminus' must be an event id string.")
    calendar = body.get("calendar")
    if calendar is not None:
        _check_calendar(calendar)
    world = body.get("world")
    if world is not None and not (isinstance(world, str) and world.strip()):
        raise InvalidBook("'world' must be an Akasha database name.")
    # Existence is *not* checked here. Whether the world is readable is the web
    # layer's business (it needs the request's identity), and a world that has
    # been renamed or revoked should leave the book readable with an empty
    # picker rather than un-loadable -- the same posture as a dangling EntityRef.
    return Book(
        id=book_id, title=title, terminus=terminus, calendar=calendar,
        world=world.strip() if world else None,
    )
