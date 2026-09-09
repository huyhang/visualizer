"""The browser and server must agree on Akasha's image-directive grammar."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from visualizer.akasha.media import parse_image_directive

_JS_DIR = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "visualizer"
    / "akasha"
    / "static"
    / "js"
)


def _node_binary():
    found = shutil.which("node")
    if found:
        return found
    try:
        import nodejs_wheel
    except ImportError:
        return None
    executable = "node.exe" if sys.platform == "win32" else "node"
    candidate = Path(nodejs_wheel.__file__).parent / "bin" / executable
    return str(candidate) if candidate.exists() else None


@pytest.fixture(scope="module")
def run_js(tmp_path_factory):
    node = _node_binary()
    if node is None:
        pytest.skip("no node available -- `pip install -e \".[dev]\"` provides one")
    workspace = tmp_path_factory.mktemp("akasha-media-js")
    (workspace / "package.json").write_text('{"type": "module"}')
    for name in (
        "api.js",
        "article.js",
        "dom.js",
        "image-format.js",
        "media.js",
        "wikitext.js",
    ):
        shutil.copy(_JS_DIR / name, workspace / name)

    def run(body: str, imports: str = ""):
        script = workspace / "driver.js"
        script.write_text(
            (f'import {{ {imports} }} from "./media.js";\n' if imports else "")
            + 'import { formatGalleryItem, formatImageDirective, parseGalleryItem, '
            'parseImageDirective } from "./image-format.js";\n'
            'import { assembleArticle, splitArticle } from "./article.js";\n'
            'import { renderWikitext } from "./wikitext.js";\n'
            "const emit = (value) => console.log(JSON.stringify(value));\n"
            + body
        )
        done = subprocess.run(
            [node, str(script)], capture_output=True, text=True, timeout=60, check=False
        )
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)

    return run


def test_browser_and_server_parse_the_same_directive(run_js):
    directive = "{{image:" + "a" * 32 + "|right|45|Tower at dusk}}"
    browser = run_js(f"emit(parseImageDirective({json.dumps(directive)}));")
    server = parse_image_directive(directive)
    assert browser == {
        "media_id": server.media_id,
        "align": server.align,
        "width": server.width,
        "caption": server.caption,
    }


def test_formatter_constrains_layout_values(run_js):
    result = run_js(
        "emit(formatImageDirective({id: '" + "b" * 32
        + "', align: 'full', width: 12, caption: 'A\\ncaption'}));",
    )
    assert result == "{{image:" + "b" * 32 + "|full|100|A caption}}"


def test_gallery_format_round_trips_caption_separators(run_js):
    media_id = "b" * 32
    result = run_js(
        f"emit(parseGalleryItem(formatGalleryItem({{id: '{media_id}', caption: 'Map | dusk'}})));",
    )
    assert result == {"media_id": media_id, "caption": "Map | dusk"}


def test_article_round_trip_keeps_gallery_order_profile_and_facts(run_js):
    first = "a" * 32
    second = "b" * 32
    script = f"""
const document = assembleArticle({{
  title: 'Atlas', body: '', facts: [{{key: 'region', value: 'North'}}],
  profileImage: '{second}',
  gallery: [
    {{media_id: '{first}', caption: 'First'}},
    {{media_id: '{second}', caption: 'Second'}},
  ],
}});
emit({{document, article: splitArticle(document, 'atlas')}});
"""
    result = run_js(script)
    assert result["document"]["gallery"] == [f"{first}|First", f"{second}|Second"]
    assert result["document"]["profile_image"] == second
    assert result["article"]["facts"] == [{"key": "region", "value": "North"}]


def test_inline_image_is_migrated_into_article_gallery(run_js):
    media_id = "c" * 32
    directive = f"{{{{image:{media_id}|left|35|Old caption}}}}"
    result = run_js(
        f"emit(splitArticle({{body: {json.dumps(directive)}}}, 'atlas').gallery);",
    )
    assert result == [{"media_id": media_id, "caption": "Old caption"}]


def test_renderer_escapes_caption_and_emits_only_validated_layout(run_js):
    directive = "{{image:" + "c" * 32 + "|left|35|<script>alert(1)</script>}}"
    html = run_js(f"emit(renderWikitext({json.dumps(directive)}));")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "align-left" in html
    assert "--image-width:35%" in html


def test_editor_can_replace_the_directive_under_the_cursor(run_js):
    original = "Before\n{{image:" + "d" * 32 + "|left|30|Old}}\nAfter"
    body = f"""
