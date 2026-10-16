"""The lessons on disk: read once, through whatever reads files."""

from pathlib import Path

import pytest

from visualizer.tutorials.catalog import LESSONS_DIR, load_catalog
from visualizer.tutorials.lessons import LessonError
from visualizer.tutorials.shots import SHOTS_DIR, load_shots
from visualizer.tutorials.validate import validate

FILES = {
    "course.toml": """
title = "T"
lede = "L"
[[parts]]
slug = "p"
kicker = "K"
title = "P"
blurb = "B"
mark = "akasha"
lessons = ["one"]
""",
    "one.toml": """
title = "One"
summary = "S"
lede = "L"
[[steps]]
title = "Step"
text = "Do it."
""",
    "glossary.toml": '[[terms]]\nword = "world"\nmeaning = "M"\n',
}


def reader(files):
    def read(path: Path) -> str:
        try:
            return files[path.name]
        except KeyError:
            raise FileNotFoundError(path) from None

    return read


def test_the_course_names_the_files_that_are_read():
    loaded = load_catalog(Path("/lessons"), read=reader(FILES))
    assert loaded.course().title == "T"
    assert loaded.lesson("one").steps[0].text == ("Do it.",)
    assert loaded.glossary()[0].word == "world"
    assert loaded.lesson("two") is None


def test_a_lesson_the_course_names_must_exist():
    files = {**FILES, "course.toml": FILES["course.toml"].replace('["one"]', '["one", "two"]')}
    with pytest.raises(LessonError, match="names 'two', which has no two.toml"):
        load_catalog(Path("/lessons"), read=reader(files))


def test_the_lessons_in_the_package_load():
    loaded = load_catalog(LESSONS_DIR)
    order = loaded.course().order()
    assert order[0] == "before-you-start"
    assert all(loaded.lesson(slug) for slug in order)


def test_the_lessons_and_their_pictures_keep_every_rule():
    """The one that matters: what a reader will see.

    A failure names the lesson and the rule. A picture that "has not been
    taken", or a label "none of its pictures show", means the camera has to be
    run again: docker compose -f docker/docker-compose.screenshots.yml run
    --rm --build tutorial-shots.
    """
    downloads = SHOTS_DIR.parent / "downloads"
    problems = validate(
        load_catalog(LESSONS_DIR),
        load_shots(),
        download_exists=lambda name: (downloads / name).is_file(),
    )
    assert [str(problem) for problem in problems] == []


def test_every_picture_the_manifest_names_is_on_disk():
    from visualizer.tutorials.shots import SIZES, THEMES, shot_path

    library = load_shots()
    for shot_id in library.ids():
        for size in SIZES:
            for theme in THEMES:
                path = SHOTS_DIR.parent / shot_path(shot_id, size, theme)
                assert path.is_file(), f"shots.json names {path.name}, which is missing"
