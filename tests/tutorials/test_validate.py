"""Every rule a lesson keeps, each broken once."""

from tests.tutorials.factories import (
    Made,
    Term,
    catalog,
    course,
    lesson,
    part,
    shot,
    shots,
    step,
)
from visualizer.tutorials.lessons import Download
from visualizer.tutorials.validate import validate

TERMS = (Term("world", "A story's everything."),)


def problems(*lessons, library=None, terms=TERMS, **kwargs):
    the_course = course(part("p", *(item.slug for item in lessons)))
    found = validate(catalog(the_course, *lessons, terms=terms), library or shots(), **kwargs)
    return [str(problem) for problem in found]


def test_a_good_lesson_has_no_problems():
    good = lesson(
        "good",
        steps=[step(text=("Press `Go`. Then wait.",), shot="good/a", alt="The Go button")],
        made=Made("Done.", shot="good/b", alt="Done"),
        lede="Your {world}.",
    )
    assert problems(good, library=shots(shot("good/a", labels={"Go"}), shot("good/b"))) == []


def test_steps_are_kept_short():
    assert problems(lesson("none", steps=[])) == ["none: has 0 steps; 1 to 5 keep it short"]
    assert "six: has 6 steps" in problems(lesson("six", steps=[step()] * 6))[0]
    wordy = step(text=("One. Two.", "Three. Four."))
    assert problems(lesson("wordy", steps=[wordy])) == [
        "wordy, step 1: has 4 sentences; at most 3 -- split the step"
    ]


def test_a_picture_needs_alt_text_and_has_to_have_been_taken():
    found = problems(lesson("pics", steps=[step(shot="pics/a")]))
    assert "pics, step 1: shows pics/a without alt text" in found
    assert "pics: shows pics/a, which has not been taken" in found


def test_a_picture_nobody_shows_is_a_problem():
    found = problems(lesson("plain"), library=shots(shot("old/leftover")))
    assert found == ["pictures: old/leftover was taken but no lesson shows it"]


def test_a_lesson_only_needs_one_read_before_it():
    first, second = lesson("first", needs="second"), lesson("second", needs="first")
    assert problems(first, second) == ["first: needs 'second', which is not read before it"]


def test_a_glossary_link_needs_an_entry():
    found = problems(lesson("terms", lede="A {plotline} in a {world}."))
    assert found == ["terms: links {plotline}, which the glossary does not define"]


def test_a_lesson_may_not_take_a_path_the_app_serves():
    assert problems(lesson("glossary")) == ["glossary: is a path the tutorials serve themselves"]


def test_a_download_has_to_exist():
    offered = lesson("map", downloads=(Download("map.svg", "A sample map"),))
    assert problems(offered, download_exists=lambda name: False) == [
        "map: offers map.svg, which is not in static/downloads"
    ]
    assert problems(offered, download_exists=lambda name: True) == []


def test_a_quoted_label_must_have_been_on_screen_in_the_lesson_s_pictures():
    pictured = lesson("labels", steps=[step(text=("Press `Go`, then `Stop`.",), shot="l/a", alt="a")])
    seen = shot("l/a", labels={"Go", "Cancel"})
    assert problems(pictured, library=shots(seen)) == [
        "labels: quotes `Stop`, which none of its pictures show"
    ]


def test_labels_wait_until_the_pictures_are_taken():
    untaken = lesson("later", steps=[step(text=("Press `Go`.",), shot="l/b", alt="b")])
    assert problems(untaken) == ["later: shows l/b, which has not been taken"]


def test_a_lesson_the_course_names_but_the_catalog_lacks():
    the_course = course(part("p", "here", "gone"))
    found = validate(catalog(the_course, lesson("here")), shots())
    assert [str(p) for p in found] == ["course: names 'gone', which the catalog does not have"]
