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
    """One thread: an ordered list of event ids plus a non-empty set of goals.

    ``events`` is this plotline's *own* segment. When ``continues_into`` names
    another plotline, the thread carries on into it -- so a shared ending is
    stored once rather than repeated in every thread. See ``continuation``.
    """

    id: str
    events: list[str]
    goals: list[str]
    title: str | None = None
    continues_into: str | None = None

    @property
    def display_title(self) -> str:
        return self.title or self.id

    def to_storage(self) -> dict:
        return {
            "title": self.title,
            "events": list(self.events),
            "goals": list(self.goals),
            "continues_into": self.continues_into,
        }

    @classmethod
    def from_storage(cls, doc: dict) -> "Plotline":
        return cls(
            id=doc["id"],
            events=list(doc.get("events", [])),
            goals=list(doc.get("goals", [])),
            title=doc.get("title"),
            continues_into=doc.get("continues_into"),
        )


@dataclass
class Book:
    """A collection of plotlines converging on one terminus event."""

    id: str
    title: str | None = None
    terminus: str | None = None
    calendar: dict | None = None
    # The Akasha database this book's cast and places live in. A *default* for
    # the article pickers, not a rule: an ``EntityRef`` still names its own
    # database, so a scene may reach into another world if the writer means it.
    # Without this a new book has nothing to search -- the scope could only be
    # inferred from scenes that do not exist yet (see ``dominant_database``).
    world: str | None = None

    def to_storage(self) -> dict:
        return {
            "title": self.title,
            "terminus": self.terminus,
            "calendar": self.calendar,
            "world": self.world,
        }

    @classmethod
    def from_storage(cls, doc: dict) -> "Book":
        return cls(
            id=doc["id"],
            title=doc.get("title"),
            terminus=doc.get("terminus"),
            calendar=doc.get("calendar"),
            world=doc.get("world"),
        )
