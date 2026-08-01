"""Where an unscheduled scene *could* go (design §4.2) -- pure, no I/O.

A writer sketching a thread often knows the order of scenes long before their
timing. Because a plotline already encodes order, the scenes around an
unscheduled one constrain it: it must start after its nearest scheduled
predecessor ends, and end before its nearest scheduled successor begins.

That turns "I haven't decided yet" from a gap into guidance. It also catches
something no other rule can: when the surrounding scenes leave **no room at
all**, there is no valid time for the scene, and that is a real contradiction
even though nothing is out of order within any single thread.
"""

from dataclasses import dataclass

from .models import Event


@dataclass
class Window:
    """The tick range an unscheduled scene must fall inside.

    ``None`` on either side means unconstrained in that direction -- no
    scheduled neighbour pins it down yet.
    """

    earliest: int | None = None
    latest: int | None = None

    @property
    def impossible(self) -> bool:
        """True when the surrounding scenes leave no room for this one."""
        return (
            self.earliest is not None
            and self.latest is not None
            and self.earliest > self.latest
        )

    @property
    def unconstrained(self) -> bool:
        return self.earliest is None and self.latest is None


def _bounds_in_path(
    path: list[str], event_id: str, by_id: dict[str, Event]
) -> tuple[int | None, int | None]:
    """Nearest scheduled predecessor's end and successor's start within one path."""
    if event_id not in path:
        return None, None
    index = path.index(event_id)

    before = None
    for eid in reversed(path[:index]):
        event = by_id.get(eid)
        if event is not None and event.is_scheduled:
            before = event.end_tick
            break

    after = None
    for eid in path[index + 1 :]:
        event = by_id.get(eid)
        if event is not None and event.is_scheduled:
            after = event.start_tick
            break

    return before, after


def window_for(
    event_id: str, paths: dict[str, list[str]], by_id: dict[str, Event]
) -> Window:
    """The tightest window implied by every plotline this scene appears in.

    Constraints from different threads compound: the latest lower bound and the
    earliest upper bound both apply.
    """
    lower: list[int] = []
    upper: list[int] = []
    for path in paths.values():
        before, after = _bounds_in_path(path, event_id, by_id)
        if before is not None:
            lower.append(before)
        if after is not None:
            upper.append(after)
    return Window(
        earliest=max(lower) if lower else None,
        latest=min(upper) if upper else None,
    )


def unscheduled_windows(
    events: list[Event], paths: dict[str, list[str]]
) -> dict[str, Window]:
    """Every unscheduled scene in the book, with the window it must fall inside."""
    by_id = {e.id: e for e in events}
    return {
        event.id: window_for(event.id, paths, by_id)
        for event in events
        if not event.is_scheduled
    }
