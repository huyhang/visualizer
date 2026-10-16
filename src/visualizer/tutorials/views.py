"""What each page shows, worked out before a template sees it.

Pure functions from a catalog and a shot library to plain values: the lesson's
number, its reading time, the lessons either side, which pictures exist. A
template only lays these out, so every decision here is tested without a
request.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .catalog import LessonCatalog
from .inline import word_count
from .lessons import Course, Lesson, Part, Step, Term
from .shots import Shot, ShotLibrary

# Reading pace for instructions, slower than prose; and the time to do a step.
WORDS_PER_MINUTE = 180
MINUTES_PER_STEP = 0.5


@dataclass(frozen=True)
class Figure:
    shot: Shot
    alt: str


@dataclass(frozen=True)
class LessonLink:
    slug: str
    title: str
    summary: str
    number: int | None


@dataclass(frozen=True)
class StepView:
    number: int
    step: Step
    figure: Figure | None


@dataclass(frozen=True)
class LessonView:
    lesson: Lesson
    part: Part | None
    number: int | None
    of: int
    minutes: int
    steps: tuple[StepView, ...]
    made: Figure | None
    needs: LessonLink | None
    previous: LessonLink | None
    next: LessonLink | None


@dataclass(frozen=True)
class Card:
    link: LessonLink
    minutes: int
    optional: bool
    cover: Figure | None


@dataclass(frozen=True)
class PartView:
    part: Part
    cards: tuple[Card, ...]


@dataclass(frozen=True)
class HubView:
    course: Course
    prelude: Card | None
    parts: tuple[PartView, ...]
    count: int
    minutes: int
    first: LessonLink | None


def reading_minutes(lesson: Lesson) -> int:
    """How long a lesson takes: reading it, and doing its steps."""
    words = sum(word_count(text) for text in lesson.texts())
    return max(1, math.ceil(words / WORDS_PER_MINUTE + MINUTES_PER_STEP * len(lesson.steps)))


def lesson_number(course: Course, slug: str) -> int | None:
    """A lesson's place among the numbered ones; the prelude has none."""
    numbered = course.numbered()
    return numbered.index(slug) + 1 if slug in numbered else None


def neighbours(course: Course, slug: str) -> tuple[str | None, str | None]:
    """The lessons read before and after ``slug``."""
    order = course.order()
    if slug not in order:
        return None, None
    at = order.index(slug)
    return (order[at - 1] if at > 0 else None, order[at + 1] if at + 1 < len(order) else None)


def link_to(catalog: LessonCatalog, slug: str | None) -> LessonLink | None:
    lesson = catalog.lesson(slug) if slug else None
    if lesson is None:
        return None
    return LessonLink(lesson.slug, lesson.title, lesson.summary, lesson_number(catalog.course(), slug))


def figure(shots: ShotLibrary, shot_id: str | None, alt: str) -> Figure | None:
    shot = shots.shot(shot_id) if shot_id else None
    return Figure(shot, alt) if shot else None


def cover_of(lesson: Lesson, shots: ShotLibrary) -> Figure | None:
    """The picture on a lesson's card: its chosen cover, what it makes, or its first step."""
    candidates = [lesson.cover, lesson.made.shot if lesson.made else None]
    candidates += [step.shot for step in lesson.steps]
    for shot_id in candidates:
        found = figure(shots, shot_id, "")
        if found:
            return found
    return None


def card(catalog: LessonCatalog, shots: ShotLibrary, slug: str) -> Card:
    lesson = catalog.lesson(slug)
    assert lesson is not None, f"the catalog has no lesson {slug!r}"
    return Card(link_to(catalog, slug), reading_minutes(lesson), lesson.optional, cover_of(lesson, shots))


def hub_view(catalog: LessonCatalog, shots: ShotLibrary) -> HubView:
    course = catalog.course()
    parts = tuple(
        PartView(part, tuple(card(catalog, shots, slug) for slug in part.lessons))
        for part in course.parts
    )
    prelude = card(catalog, shots, course.prelude) if course.prelude else None
    cards = [c for view in parts for c in view.cards] + ([prelude] if prelude else [])
    return HubView(
        course=course,
        prelude=prelude,
        parts=parts,
        count=len(course.numbered()),
        minutes=sum(c.minutes for c in cards),
        first=link_to(catalog, course.order()[0]),
    )


def lesson_view(slug: str, catalog: LessonCatalog, shots: ShotLibrary) -> LessonView | None:
    lesson = catalog.lesson(slug)
    course = catalog.course()
    if lesson is None or slug not in course.order():
        return None
    before, after = neighbours(course, slug)
    return LessonView(
        lesson=lesson,
        part=course.part_of(slug),
        number=lesson_number(course, slug),
        of=len(course.numbered()),
        minutes=reading_minutes(lesson),
        steps=tuple(
            StepView(number, step, figure(shots, step.shot, step.alt))
            for number, step in enumerate(lesson.steps, 1)
        ),
        made=figure(shots, lesson.made.shot, lesson.made.alt) if lesson.made else None,
        needs=link_to(catalog, lesson.needs),
        previous=link_to(catalog, before),
        next=link_to(catalog, after),
    )


def glossary_view(catalog: LessonCatalog) -> tuple[Term, ...]:
    return tuple(sorted(catalog.glossary(), key=lambda term: term.word.lower()))
