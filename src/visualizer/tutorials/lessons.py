"""What the tutorials are made of, and how their files become it.

The course, each lesson and the glossary are TOML files under ``lessons/``,
read by the standard library. TOML rather than Markdown on purpose: a fixed
shape is what makes every lesson look alike, and nothing in a file can inject
markup -- ``inline.py`` escapes everything first and knows three marks.

A file that does not have the expected shape -- a missing title, a misspelt
key, a note of a kind nobody draws -- is a ``LessonError`` naming the file and
the place, raised when the catalog is loaded rather than discovered on a page.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from typing import Any

NOTE_KINDS = ("tip", "good-to-know", "if")


class LessonError(ValueError):
    """A course, lesson or glossary file without the expected shape."""


@dataclass(frozen=True)
class Note:
    """An aside under a step: a tip, something good to know, or "if this looks different"."""

    kind: str
    text: str


@dataclass(frozen=True)
class Step:
    title: str
    text: tuple[str, ...]
    shot: str | None = None
    alt: str = ""
    note: Note | None = None


@dataclass(frozen=True)
class Made:
    """What the writer has at the end of a lesson."""

    text: str
    shot: str | None = None
    alt: str = ""


@dataclass(frozen=True)
class Download:
    """A file a lesson offers, from ``static/downloads/``."""

    file: str
    label: str


@dataclass(frozen=True)
class Lesson:
    slug: str
    title: str
    summary: str
    lede: str
    steps: tuple[Step, ...]
    needs: str | None = None
    made: Made | None = None
    optional: bool = False
    downloads: tuple[Download, ...] = ()
    cover: str | None = None

    def shot_ids(self) -> tuple[str, ...]:
        """Every picture this lesson shows, in order."""
        named = [step.shot for step in self.steps]
        named += [self.made.shot if self.made else None, self.cover]
        return tuple(dict.fromkeys(shot for shot in named if shot))

    def texts(self) -> tuple[str, ...]:
        """Every passage a reader sees, for the checks that read them all."""
        found = [self.title, self.summary, self.lede]
        for step in self.steps:
            found += [step.title, *step.text]
            found += [step.note.text] if step.note else []
        found += [self.made.text] if self.made else []
        return tuple(found)


@dataclass(frozen=True)
class Part:
    slug: str
    kicker: str
    title: str
    blurb: str
    mark: str
    lessons: tuple[str, ...]


@dataclass(frozen=True)
class Course:
    title: str
    lede: str
    parts: tuple[Part, ...]
    prelude: str | None = None

    def numbered(self) -> tuple[str, ...]:
        """The lessons of every part, in order: the ones that get a number."""
        return tuple(slug for part in self.parts for slug in part.lessons)

    def order(self) -> tuple[str, ...]:
        """Every lesson in reading order, the unnumbered prelude first."""
        return ((self.prelude,) if self.prelude else ()) + self.numbered()

    def part_of(self, slug: str) -> Part | None:
        return next((part for part in self.parts if slug in part.lessons), None)


@dataclass(frozen=True)
class Term:
    word: str
    meaning: str

    @property
    def slug(self) -> str:
        return term_slug(self.word)


def term_slug(word: str) -> str:
    """The glossary anchor for a word: "Plotline" and "plotline" are one term."""
    return re.sub(r"[^a-z0-9]+", "-", word.lower()).strip("-")


# -- parsing ---------------------------------------------------------------------


def parse_course(text: str, where: str = "course.toml") -> Course:
    table = _load(text, where)
    _only(table, {"title", "lede", "prelude", "parts"}, where)
    parts = tuple(
        _part(part, f"{where}, part {index}")
        for index, part in enumerate(_tables(table, "parts", where), 1)
    )
    if not parts:
        raise LessonError(f"{where}: a course needs at least one part")
    return Course(
        title=_text(table, "title", where),
        lede=_text(table, "lede", where),
        parts=parts,
        prelude=_optional_text(table, "prelude", where),
    )


def parse_lesson(slug: str, text: str) -> Lesson:
    where = f"{slug}.toml"
    table = _load(text, where)
    _only(
        table,
        {"title", "summary", "lede", "needs", "optional", "cover", "steps", "made", "downloads"},
        where,
    )
    steps = tuple(
        _step(step, f"{where}, step {index}")
        for index, step in enumerate(_tables(table, "steps", where), 1)
    )
    return Lesson(
        slug=slug,
        title=_text(table, "title", where),
        summary=_text(table, "summary", where),
        lede=_text(table, "lede", where),
        steps=steps,
        needs=_optional_text(table, "needs", where),
        made=_made(table["made"], f"{where}, made") if "made" in table else None,
        optional=_flag(table, "optional", where),
        downloads=tuple(
            _download(item, f"{where}, download {index}")
            for index, item in enumerate(_tables(table, "downloads", where), 1)
        ),
        cover=_optional_text(table, "cover", where),
    )


def parse_glossary(text: str, where: str = "glossary.toml") -> tuple[Term, ...]:
    table = _load(text, where)
    _only(table, {"terms"}, where)
    terms = []
    for index, item in enumerate(_tables(table, "terms", where), 1):
        place = f"{where}, term {index}"
        _only(item, {"word", "meaning"}, place)
        terms.append(Term(word=_text(item, "word", place), meaning=_text(item, "meaning", place)))
    return tuple(terms)


def _part(table: dict, where: str) -> Part:
    _only(table, {"slug", "kicker", "title", "blurb", "mark", "lessons"}, where)
    lessons = _texts(table, "lessons", where)
    if not lessons:
        raise LessonError(f"{where}: a part needs at least one lesson")
    return Part(
        slug=_text(table, "slug", where),
        kicker=_text(table, "kicker", where),
        title=_text(table, "title", where),
        blurb=_text(table, "blurb", where),
        mark=_text(table, "mark", where),
        lessons=lessons,
    )


def _step(table: dict, where: str) -> Step:
    _only(table, {"title", "text", "shot", "alt", "note"}, where)
    return Step(
        title=_text(table, "title", where),
        text=_texts(table, "text", where, required=True),
        shot=_optional_text(table, "shot", where),
        alt=_optional_text(table, "alt", where) or "",
        note=_note(table["note"], f"{where}, note") if "note" in table else None,
    )


def _note(value: Any, where: str) -> Note:
    table = _as_table(value, where)
    _only(table, {"kind", "text"}, where)
    kind = _text(table, "kind", where)
    if kind not in NOTE_KINDS:
        raise LessonError(f"{where}: kind {kind!r} is not one of {', '.join(NOTE_KINDS)}")
    return Note(kind=kind, text=_text(table, "text", where))


def _made(value: Any, where: str) -> Made:
    table = _as_table(value, where)
    _only(table, {"text", "shot", "alt"}, where)
    return Made(
        text=_text(table, "text", where),
        shot=_optional_text(table, "shot", where),
        alt=_optional_text(table, "alt", where) or "",
    )


def _download(table: dict, where: str) -> Download:
    _only(table, {"file", "label"}, where)
    return Download(file=_text(table, "file", where), label=_text(table, "label", where))


# -- the shape of a value ----------------------------------------------------------


def _load(text: str, where: str) -> dict:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as err:
        raise LessonError(f"{where}: {err}") from None


def _only(table: dict, allowed: set[str], where: str) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise LessonError(f"{where}: unexpected {', '.join(unknown)}")


def _as_table(value: Any, where: str) -> dict:
    if not isinstance(value, dict):
        raise LessonError(f"{where}: expected a table")
    return value


def _tables(table: dict, key: str, where: str) -> list[dict]:
    items = table.get(key, [])
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise LessonError(f"{where}: {key} must be a list of tables")
    return items


def _text(table: dict, key: str, where: str) -> str:
    value = _optional_text(table, key, where)
    if value is None:
        raise LessonError(f"{where}: {key} is required")
    return value


def _optional_text(table: dict, key: str, where: str) -> str | None:
    value = table.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise LessonError(f"{where}: {key} must be non-empty text")
    return value.strip()


def _texts(table: dict, key: str, where: str, required: bool = False) -> tuple[str, ...]:
    """A passage or a list of them: one string is a one-item list."""
    value = table.get(key, [])
    items = [value] if isinstance(value, str) else value
    if not isinstance(items, list) or not all(
        isinstance(item, str) and item.strip() for item in items
    ):
        raise LessonError(f"{where}: {key} must be text or a list of text")
    if required and not items:
        raise LessonError(f"{where}: {key} is required")
    return tuple(item.strip() for item in items)


def _flag(table: dict, key: str, where: str) -> bool:
    value = table.get(key, False)
    if not isinstance(value, bool):
        raise LessonError(f"{where}: {key} must be true or false")
    return value
