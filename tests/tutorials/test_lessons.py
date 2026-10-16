"""Lesson, course and glossary files become values, or say exactly what is wrong."""

import pytest

from visualizer.tutorials.lessons import (
    LessonError,
    Note,
    parse_course,
    parse_glossary,
    parse_lesson,
    term_slug,
)

LESSON = """
title = "Your first article"
summary = "Write a page for your main character."
lede = "An {article} is one page about one thing."
needs = "a-home"

[[steps]]
title = "Give it a name"
text = "Type a name into **Title**, then press `Continue`."
shot = "first/name-it"
alt = "The New article dialog"
note = { kind = "tip", text = "The slug fills itself in." }

[[steps]]
title = "Write"
text = ["One line.", "Another line."]

[made]
text = "Your first article."
shot = "first/made"
alt = "The finished article"
"""


def test_a_lesson_reads_into_steps_notes_and_what_it_makes():
    lesson = parse_lesson("first", LESSON)
    assert lesson.title == "Your first article"
    assert lesson.needs == "a-home"
    assert [step.title for step in lesson.steps] == ["Give it a name", "Write"]
    assert lesson.steps[0].note == Note("tip", "The slug fills itself in.")
    assert lesson.steps[1].text == ("One line.", "Another line.")
    assert lesson.made.shot == "first/made"
    assert lesson.optional is False


def test_a_lesson_lists_its_pictures_once_each_in_order():
    with_cover = LESSON.replace('needs = "a-home"', 'needs = "a-home"\ncover = "first/made"')
    lesson = parse_lesson("first", with_cover)
    assert lesson.cover == "first/made"
    assert lesson.shot_ids() == ("first/name-it", "first/made")


def test_every_passage_a_reader_sees_is_listed():
    texts = parse_lesson("first", LESSON).texts()
    assert "The slug fills itself in." in texts
    assert "Your first article." in texts


@pytest.mark.parametrize(
    ("change", "complaint"),
    [
        (('title = "Your first article"\n', ""), "title is required"),
        (('shot = "first/name-it"', 'shots = "first/name-it"'), "unexpected shots"),
        (('kind = "tip"', 'kind = "warning"'), "kind 'warning' is not one of"),
        (('needs = "a-home"', "needs = 3"), "needs must be non-empty text"),
        (('text = ["One line.", "Another line."]', "text = []"), "text is required"),
        (("[made]", "[[made]]"), "expected a table"),
        (('title = "Write"', 'title = "Write'), "first.toml"),
    ],
)
def test_a_broken_lesson_says_where_and_what(change, complaint):
    old, new = change
    with pytest.raises(LessonError, match=complaint):
        parse_lesson("first", LESSON.replace(old, new, 1))


COURSE = """
title = "From first article to first draft"
lede = "Short lessons."
prelude = "before"

[[parts]]
slug = "world"
kicker = "Part 1"
title = "Your world"
blurb = "People and places."
mark = "akasha"
lessons = ["home", "first"]

[[parts]]
slug = "draft"
kicker = "Part 2"
title = "Your draft"
blurb = "Prose."
mark = "logos"
lessons = ["write"]
"""


def test_a_course_reads_in_reading_order_with_the_prelude_unnumbered():
    course = parse_course(COURSE)
    assert course.order() == ("before", "home", "first", "write")
    assert course.numbered() == ("home", "first", "write")
    assert course.part_of("write").slug == "draft"
    assert course.part_of("before") is None


def test_a_course_needs_parts_with_lessons():
    with pytest.raises(LessonError, match="at least one lesson"):
        parse_course(COURSE.replace('lessons = ["write"]', "lessons = []"))
    with pytest.raises(LessonError, match="at least one part"):
        parse_course('title = "t"\nlede = "l"\n')


def test_the_glossary_reads_words_and_meanings():
    terms = parse_glossary('[[terms]]\nword = "Plot line"\nmeaning = "A thread."\n')
    assert terms[0].word == "Plot line"
    assert terms[0].slug == "plot-line"


@pytest.mark.parametrize(("word", "slug"), [("World", "world"), ("Plot line", "plot-line"), ("  Draft ", "draft")])
def test_a_term_has_one_anchor_however_it_is_written(word, slug):
    assert term_slug(word) == slug
