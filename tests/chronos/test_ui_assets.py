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


def test_the_editor_modules_are_served(client, app, fake_gate):
    # A module that 404s takes the whole SPA down, since app.js imports it.
    for module in _modules():
        assert client.get(f"/static/js/{module.name}").status_code == 200, module.name


def test_the_shared_modules_are_served_under_this_apps_static_path(client):
    """The shared tree is only shared because *both* apps serve it.

    It lives at the package root, outside this service's ``static/``, so it
    reaches the browser via a route rather than Flask's static handler -- and
    that route has to win against ``/static/<path:filename>``, which would
    otherwise swallow it and 404. Chronos is also mounted under ``/timeline`` in
    production; the URL here is relative to the app, so it is right at either
    mount.
    """
    assert _shared_modules(), "no shared modules found — wrong path?"
    for module in _shared_modules():
        resp = client.get(f"/static/js/shared/{module.name}")
        assert resp.status_code == 200, module.name
        assert "slugify" in resp.get_data(as_text=True)


def _body_builder(source: str) -> str:
    """The text of a module's ``body()`` payload builder.

    Both editors declare it at one level of indentation inside their entry
    function, so it ends at the first line that is exactly two spaces and a
    brace -- the same convention the rest of the file is written in.
    """
    start = source.index("function body()")
    return source[start : source.index("\n  }", start)]


@pytest.mark.parametrize("module,fields", [
    ("bookform.js", ("title", "overview", "calendar", "world", "terminus")),
    ("plotedit.js", ("title", "overview", "events", "goals", "continues_into")),
], ids=lambda v: v if isinstance(v, str) else "")
def test_the_editors_resend_every_stored_field(module, fields):
    """A PUT replaces the whole document, so a payload that omits a field erases it.

    Both editors build that payload by hand, and the fields easiest to forget are
    the ones nothing recomputes and no verdict mentions -- an overview, a
    terminus, a continuation. The API test pins what the server does with a
    partial body; this pins the browser's half, which is where the mistake would
    actually be made. Python cannot drive the form, but it can read it, and this
    is a failure mode worth catching statically: it deletes a writer's prose and
    raises nothing at all.
    """
    body = _body_builder((_JS_DIR / module).read_text())
    missing = [f for f in fields if f not in body]
    assert not missing, f"{module}'s body() never sends {missing}"


# Elements whose displayed value is *not* set by a `value` attribute. A
# textarea's value is its child text; a select's is whichever option carries
# `selected`. ``el`` routes unknown keys to setAttribute, so `value:` on either
# is accepted, ignored, and invisible -- the control renders empty while the
# state behind it is correct, which is the worst way to be wrong: the writer
# edits a field that will not show them what is already in it.
#
# The fix both services already use everywhere: assign the `.value` property
# after constructing it (``sceneform.js``), or for a textarea pass `text:`,
# which ``el`` maps to textContent (akasha's ``editor.js``).
_VALUELESS_TAGS = ("textarea", "select")


@pytest.mark.parametrize("tag", _VALUELESS_TAGS)
def test_no_module_sets_value_as_an_attribute_on(tag):
    """`el("option", { value: … })` is fine and is not caught here -- option is
    one of the elements that really does have the attribute."""
    pattern = re.compile(rf"""el\(\s*["']{tag}["']\s*,\s*\{{[^}}]*\bvalue\s*:""")
    for module in _modules():
        assert not pattern.search(module.read_text()), (
            f'{module.name}: el("{tag}", {{ value: … }}) is silently ignored — '
            f"assign the .value property after constructing it"
        )


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
