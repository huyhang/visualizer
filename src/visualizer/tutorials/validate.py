"""The rules a lesson keeps, checked rather than hoped for.

``validate`` lists every way the catalog and its pictures break the rules the
tutorials are written to; a test asserts the list is empty. So a step that
grows a fourth sentence, a picture nobody took, a picture nobody shows, a
lesson that needs one the reader has not reached, a label quoted that was not
on screen, or a glossary word with no entry fails the build instead of
reaching a reader.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .catalog import LessonCatalog
from .inline import labels_in, sentence_count, terms_in
from .lessons import Lesson, term_slug
from .shots import ShotLibrary

MAX_STEPS = 5
MAX_SENTENCES = 3
# Paths the app serves itself, which no lesson may be called.
RESERVED = frozenset({"glossary", "static", "login", "logout", "register", "change-password"})


@dataclass(frozen=True)
class Problem:
    where: str
    what: str

    def __str__(self) -> str:
        return f"{self.where}: {self.what}"


def validate(
    catalog: LessonCatalog,
    shots: ShotLibrary,
    download_exists: Callable[[str], bool] = lambda _file: True,
) -> list[Problem]:
    lessons = [catalog.lesson(slug) for slug in catalog.course().order()]
    present = [lesson for lesson in lessons if lesson is not None]
    known_terms = {term.slug for term in catalog.glossary()}
    problems = list(_missing(catalog))
    problems += _reserved(present)
    for lesson in present:
        problems += _steps(lesson)
        problems += _pictures(lesson, shots)
        problems += _labels(lesson, shots)
        problems += _terms(lesson, known_terms)
        problems += _downloads(lesson, download_exists)
    problems += _needs(present)
    problems += _unshown(present, shots)
    return problems


def _missing(catalog: LessonCatalog) -> Iterable[Problem]:
    for slug in catalog.course().order():
        if catalog.lesson(slug) is None:
            yield Problem("course", f"names {slug!r}, which the catalog does not have")


def _reserved(lessons: list[Lesson]) -> Iterable[Problem]:
    for lesson in lessons:
        if lesson.slug in RESERVED:
            yield Problem(lesson.slug, "is a path the tutorials serve themselves")


def _steps(lesson: Lesson) -> Iterable[Problem]:
    if not 1 <= len(lesson.steps) <= MAX_STEPS:
        yield Problem(lesson.slug, f"has {len(lesson.steps)} steps; 1 to {MAX_STEPS} keep it short")
    for number, step in enumerate(lesson.steps, 1):
        sentences = sum(sentence_count(text) for text in step.text)
        if sentences > MAX_SENTENCES:
            yield Problem(
                f"{lesson.slug}, step {number}",
                f"has {sentences} sentences; at most {MAX_SENTENCES} -- split the step",
            )


def _pictures(lesson: Lesson, shots: ShotLibrary) -> Iterable[Problem]:
    shown = [(f"step {n}", step.shot, step.alt) for n, step in enumerate(lesson.steps, 1)]
    if lesson.made:
        shown.append(("made", lesson.made.shot, lesson.made.alt))
    for place, shot_id, alt in shown:
        if shot_id and not alt:
            yield Problem(f"{lesson.slug}, {place}", f"shows {shot_id} without alt text")
    for shot_id in lesson.shot_ids():
        if shots.shot(shot_id) is None:
            yield Problem(lesson.slug, f"shows {shot_id}, which has not been taken")


def _labels(lesson: Lesson, shots: ShotLibrary) -> Iterable[Problem]:
    """A label a lesson quotes was on screen in one of its own pictures.

    Checked against what the camera saw rather than against the source, where
    labels are assembled ("＋ New " + the word for an article) and never appear
    whole. A lesson whose pictures are not taken yet is reported for that
    instead, so its labels are not checked against nothing.
    """
    taken = [shots.shot(shot_id) for shot_id in lesson.shot_ids()]
    if not taken or None in taken:
        return
    seen = frozenset().union(*(shot.labels for shot in taken))
    quoted = dict.fromkeys(label for text in lesson.texts() for label in labels_in(text))
    for label in quoted:
        if label not in seen:
            yield Problem(lesson.slug, f"quotes `{label}`, which none of its pictures show")


def _terms(lesson: Lesson, known: set[str]) -> Iterable[Problem]:
    for text in lesson.texts():
        for term in terms_in(text):
            if term_slug(term) not in known:
                yield Problem(lesson.slug, f"links {{{term}}}, which the glossary does not define")


def _downloads(lesson: Lesson, exists: Callable[[str], bool]) -> Iterable[Problem]:
    for download in lesson.downloads:
        if not exists(download.file):
            yield Problem(lesson.slug, f"offers {download.file}, which is not in static/downloads")


def _needs(lessons: list[Lesson]) -> Iterable[Problem]:
    seen: set[str] = set()
    for lesson in lessons:
        if lesson.needs and lesson.needs not in seen:
            yield Problem(lesson.slug, f"needs {lesson.needs!r}, which is not read before it")
        seen.add(lesson.slug)


def _unshown(lessons: list[Lesson], shots: ShotLibrary) -> Iterable[Problem]:
    shown = {shot_id for lesson in lessons for shot_id in lesson.shot_ids()}
    for shot_id in sorted(shots.ids() - shown):
        yield Problem("pictures", f"{shot_id} was taken but no lesson shows it")
