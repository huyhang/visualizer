"""I/O-free records for a manuscript outline, its volumes and its sections.

Three records, each owning exactly one thing. The outline owns the order of
volumes; a volume owns the order of its sections; a section owns its prose.
Nothing that can be derived is stored -- numbers, counts and links are computed
on read, so reordering cannot leave stale metadata behind.
"""

from dataclasses import dataclass, field


@dataclass
class Outline:
    """The volume order for one Chronos book."""

    book: str
    volumes: list[str] = field(default_factory=list)

    def to_storage(self) -> dict:
        return {"volumes": list(self.volumes)}

    @classmethod
    def from_storage(cls, record: dict) -> "Outline":
        return cls(book=record["book"], volumes=list(record.get("volumes", [])))


@dataclass
class Volume:
    id: str
    title: str
    overview: str = ""
    sections: list[str] = field(default_factory=list)

    def to_storage(self) -> dict:
        return {
            "title": self.title,
            "overview": self.overview,
            "sections": list(self.sections),
        }

    @classmethod
    def from_storage(cls, record: dict) -> "Volume":
        return cls(
            id=record["volume"],
            title=record["title"],
            overview=record.get("overview", ""),
            sections=list(record.get("sections", [])),
        )


@dataclass
class Section:
    id: str
    kind: str
    document: dict
    title: str | None = None
    overview: str = ""
    event_ids: list[str] = field(default_factory=list)

    def to_storage(self) -> dict:
        return {
            "kind": self.kind,
            "title": self.title,
            "overview": self.overview,
            "event_ids": list(self.event_ids),
            "document": self.document,
        }

    @classmethod
    def from_storage(cls, record: dict) -> "Section":
        return cls(
            id=record["section"],
            kind=record["kind"],
            title=record.get("title"),
            overview=record.get("overview", ""),
            event_ids=list(record.get("event_ids", [])),
            document=record["document"],
        )
