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

    def run(imports: str, body: str):
        script = workspace / "driver.js"
        script.write_text(
            f'import {{ {imports} }} from "./media.js";\n'
            'import { formatGalleryItem, parseGalleryItem, parseImageDirective } '
            'from "./image-format.js";\n'
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
    browser = run_js("formatImageDirective", f"emit(parseImageDirective({json.dumps(directive)}));")
    server = parse_image_directive(directive)
    assert browser == {
        "media_id": server.media_id,
        "align": server.align,
        "width": server.width,
        "caption": server.caption,
    }


def test_formatter_constrains_layout_values(run_js):
    result = run_js(
        "formatImageDirective",
        "emit(formatImageDirective({id: '" + "b" * 32
        + "', align: 'full', width: 12, caption: 'A\\ncaption'}));",
    )
    assert result == "{{image:" + "b" * 32 + "|full|100|A caption}}"


def test_gallery_format_round_trips_caption_separators(run_js):
    media_id = "b" * 32
    result = run_js(
        "formatImageDirective",
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
    result = run_js("formatImageDirective", script)
    assert result["document"]["gallery"] == [f"{first}|First", f"{second}|Second"]
    assert result["document"]["profile_image"] == second
    assert result["article"]["facts"] == [{"key": "region", "value": "North"}]


def test_inline_image_is_migrated_into_article_gallery(run_js):
    media_id = "c" * 32
    directive = f"{{{{image:{media_id}|left|35|Old caption}}}}"
    result = run_js(
        "formatImageDirective",
        f"emit(splitArticle({{body: {json.dumps(directive)}}}, 'atlas').gallery);",
    )
    assert result == [{"media_id": media_id, "caption": "Old caption"}]


def test_renderer_escapes_caption_and_emits_only_validated_layout(run_js):
    directive = "{{image:" + "c" * 32 + "|left|35|<script>alert(1)</script>}}"
    html = run_js("formatImageDirective", f"emit(renderWikitext({json.dumps(directive)}));")
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
    result = run_js("directiveAtCursor, insertImageDirective", body)
    assert result["value"] == "Before\n{{image:" + "d" * 32 + "|right|65|New}}\nAfter"
    assert result["cursor"][0] == result["cursor"][1]
