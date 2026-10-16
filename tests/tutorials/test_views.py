"""What each page shows, decided before any template runs."""

from tests.tutorials.factories import (
    Made,
    catalog,
    course,
    lesson,
    part,
    shot,
    shots,
    step,
)
from visualizer.tutorials.views import (
    cover_of,
    hub_view,
    lesson_number,
    lesson_view,
    neighbours,
    reading_minutes,
)

COURSE = course(part("world", "home", "first"), part("draft", "write"), prelude="before")
CATALOG = catalog(
    COURSE,
    lesson("before", title="Before you start"),
    lesson("home", title="A home for your story", needs="before"),
    lesson(
        "first",
        title="Your first article",
        needs="home",
        steps=[step(shot="first/name", alt="Naming it"), step(shot="first/missing", alt="x")],
        made=Made("Your first article.", shot="first/made", alt="The article"),
    ),
    lesson("write", title="Start writing", optional=True),
)
SHOTS = shots(shot("first/name"), shot("first/made"))


def test_the_prelude_has_no_number_and_the_parts_count_from_one():
    assert lesson_number(COURSE, "before") is None
    assert [lesson_number(COURSE, slug) for slug in ("home", "first", "write")] == [1, 2, 3]


def test_neighbours_follow_reading_order_across_parts():
    assert neighbours(COURSE, "before") == (None, "home")
    assert neighbours(COURSE, "first") == ("home", "write")
    assert neighbours(COURSE, "write") == ("first", None)
    assert neighbours(COURSE, "nowhere") == (None, None)


def test_reading_time_counts_the_words_and_the_steps():
    short = lesson("short", steps=[step()])
    assert reading_minutes(short) == 1
    long = lesson("long", lede=" ".join(["word"] * 900), steps=[step()] * 4)
    # 923 words (the lede's 900, then titles and steps) at 180 a minute is 5.1,
    # and four steps at half a minute each: 7.1, so 8.
    assert reading_minutes(long) == 8


def test_a_lesson_view_has_its_place_its_pictures_and_its_way_on():
    view = lesson_view("first", CATALOG, SHOTS)
    assert (view.number, view.of, view.part.slug) == (2, 3, "world")
    assert view.steps[0].figure.alt == "Naming it"
    assert view.steps[1].figure is None  # not taken yet: the step still reads
    assert view.made.shot.id == "first/made"
    assert view.needs.title == "A home for your story"
    assert (view.previous.slug, view.next.slug) == ("home", "write")
    assert view.next.number == 3


def test_a_lesson_the_course_does_not_name_is_not_a_page():
    assert lesson_view("nowhere", CATALOG, SHOTS) is None


def test_a_card_shows_the_cover_then_what_it_makes_then_its_first_picture():
    first = CATALOG.lesson("first")
    assert cover_of(first, SHOTS).shot.id == "first/made"
    assert cover_of(first, shots(shot("first/name"))).shot.id == "first/name"
    assert cover_of(lesson("bare"), SHOTS) is None


def test_the_hub_has_the_prelude_apart_and_the_parts_in_order():
    hub = hub_view(CATALOG, SHOTS)
    assert hub.prelude.link.title == "Before you start"
    assert [[c.link.slug for c in view.cards] for view in hub.parts] == [["home", "first"], ["write"]]
    assert hub.count == 3
    assert hub.first.slug == "before"
    assert hub.parts[1].cards[0].optional
    assert hub.minutes == sum(
        c.minutes for view in hub.parts for c in view.cards
    ) + hub.prelude.minutes
