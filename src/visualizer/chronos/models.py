"""Plain domain types, free of any I/O.

These dataclasses are what the pure logic (``conflicts``, ``ordering``,
``book_rules``) operates on, and what ``validation`` parses payloads into. They
are deliberately dumb: no persistence, no Flask, no validation beyond structure.
``EntityRef`` is frozen so it is hashable and compares by value -- exactly what
temporal-conflict location/character comparisons need.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EntityRef:
    """A reference to a document in akasha (character/item/location)."""

    database: str
    collection: str
    id: str

    def to_dict(self) -> dict:
        return {"database": self.database, "collection": self.collection, "id": self.id}


@dataclass
class Event:
    """A claim that these characters/items did something at a place and time."""

    id: str
    location: EntityRef
    start_tick: int | None
    end_tick: int | None
    title: str | None = None
    description: str = ""
    characters: list[EntityRef] = field(default_factory=list)
    items: list[EntityRef] = field(default_factory=list)

    @property
    def display_title(self) -> str:
        return self.title or self.id

    @property
    def is_scheduled(self) -> bool:
        """Whether this scene has been placed on the timeline yet.

        Drafting writers record scenes before they know when they happen; an
        unscheduled scene has no interval, so it cannot conflict with or be
        ordered against anything (see ``scheduling``).
        """
        return self.start_tick is not None and self.end_tick is not None

    def entity_refs(self) -> list[EntityRef]:
        """Every EntityRef this event references (for existence checks)."""
        return [self.location, *self.characters, *self.items]

    def to_storage(self) -> dict:
        return {
            "title": self.title,
            "location": self.location.to_dict(),
            "start_tick": self.start_tick,
            "end_tick": self.end_tick,
            "description": self.description,
            "characters": [c.to_dict() for c in self.characters],
            "items": [i.to_dict() for i in self.items],
        }

    @classmethod
    def from_storage(cls, doc: dict) -> "Event":
        return cls(
            id=doc["id"],
            title=doc.get("title"),
            location=EntityRef(**doc["location"]),
            start_tick=doc["start_tick"],
            end_tick=doc["end_tick"],
            description=doc.get("description", ""),
            characters=[EntityRef(**c) for c in doc.get("characters", [])],
            items=[EntityRef(**i) for i in doc.get("items", [])],
        )


@dataclass
class Plotline:
    """One thread: an ordered list of event ids plus the goals it serves.

    ``events`` is this plotline's *own* segment. When ``continues_into`` names
    another plotline, the thread carries on into it -- so a shared ending is
    stored once rather than repeated in every thread. See ``continuation``.
    """

    id: str
    events: list[str]
    # The ids of the ``Goal`` records in this book that this thread pursues. May
    # be empty: a thread is often drafted before the writer has decided what it
    # is for, and "serves no goal" is worth reporting rather than refusing.
    goals: list[str]
    title: str | None = None
    continues_into: str | None = None
    # Where in the continuation this thread joins: a scene in the target's
    # resolved path, or ``None`` for its first scene. A thread that catches up
    # with the trunk halfway needs this; without it the only way to say so was
    # to copy the trunk's opening scenes into ``events``, which is the edit
    # amplification ``continues_into`` exists to remove.
    continues_into_at: str | None = None
    # The writer's own prose about this thread. See ``Book.overview``.
    overview: str = ""

    @property
    def display_title(self) -> str:
        return self.title or self.id

    def to_storage(self) -> dict:
        return {
            "title": self.title,
            "events": list(self.events),
            "goals": list(self.goals),
            "continues_into": self.continues_into,
            "continues_into_at": self.continues_into_at,
            "overview": self.overview,
        }

    @classmethod
    def from_storage(cls, doc: dict) -> "Plotline":
        return cls(
            id=doc["id"],
            events=list(doc.get("events", [])),
            goals=list(doc.get("goals", [])),
            title=doc.get("title"),
            continues_into=doc.get("continues_into"),
            # Threads written before the field existed join at the head, which
            # is exactly what ``None`` means -- so no migration runs.
            continues_into_at=doc.get("continues_into_at"),
            overview=doc.get("overview", ""),
        )


@dataclass
class Goal:
    """Something the story is trying to bring about.

    A goal is what a thread is *for* -- ``Plotline.goals`` names these by id --
    and goals rest on one another: a coronation needs a claim proved first, so
    ``depends_on`` names the goals in this book that must be met before it.

    ``achieved_at`` is the single point where a goal touches the timeline: the
    scene that delivers it. Optional, because a goal is usually named long
    before the scene that pays it off has been written. Everything else a reader
    wants to know -- whether it is met, met too early, pursued by nobody -- is
    *computed* from those two fields (see ``goal_rules``) rather than stored, so
    each question has one answer instead of a stored one and a derived one that
    drift apart.
    """

    id: str
    title: str | None = None
    description: str = ""
    depends_on: list[str] = field(default_factory=list)
    achieved_at: str | None = None

    @property
    def display_title(self) -> str:
        return self.title or self.id

    def to_storage(self) -> dict:
        return {
            "title": self.title,
            "description": self.description,
            "depends_on": list(self.depends_on),
            "achieved_at": self.achieved_at,
        }

    @classmethod
    def from_storage(cls, doc: dict) -> "Goal":
        return cls(
            id=doc["id"],
            title=doc.get("title"),
            description=doc.get("description", ""),
            depends_on=list(doc.get("depends_on", [])),
            achieved_at=doc.get("achieved_at"),
        )


# What a legacy single-calendar book's one attachment is called once promoted.
# Books written before this field existed have exactly one calendar, so the id
# is never shown: the view switcher only appears when there is a choice to make.
DEFAULT_CALENDAR_ID = "default"


@dataclass
class LibraryCalendar:
    """A named, reusable calendar in a writer's library.

    Identity is ``(owner, id)``, not ``id`` alone -- calendar names are generic
    ("imperial", "lunar", "elvish") and every writer reaches for the same dozen
    words, so a global namespace would make the first writer to register one the
    owner of that word forever, and would tell the next writer that a calendar
    they cannot read exists. The owner lives on the record rather than in this
    dataclass's identity because the store supplies it (see ``CalendarStore``).

    A library entry is only ever *copied* into a book. Nothing here is on the
    read path of a book's dates.
    """

    id: str
    name: str
    descriptor: dict
    notes: str = ""

    def to_storage(self) -> dict:
        return {"name": self.name, "descriptor": self.descriptor, "notes": self.notes}

    @classmethod
    def from_storage(cls, doc: dict) -> "LibraryCalendar":
        return cls(
            id=doc["id"],
            name=doc.get("name", doc["id"]),
            descriptor=doc.get("descriptor") or {},
            notes=doc.get("notes", ""),
        )


@dataclass
class CalendarAttachment:
    """One reckoning a book keeps its dates in.

    The descriptor is **copied** into the book rather than referenced (see
    ``calendar.codec_for``); ``source`` records where the copy came from so an
    update can be offered explicitly, never applied behind the writer's back.
    A copy is also what keeps a book readable by anyone who can read the book --
    the labels are its own bytes, not another writer's record.

    ``from_tick``/``until_tick`` bound the era this reckoning was kept in, so a
    destroyed culture's calendar stops dating scenes that happened after it.
    ``origin`` is the same sort of story-local fact for a Gregorian calendar:
    which Earth moment this book's tick 0 was.
    """

    id: str
    descriptor: dict | None = None
    label: str = ""
    # {"owner": ..., "calendar": ..., "rev": ...} -- owner-qualified, because
    # library ids are unique per writer, not globally. An unqualified pointer
    # would let one writer's "imperial" offer to overwrite another's.
    source: dict | None = None
    from_tick: int | None = None
    until_tick: int | None = None
    # Which Earth moment this book's tick 0 was, for a Gregorian descriptor.
    # It lives here rather than in the library entry because it is the *story's*
    # alignment: two books may share one Earth calendar and sit centuries apart.
    origin: str | None = None

    @property
    def display_label(self) -> str:
        return self.label or self.id

    def to_storage(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "descriptor": self.descriptor,
            "source": self.source,
            "from_tick": self.from_tick,
            "until_tick": self.until_tick,
            "origin": self.origin,
        }

    @classmethod
    def from_storage(cls, doc: dict) -> "CalendarAttachment":
        return cls(
            id=doc["id"],
            descriptor=doc.get("descriptor"),
            label=doc.get("label", ""),
            source=doc.get("source"),
            from_tick=doc.get("from_tick"),
            until_tick=doc.get("until_tick"),
            origin=doc.get("origin"),
        )


@dataclass
class Book:
    """A collection of plotlines converging on one terminus event."""

    id: str
    title: str | None = None
    terminus: str | None = None
    # Ordered; the first is what the book reads through by default. Several at
    # once are the point -- parallel cultures reckoning one tick line.
    calendars: list[CalendarAttachment] = field(default_factory=list)
    # The Akasha database this book's cast and places live in. A *default* for
    # the article pickers, not a rule: an ``EntityRef`` still names its own
    # database, so a scene may reach into another world if the writer means it.
    # Without this a new book has nothing to search -- the scope could only be
    # inferred from scenes that do not exist yet (see ``dominant_database``).
    world: str | None = None
    # What this book is about, in the writer's own words. Free prose that no rule
    # reads -- it exists so a shelf of books, or a list of threads, says something
    # more than its title. Empty rather than null: "never written" and "written,
    # then cleared" are the same state, and one empty value is one fewer case for
    # every reader (and every form) to handle.
    overview: str = ""

    @property
    def calendar(self) -> dict | None:
        """The descriptor a single-calendar client still expects.

        Kept so every reader written before books could hold several calendars
        keeps working, and derived rather than stored: two copies of one fact is
        how they come to disagree.
        """
        return self.calendars[0].descriptor if self.calendars else None

    def to_storage(self) -> dict:
        return {
            "title": self.title,
            "terminus": self.terminus,
            "calendars": [c.to_storage() for c in self.calendars],
            "world": self.world,
            "overview": self.overview,
        }

    @classmethod
    def from_storage(cls, doc: dict) -> "Book":
        return cls(
            id=doc["id"],
            title=doc.get("title"),
            terminus=doc.get("terminus"),
            calendars=_calendars_from_storage(doc),
            world=doc.get("world"),
            # Books written before the field existed simply have none.
            overview=doc.get("overview", ""),
        )


def _calendars_from_storage(doc: dict) -> list[CalendarAttachment]:
    """A book's attachments, promoting a pre-library single ``calendar``.

    No migration runs: a book stored with the old field is read as a one-element
    list, and the next write puts it in the new shape. Promotion is deliberately
    one-way -- nothing writes ``calendar`` back -- so there is never a document
    carrying both spellings for a later reader to have to choose between.
    """
    stored = doc.get("calendars")
    if stored:
        return [CalendarAttachment.from_storage(c) for c in stored]
    legacy = doc.get("calendar")
    if legacy:
        return [CalendarAttachment(id=DEFAULT_CALENDAR_ID, descriptor=legacy)]
    return []
