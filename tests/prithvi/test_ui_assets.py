"""Static wiring for the map page's ES modules.

There is no bundler and no import map: whatever a module writes as a specifier
is what the browser will ask the server for. So a typo in an import, or a name
that moved, is a blank page at runtime and nothing at all at test time -- unless
something reads the graph, which is what this does. The same check Chronos runs
over its own tree.
"""

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2] / "src" / "visualizer"
_JS = _ROOT / "prithvi" / "static" / "js"
_SHARED = _ROOT / "static" / "js"
_TEMPLATE = _ROOT / "prithvi" / "templates" / "maps.html"

_IMPORT = re.compile(
    r"""import\s+(?:(?P<names>\{[^}]*\})\s+from\s+)?["'](?P<from>[^"']+)["']""",
    re.DOTALL,
)
_EXPORT = re.compile(
    r"""export\s+(?:async\s+)?(?:function|class|const|let|var)\s+(?P<name>[\w$]+)"""
)


def _modules():
    return sorted(_JS.glob("*.js"))


def _target(importer: Path, specifier: str) -> Path:
    # `./shared/x.js` is served from the package root under this app's own
    # static path -- see visualizer/shared_assets.py -- so it resolves there
    # rather than beside the importer.
    if specifier.startswith("./shared/"):
        return (_SHARED / specifier.removeprefix("./shared/")).resolve()
    return (importer.parent / specifier).resolve()


def _imports(module: Path):
    for match in _IMPORT.finditer(module.read_text()):
        specifier = match.group("from")
        if not specifier.startswith("."):
            continue
        names = (match.group("names") or "").strip("{}")
        yield _target(module, specifier), [
            name.split(" as ")[0].strip() for name in names.split(",") if name.strip()
        ]


@pytest.mark.parametrize("module", _modules(), ids=lambda path: path.name)
def test_every_import_resolves_to_a_module_that_exports_the_name(module):
    for target, names in _imports(module):
        assert target.exists(), f"{module.name} imports missing {target.name}"
        missing = set(names) - set(_EXPORT.findall(target.read_text()))
        assert not missing, f"{module.name} imports {missing} absent from {target.name}"


@pytest.mark.parametrize("module", _modules(), ids=lambda path: path.name)
def test_no_module_reaches_for_a_bundler(module):
    """Bare specifiers need a build step this project deliberately has none of."""
    for match in _IMPORT.finditer(module.read_text()):
        specifier = match.group("from")
        assert specifier.startswith("."), f"{module.name} imports bare {specifier!r}"


def test_the_entrypoint_reaches_every_module_in_the_tree():
    """An unreachable module is dead weight the browser never loads."""
    reached, queue = set(), [_JS / "app.js"]
    while queue:
        current = queue.pop()
        if current in reached:
            continue
        reached.add(current)
        queue.extend(target for target, _ in _imports(current) if target.parent == _JS)
    assert {path.name for path in reached} == {path.name for path in _modules()}


def test_the_service_ships_the_same_mark_its_siblings_do():
    """Each service has a glyph for the header and an icon for the tab.

    A convention rather than a requirement, which is exactly the kind of thing
    that gets skipped: the page still works without them, it just quietly looks
    like it belongs to no one and shows the browser's default favicon.
    """
    for service in ("akasha", "chronos", "prithvi", "logos"):
        for kind in ("glyph", "icon"):
            asset = _ROOT / service / "static" / f"{service}-{kind}.svg"
            assert asset.exists(), f"{service} has no {kind}"
            assert asset.read_text().lstrip().startswith("<svg")


@pytest.mark.parametrize("kind", ["glyph", "icon"])
def test_the_mark_is_well_formed_svg(kind):
    from xml.etree import ElementTree

    asset = _ROOT / "prithvi" / "static" / f"prithvi-{kind}.svg"
    root = ElementTree.fromstring(asset.read_text())
    assert root.tag.endswith("svg")
    assert root.get("viewBox") == "0 0 32 32"
    assert root.get("aria-label") == "Prithvi"


def test_the_template_loads_the_entrypoint_as_a_module():
    markup = _TEMPLATE.read_text()
    assert 'type="module"' in markup
    assert "js/app.js" in markup


def test_every_element_the_entrypoint_looks_up_exists_in_the_template():
    """`getElementById` returning null is a TypeError on the first interaction."""
    markup = _TEMPLATE.read_text()
    lookups = re.findall(r"""\$\(["']([\w-]+)["']\)""", (_JS / "app.js").read_text())
    wanted = set(lookups)
    assert wanted, "expected app.js to look elements up by id"
    missing = {name for name in wanted if f'id="{name}"' not in markup}
    assert not missing, f"app.js expects ids the template does not define: {missing}"
