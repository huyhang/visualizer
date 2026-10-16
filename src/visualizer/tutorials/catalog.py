"""Where the app finds its lessons: a protocol, and the files that satisfy it.

The app is handed a ``LessonCatalog`` and never opens a file itself. The one on
disk is read once, by ``load_catalog``, which is handed the directory and the
function that reads it -- so a test passes a dict, and a broken file fails the
stack's start rather than the page that shows it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .lessons import (
    Course,
    Lesson,
    LessonError,
    Term,
    parse_course,
    parse_glossary,
    parse_lesson,
)

LESSONS_DIR = Path(__file__).resolve().parent / "lessons"


class LessonCatalog(Protocol):
    def course(self) -> Course: ...

    def lesson(self, slug: str) -> Lesson | None: ...

    def glossary(self) -> tuple[Term, ...]: ...


@dataclass(frozen=True)
class InMemoryCatalog:
    """A course, its lessons and its glossary, already parsed."""

    the_course: Course
    lessons: Mapping[str, Lesson]
    terms: tuple[Term, ...] = field(default=())

    def course(self) -> Course:
        return self.the_course

    def lesson(self, slug: str) -> Lesson | None:
        return self.lessons.get(slug)

    def glossary(self) -> tuple[Term, ...]:
        return self.terms


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_catalog(directory: Path = LESSONS_DIR, read: Callable[[Path], str] = _read) -> InMemoryCatalog:
    """Every file the course names, read and parsed once.

    ``course.toml`` names the lessons; each is ``<slug>.toml`` beside it, and
    ``glossary.toml`` holds the words they define.
    """
    course = parse_course(read(directory / "course.toml"))
    lessons = {}
    for slug in course.order():
        try:
            text = read(directory / f"{slug}.toml")
        except FileNotFoundError:
            raise LessonError(f"course.toml names {slug!r}, which has no {slug}.toml") from None
        lessons[slug] = parse_lesson(slug, text)
    return InMemoryCatalog(course, lessons, parse_glossary(read(directory / "glossary.toml")))
