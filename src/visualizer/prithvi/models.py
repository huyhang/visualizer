"""The few values Prithvi reasons about, with no I/O anywhere near them.

Four frozen types, all small enough to construct in a test without a fixture:
where an article lives, where a pin sits, the coordinate space it sits in, and
how far across that space is in the world's own units.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ArticleRef:
    """One Akasha article, addressed the way Akasha addresses it.

    ``world`` is an Akasha database. A pin never carries its own copy of this --
    it is read off the request path, so a pin cannot point outside the world its
    map belongs to.
    """

    world: str
    collection: str
    article_id: str

    def to_dict(self, *, title: str | None, status: str) -> dict:
        return {
            "database": self.world,
            "collection": self.collection,
            "id": self.article_id,
            "title": title,
            "status": status,
        }


@dataclass(frozen=True)
class Position:
    """A point in the map's own coordinate space, in ``viewBox`` units."""

    x: float
    y: float

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y}


@dataclass(frozen=True)
class ViewBox:
    """The rectangle an SVG declares as its coordinate space.

    Pins are validated against this and nothing else, which is why a map's
    ``viewBox`` is frozen for as long as it has pins: change the rectangle and
    every stored coordinate silently means somewhere different.
    """

    min_x: float
    min_y: float
    width: float
    height: float

    @property
    def max_x(self) -> float:
        return self.min_x + self.width

    @property
    def max_y(self) -> float:
        return self.min_y + self.height

    @property
    def smaller_side(self) -> float:
        return min(self.width, self.height)

    def contains(self, position: Position) -> bool:
        return (
            self.min_x <= position.x <= self.max_x
            and self.min_y <= position.y <= self.max_y
        )

    def to_list(self) -> list[float]:
        return [self.min_x, self.min_y, self.width, self.height]

    @classmethod
    def from_list(cls, value) -> "ViewBox":
        return cls(*(float(part) for part in value))


@dataclass(frozen=True)
class Scale:
    """How wide the map is in the world's own distance units.

    ``across`` is the real distance spanned by the ``viewBox`` width, so a pixel
    distance can be converted without knowing anything else about the drawing.
    Prithvi stores this and returns it; nothing in this service reads it. It is
    here because code is cheap to add later and measurements are not -- a scale
    backfilled onto a map drawn six months ago means someone deciding, again,
    how wide that coastline was meant to be.
    """

    across: float
    unit: str

    def to_dict(self) -> dict:
        return {"across": self.across, "unit": self.unit}
