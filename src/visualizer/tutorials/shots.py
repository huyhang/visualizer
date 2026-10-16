"""The tutorials' pictures: what the camera writes, and what a page reads.

Every picture is taken at two widths and in both themes. The files live under
``static/shots/`` as ``<id>-<width>-<theme>.webp``; ``shots.json`` beside them
records each width's size and the rings that point at what to press. The
camera (``docker/tutorial_shots.py``) writes that file and this module reads
it, so its shape is defined here, once, on both sides.

A ring is a percentage of its picture rather than a mark drawn into it, so the
page draws it -- sharp at any size, in the theme's accent -- and the same ring
fits the light and the dark picture.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

# The desktop picture, and the phone one: the widths the camera's window takes.
DESKTOP = 1280
PHONE = 390
SIZES = (DESKTOP, PHONE)
THEMES = ("light", "dark")
# Below this the page shows the phone picture. The service nav's own
# breakpoint, so the picture changes when the app it shows does.
PHONE_BELOW = 821
# How far a ring stands off the thing it rings, in screen pixels.
RING_PAD = 5

SHOTS_DIR = Path(__file__).resolve().parent / "static" / "shots"
MANIFEST = SHOTS_DIR / "shots.json"


@dataclass(frozen=True)
class Box:
    """A rectangle on the screen, in CSS pixels, as Playwright reports one."""

    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class Ring:
    """Where to look, as percentages of the picture's width and height."""

    left: float
    top: float
    width: float
    height: float


@dataclass(frozen=True)
class Variant:
    """One width of a picture: its size, and its rings."""

    size: int
    width: int
    height: int
    rings: tuple[Ring, ...] = ()


@dataclass(frozen=True)
class Shot:
    id: str
    desktop: Variant
    phone: Variant
    # Every label on screen when it was taken, so a lesson can be held to
    # quoting only what is really there.
    labels: frozenset[str] = frozenset()


def shot_path(shot_id: str, size: int, theme: str) -> str:
    """A picture's file, relative to the app's static folder."""
    return f"shots/{shot_id}-{size}-{theme}.webp"


def ring_within(frame: Box, target: Box, pad: float = RING_PAD) -> Ring:
    """A ring around ``target``, as percentages of the picture cut at ``frame``."""
    return Ring(
        left=round((target.x - pad - frame.x) / frame.width * 100, 2),
        top=round((target.y - pad - frame.y) / frame.height * 100, 2),
        width=round((target.width + 2 * pad) / frame.width * 100, 2),
        height=round((target.height + 2 * pad) / frame.height * 100, 2),
    )


class ShotLibrary(Protocol):
    def shot(self, shot_id: str) -> Shot | None: ...

    def ids(self) -> frozenset[str]: ...


@dataclass(frozen=True)
class ManifestShots:
    """The pictures ``shots.json`` describes."""

    shots: Mapping[str, Shot] = field(default_factory=dict)

    def shot(self, shot_id: str) -> Shot | None:
        return self.shots.get(shot_id)

    def ids(self) -> frozenset[str]:
        return frozenset(self.shots)

    @classmethod
    def from_manifest(cls, manifest: Mapping) -> ManifestShots:
        return cls({shot_id: _shot(shot_id, entry) for shot_id, entry in manifest["shots"].items()})


def _shot(shot_id: str, entry: Mapping) -> Shot:
    return Shot(
        shot_id,
        desktop=_variant(DESKTOP, entry),
        phone=_variant(PHONE, entry),
        labels=frozenset(entry.get("labels", ())),
    )


def _variant(size: int, entry: Mapping) -> Variant:
    taken = entry[str(size)]
    return Variant(
        size=size,
        width=int(taken["width"]),
        height=int(taken["height"]),
        rings=tuple(Ring(**ring) for ring in taken.get("rings", ())),
    )


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_shots(path: Path = MANIFEST, read: Callable[[Path], str] = _read) -> ManifestShots:
    """The pictures on disk; none at all before the camera has first run."""
    try:
        return ManifestShots.from_manifest(json.loads(read(path)))
    except FileNotFoundError:
        return ManifestShots()


@dataclass
class ManifestBuilder:
    """What the camera has taken so far, as the manifest it will write."""

    entries: dict[str, dict[str, dict]] = field(default_factory=dict)

    def add(
        self,
        shot_id: str,
        size: int,
        picture: Box,
        rings: tuple[Ring, ...],
        labels: frozenset[str] = frozenset(),
    ) -> None:
        entry = self.entries.setdefault(shot_id, {})
        entry[str(size)] = {
            "width": round(picture.width),
            "height": round(picture.height),
            "rings": [ring.__dict__ for ring in rings],
        }
        entry["labels"] = sorted(set(entry.get("labels", ())) | labels)

    def manifest(self) -> dict:
        return {"version": 1, "sizes": list(SIZES), "themes": list(THEMES),
                "shots": dict(sorted(self.entries.items()))}

    def json(self) -> str:
        return json.dumps(self.manifest(), indent=1) + "\n"
