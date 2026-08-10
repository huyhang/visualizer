"""Static checks on the editor SPA's ES modules.

There is no JS test harness in this project (by choice -- the rules live in
Python, and the browser code is deliberately thin). What Python *can* still
check cheaply is the wiring: that every module the app serves exists, that no
module imports a file that is not there, and that every named import is actually
exported by the module it comes from. Those are the mistakes a rename makes, and
they break the whole page at load time rather than failing quietly.

The mirror of ``tests/chronos/test_ui_assets.py``, which akasha did not have --
so the browse views arrived alongside the check that they are wired up at all.
"""

import re
from pathlib import Path

import pytest

_JS_DIR = Path(__file__).resolve().parents[2] / "src" / "visualizer" / "akasha" / "static" / "js"

# `import { a, b } from "./x.js";` and `import "./x.js";`
_IMPORT = re.compile(r"""import\s+(?:(?P<names>\{[^}]*\})\s+from\s+)?["'](?P<from>[^"']+)["']""")
# `$` and `$$` are valid identifiers, and dom.js exports both.
_EXPORT = re.compile(r"""export\s+(?:async\s+)?(?:function|class|const|let|var)\s+(?P<name>[\w$]+)""")

# Modules allowed to write HTML directly, each because it *is* the escaping
# layer for its own output rather than a view pasting a title into the page:
#   dom.js       -- offers the `html:` escape hatch the others go through
#   wikitext.js  -- renders wikitext, escaping every value it interpolates
#   diffview.js  -- emits <ins>/<del> around text it has already escaped
#   editor.js    -- shows the live preview, which is wikitext.js's output
_HTML_ALLOWED = {"dom.js", "wikitext.js", "diffview.js", "editor.js"}

# Modules both services load. They live once, at the package root, and are
# served by each app beneath its own static path (``visualizer/shared_assets``),
# so `./shared/x.js` resolves from either tree and at either mount. On disk they
# are nowhere near the importer, hence the redirect in ``_target``.
_SHARED_JS = Path(__file__).resolve().parents[2] / "src" / "visualizer" / "static" / "js"
_SHARED_PREFIX = "./shared/"


def _shared_modules():
    return sorted(_SHARED_JS.glob("*.js"))


def _target(importer: Path, specifier: str) -> Path:
    if specifier.startswith(_SHARED_PREFIX):
        return (_SHARED_JS / specifier[len(_SHARED_PREFIX):]).resolve()
    return (importer.parent / specifier).resolve()


def _modules():
    return sorted(_JS_DIR.glob("*.js"))


def _exports(path: Path) -> set[str]:
    return set(_EXPORT.findall(path.read_text()))


def _imports(path: Path):
    """Yield (target_module_path, imported_names) for each relative import."""
    for match in _IMPORT.finditer(path.read_text()):
        target = match.group("from")
        if not target.startswith("."):
            continue  # no bare/bundler specifiers in this project
        names = match.group("names") or ""
        yield (
            _target(path, target),
            [n.split(" as ")[0].strip() for n in names.strip("{}").split(",") if n.strip()],
        )


@pytest.mark.parametrize("module", _modules() + _shared_modules(), ids=lambda p: p.name)
def test_every_import_resolves_to_a_module_that_exports_it(module):
    for target, names in _imports(module):
        assert target.exists(), f"{module.name} imports missing module {target.name}"
        missing = sorted(set(names) - _exports(target))
        assert not missing, f"{module.name} imports {missing} which {target.name} does not export"


def test_the_entrypoint_reaches_every_module():
    """No orphans: a module nothing imports is dead code (or a missing wire-up)."""
    reached, queue = set(), [_JS_DIR / "app.js"]
    while queue:
        current = queue.pop()
        if current in reached:
            continue
        reached.add(current)
        queue.extend(target for target, _ in _imports(current))
    local = {p for p in reached if p.parent == _JS_DIR}
    assert {p.name for p in _modules()} == {p.name for p in local}


def test_the_editor_modules_are_served(client):
    # A module that 404s takes the whole SPA down, since app.js imports it.
    for module in _modules():
        assert client.get(f"/static/js/{module.name}").status_code == 200, module.name


def test_the_shared_modules_are_served_under_this_apps_static_path(client):
    """The mirror of chronos's check: the shared tree is only shared because
    *both* apps serve it, out of the package root rather than this service's
    ``static/``, via a route that has to beat ``/static/<path:filename>``."""
    assert _shared_modules(), "no shared modules found — wrong path?"
    for module in _shared_modules():
        resp = client.get(f"/static/js/shared/{module.name}")
        assert resp.status_code == 200, module.name
        assert "slugify" in resp.get_data(as_text=True)


def test_no_view_builds_dom_from_untrusted_html():
    """View modules take `text`, never `innerHTML`, for anything user-supplied.

    A stray `innerHTML =` in a browse view is how an article title becomes
    script. The renderers that legitimately emit markup are listed (and the
    reason given) in ``_HTML_ALLOWED``.
    """
    for module in _modules():
        if module.name in _HTML_ALLOWED:
            continue
        source = module.read_text()
        assert "innerHTML" not in source, f"{module.name} sets innerHTML"
        assert not re.search(r"""\bhtml:\s""", source), f"{module.name} uses the html: escape hatch"


def test_the_editor_page_mounts_what_the_app_expects():
    """The SPA reaches for these ids on boot; a renamed one is a blank page."""
    template = _JS_DIR.parents[1] / "templates" / "editor.html"
    markup = template.read_text()
    for element_id in ("pane", "sidebar", "tree", "scrim", "toast",
                       "search-box", "new-article-btn", "home-link",
                       "theme-toggle", "font-toggle", "menu-toggle"):
        assert f'id="{element_id}"' in markup, element_id
