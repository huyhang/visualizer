"""Small builders for courses, lessons and pictures, so each test says only
what it is about."""

from visualizer.tutorials.catalog import InMemoryCatalog
from visualizer.tutorials.lessons import Course, Lesson, Made, Note, Part, Step, Term
from visualizer.tutorials.shots import ManifestShots, Ring, Shot, Variant


def step(title="Do the thing", text=("Press `Go`.",), shot=None, alt="", note=None):
    return Step(title=title, text=tuple(text), shot=shot, alt=alt, note=note)


def lesson(slug, title=None, steps=None, **fields):
    return Lesson(
        slug=slug,
        title=title or slug.replace("-", " ").capitalize(),
        summary=fields.pop("summary", f"About {slug}."),
        lede=fields.pop("lede", "What this lesson is for."),
        steps=tuple(steps if steps is not None else [step()]),
        **fields,
    )


def course(*parts, prelude=None):
    return Course(
        title="From first article to first draft",
        lede="Short lessons, in order.",
        parts=tuple(parts),
        prelude=prelude,
    )


def part(slug, *lessons, mark="akasha"):
    return Part(
        slug=slug, kicker=f"Part · {slug}", title=slug.title(), blurb="What it covers.",
        mark=mark, lessons=tuple(lessons),
    )


def catalog(the_course, *lessons, terms=()):
    return InMemoryCatalog(the_course, {item.slug: item for item in lessons}, tuple(terms))


def shot(shot_id, ring=None, labels=()):
    rings = (ring,) if ring else ()
    return Shot(
        shot_id,
        desktop=Variant(1280, 640, 400, rings),
        phone=Variant(390, 390, 300, rings),
        labels=frozenset(labels),
    )


def shots(*items):
    return ManifestShots({item.id: item for item in items})


A_RING = Ring(left=10.0, top=20.0, width=30.0, height=5.0)

__all__ = [
    "A_RING", "Made", "Note", "Term", "catalog", "course", "lesson", "part", "shot",
    "shots", "step",
]
