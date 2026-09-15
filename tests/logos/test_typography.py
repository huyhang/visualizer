"""Straight quotes in, curly quotes out -- and everything that depends on it.

Two rules share one module. ``curl_text`` reads both ways and owns every write
that reaches the API; ``curl_typed_mark`` reads only backwards, because at a
caret nothing follows the mark yet, and ``fix_elisions`` is how the second
catches up with the first. The browser mirrors all three in
``static/js/typography.js``; ``test_reader_js`` holds that side.
"""

import pytest

from visualizer.logos.publication import validate_publication
from visualizer.logos.typography import curl_text, curl_typed_mark, fix_elisions
from visualizer.logos.writing import RuleBasedWritingAdvisor

from .conftest import BOOK, SECTION, VOLUME, document

SECTION_PATH = f"/books/{BOOK}/volumes/{VOLUME}/sections/{SECTION}"
DRAFTS = SECTION_PATH + "/drafts"


@pytest.mark.parametrize(
    "given,expected",
    [
        ('He said "hello" to her.', "He said “hello” to her."),
        ("don't", "don’t"),
        ("Jones' hat", "Jones’ hat"),
        ("5 o'clock", "5 o’clock"),
        # A closing single quote follows punctuation far more often than it
        # follows a letter -- it is how every line of quoted dialogue ends.
        ("'Hello,' she said.", "‘Hello,’ she said."),
        ("end.' Next", "end.’ Next"),
        ('"Stop!" he cried; \'Now,\' she said.', "“Stop!” he cried; ‘Now,’ she said."),
        ('she said, "\'Quite,\' indeed."', "she said, “‘Quite,’ indeed.”"),
        # An elided leading letter is an apostrophe, not an opening quote.
        ("'twas the night", "’twas the night"),
        ("'til dawn", "’til dawn"),
        ("'Tis so.", "’Tis so."),
        ("'em all", "’em all"),
        ("rock 'n' roll", "rock ’n’ roll"),
        ("The '90s were wild.", "The ’90s were wild."),
        ("already “curly” don’t", "already “curly” don’t"),
        ("no quotes here", "no quotes here"),
        ("", ""),
    ],
)
def test_quotes_curl_by_their_surroundings(given, expected):
    assert curl_text(given) == expected


def test_curling_is_idempotent():
    for given in ("'Hello,' she said.", "'twas", 'He said "hi"', "rock 'n' roll"):
        once = curl_text(given)
        assert curl_text(once) == once, given


@pytest.mark.parametrize(
    "before,mark,expected",
    [
        ("She said ", '"', "“"),
        ("", '"', "“"),
        ("(", '"', "“"),
        ("She said “hello", '"', "”"),
        ("don", "'", "’"),
        ("said ", "'", "‘"),
    ],
)
def test_a_typed_mark_is_decided_from_what_precedes_it(before, mark, expected):
    """At the caret there is no following character to read, so an opening
    quote can only be told from a closing one by what is already typed."""
    assert curl_typed_mark(before, mark) == expected


def test_fix_elisions_repairs_the_guess_the_caret_could_not_make():
    assert fix_elisions("‘tis so") == "’tis so"
    assert fix_elisions("the ‘90s") == "the ’90s"
    assert fix_elisions("‘Hello,’ she said") == "‘Hello,’ she said"
    assert fix_elisions("nothing to do") == "nothing to do"


def test_every_manuscript_field_a_writer_types_reads_back_curly(client):
    """Prose, titles, overviews and draft names all pass through the same two
    text validators, which is what keeps this true of fields added later."""
    straight = "The 'quiet' \"gate\""
    curly = "The ‘quiet’ “gate”"

    volume = client.post(
        f"/books/{BOOK}/volumes/{VOLUME}",
        json={"title": straight, "overview": straight},
    ).get_json()
    section = client.post(
        SECTION_PATH,
        json={
            "kind": "chapter", "title": straight, "overview": straight,
            "event_ids": [], "document": document(straight),
        },
    ).get_json()
    created = client.post(DRAFTS, json={"name": straight}).get_json()

    assert volume["title"] == curly
    assert volume["overview"] == curly
    assert section["title"] == curly
    assert section["overview"] == curly
    assert section["document"]["content"][0]["content"][0]["text"] == curly
    # A name curled on update but not on create would change under the writer
    # the first time they saved.
    assert created["name"] == curly


def test_publication_metadata_curls_but_the_language_tag_is_left_alone():
    """The title page is the most typeset surface in the product; `language`
    is a tag matched against a pattern, not prose."""
    result = validate_publication({
        "title": "The Ember Pact", "subtitle": "Lyra's 'first' turn",
        "author": "A. Writer", "language": "en-GB",
        "publisher": "", "copyright": "",
    })

    assert result["subtitle"] == "Lyra’s ‘first’ turn"
    assert result["language"] == "en-GB"


def test_the_advisor_reads_a_curled_contraction_as_one_word():
    """Curling runs on every write, so by the time the coach sees prose the
    apostrophes are already curly. A word pattern that only knew the straight
    mark would stop matching repeats and would split `it's` into `it` + `s`,
    inventing a repeated opening of `it s` that the writer never wrote."""
    advisor = RuleBasedWritingAdvisor()

    repeated = advisor.review(document("She said it’s it’s a long road."))
    varied = advisor.review(
        document("It’s raining hard. It’s sailing away. It’s sinking fast.")
    )

    assert [issue["title"] for issue in repeated] == ["Repeated word"]
    assert repeated[0]["excerpt"] == "it’s it’s"
    assert varied == []
