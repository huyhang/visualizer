"""Static checks on the SPA's ES modules.

There is no JS test harness in this project (by choice -- the rules live in
Python, and the browser code is deliberately thin). What Python *can* still
check cheaply is the wiring: that every module the app serves exists, that no
module imports a file that is not there, and that every named import is actually
exported by the module it comes from. Those are the mistakes a rename makes, and
they break the whole page at load time rather than failing quietly.
"""

import re
from pathlib import Path

import pytest

_JS_DIR = Path(__file__).resolve().parents[2] / "src" / "visualizer" / "chronos" / "static" / "js"

# `import { a, b } from "./x.js";` and `import "./x.js";`
_IMPORT = re.compile(r"""import\s+(?:(?P<names>\{[^}]*\})\s+from\s+)?["'](?P<from>[^"']+)["']""")
# `$` and `$$` are valid identifiers, and dom.js exports both.
_EXPORT = re.compile(r"""export\s+(?:async\s+)?(?:function|class|const|let|var)\s+(?P<name>[\w$]+)""")


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
            (path.parent / target).resolve(),
            [n.split(" as ")[0].strip() for n in names.strip("{}").split(",") if n.strip()],
        )


@pytest.mark.parametrize("module", _modules(), ids=lambda p: p.name)
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
    assert {p.name for p in _modules()} == {p.name for p in reached}


def test_the_editor_modules_are_served(client, app, fake_gate):
    # A module that 404s takes the whole SPA down, since app.js imports it.
    for module in _modules():
        assert client.get(f"/static/js/{module.name}").status_code == 200, module.name


def test_no_module_builds_dom_from_untrusted_html():
    """The DOM helpers take `text`, never `innerHTML`, for anything user-supplied.

    ``dom.js`` offers an `html:` escape hatch for callers that guarantee safety;
    nothing in the visualiser should be using it, and a stray `innerHTML =` in a
    view module is how a scene title becomes script.
    """
    for module in _modules():
        if module.name == "dom.js":
            continue
        source = module.read_text()
        assert "innerHTML" not in source, f"{module.name} sets innerHTML"
        assert not re.search(r"""\bhtml:\s""", source), f"{module.name} uses the html: escape hatch"