globalThis.Event = class {{}};
const area = {{
  value: {json.dumps(original)}, selectionStart: 20, selectionEnd: 20,
  focus() {{}}, setSelectionRange(start, end) {{ this.cursor = [start, end]; }},
  dispatchEvent() {{}},
}};
const found = directiveAtCursor(area);
insertImageDirective(area, {{id: found.placement.media_id, align: 'right', width: 65, caption: 'New'}}, found);
emit({{value: area.value, cursor: area.cursor}});
"""
    result = run_js(body, "directiveAtCursor, insertImageDirective")
    assert result["value"] == "Before\n{{image:" + "d" * 32 + "|right|65|New}}\nAfter"
    assert result["cursor"][0] == result["cursor"][1]


def test_a_gallery_fact_that_predates_images_survives_a_round_trip(run_js):
    """`gallery` and `profile_image` are only reserved when they hold image
    references. A list of wing names is an infobox fact, and must come back."""
    script = """
const stored = {
  title: 'The Louvre',
  gallery: ['Denon wing', 'Sully wing'],
  profile_image: 'commissioned 1387 by the guild',
};
const article = splitArticle(stored, 'louvre');
emit({facts: article.facts, gallery: article.gallery,
      profile: article.profileImage,
      rebuilt: assembleArticle({title: article.title, body: article.body,
                                facts: article.facts,
                                profileImage: article.profileImage,
                                gallery: article.gallery})});
"""
    result = run_js(script)
    assert result["gallery"] == []
    assert result["profile"] is None
    assert {f["key"] for f in result["facts"]} == {"gallery", "profile_image"}
    assert result["rebuilt"]["gallery"] == ["Denon wing", "Sully wing"]
    assert result["rebuilt"]["profile_image"] == "commissioned 1387 by the guild"


def test_an_image_gallery_still_claims_the_field(run_js):
    media_id = "e" * 32
    script = f"""
const stored = {{title: 'Atlas', gallery: ['{media_id}|A caption'],
                 profile_image: '{media_id}', region: 'North'}};
const article = splitArticle(stored, 'atlas');
emit({{facts: article.facts, gallery: article.gallery,
      profile: article.profileImage}});
"""
    result = run_js(script)
    assert result["gallery"] == [{"media_id": media_id, "caption": "A caption"}]
    assert result["profile"] == media_id
    assert [f["key"] for f in result["facts"]] == ["region"]


def test_the_figure_markup_has_one_source(run_js):
    """`createImageFigure` reparses `renderImage`'s output rather than
    rebuilding it, so the reader's hooks cannot drift from the renderer's."""
    media_id = "f" * 32
    directive = f"{{{{image:{media_id}|right|45|Quote \" and <tag>}}}}"
    html = run_js(f"emit(renderWikitext({json.dumps(directive)}));")

    assert f'data-media-id="{media_id}"' in html
    assert 'class="article-image align-right"' in html
    assert "--image-width:45%" in html
    assert 'aria-label="Open full-size image"' in html
    assert "<script>" not in html and "&lt;tag&gt;" in html


def test_a_crafted_placement_cannot_break_out_of_an_attribute(run_js):
    """`createImageFigure` is called with hand-built placements, not only with
    parser output, so the markup escapes its own attribute values."""
    html = run_js(
        "emit(renderWikitext('{{image:' + 'a'.repeat(32)"
        " + '|left|30|\" onerror=alert(1) x=\"}}'));"
    )
    tags, caption = html.split("<figcaption>")
    # The payload reached text content, where a bare quote is harmless...
    assert caption.startswith('" onerror=alert(1) x="</figcaption>')
    # ...and nothing of it reached an attribute.
    assert "onerror" not in tags
    assert tags.count('"') % 2 == 0  # every attribute quote is still paired


def test_a_diorama_previews_from_its_poster_not_a_thumbnail(run_js):
    """The library holds two kinds and only one of them has a thumbnail.

    Reaching for `thumbnail_url` on a diorama yields `undefined`, which the
    browser renders as a broken-image icon beside perfectly correct alt text --
    which is exactly what the article gallery was showing.
    """
    result = run_js(
        "emit({\n"
        "  image: previewSource({thumbnail_url: '/t', poster_url: null}),\n"
        "  diorama: previewSource({poster_url: '/p'}),\n"
        "  posterless: previewSource({model_url: '/m'}),\n"
        "  nothing: previewSource(null),\n"
        "});",
        "previewSource",
    )
    assert result == {
        "image": "/t",
        "diorama": "/p",
        # No still was captured: the caller shows a placeholder rather than
        # setting src to undefined.
        "posterless": None,
        "nothing": None,
    }
