"""A lesson's text: escaped first, then three marks and no more."""

import pytest

from visualizer.tutorials.inline import (
    labels_in,
    plain,
    render_inline,
    sentence_count,
    terms_in,
    word_count,
)


def href(word):
    return {"world": "/g#world", "category": "/g#category"}.get(word)


def test_a_label_is_a_key_cap():
    assert render_inline("Press `＋ New world`.", href) == (
        'Press <span class="ui">＋ New world</span>.'
    )


def test_bold_is_emphasis():
    assert render_inline("Type into **Title**.", href) == "Type into <strong>Title</strong>."


def test_a_glossary_word_links_to_its_entry():
    assert render_inline("Your {world}.", href) == 'Your <a class="term" href="/g#world">world</a>.'


def test_a_glossary_word_can_be_shown_in_another_form():
    assert render_inline("Two {categories|category}.", href) == (
        'Two <a class="term" href="/g#category">categories</a>.'
    )


def test_a_word_the_glossary_lacks_is_plain_text():
    assert render_inline("A {plotline}.", href) == "A plotline."


@pytest.mark.parametrize(
    "text",
    ['<script>alert(1)</script>', '`<b>`', '**<i>x</i>**', '{<img src=x>}'],
)
def test_nothing_in_a_lesson_becomes_markup(text):
    rendered = str(render_inline(text, href))
    assert "<script" not in rendered and "<b>" not in rendered
    assert "<i>" not in rendered and "<img" not in rendered


def test_the_labels_and_terms_a_passage_uses_are_listed():
    text = "Press `Create`, then `Continue` in your {worlds|world} and {category}."
    assert labels_in(text) == ("Create", "Continue")
    assert terms_in(text) == ("world", "category")


def test_plain_text_keeps_the_words_and_drops_the_marks():
    assert plain("Press `Go` in **Title** of your {worlds|world}.") == (
        "Press Go in Title of your worlds."
    )


@pytest.mark.parametrize(
    ("text", "count"),
    [
        ("One.", 1),
        ("One. Two! Three?", 3),
        ("No full stop at all", 1),
        ("Type into `Search titles…` and wait.", 1),
        ("It is **lantern-coast**. The app shows it back.", 2),
    ],
)
def test_sentences_are_counted_without_counting_a_label_s_dots(text, count):
    assert sentence_count(text) == count


def test_words_are_counted_as_a_reader_reads_them():
    assert word_count("Press `＋ New world` now.") == 5
