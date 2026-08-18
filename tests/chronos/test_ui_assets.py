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


# Factories a caller writes as `const thing = factory({onChange: () => refresh()})`,
# where `refresh` reads `thing`. Each paints itself once while being constructed,
# and must not report that first paint as a change: the caller's `const` is still
# in its temporal dead zone, so an onChange that touches it throws a
# ReferenceError before anything is on screen. Both guard it with a `notify`
# flag defaulting to true, passed false for the first paint only.
_FIRST_PAINT_MUST_BE_SILENT = [
    ("calendarfield.js", "rebuild(null, false)"),
    ("calendarlist.js", "rebuild(false)"),
]


@pytest.mark.parametrize("module,silent_call", _FIRST_PAINT_MUST_BE_SILENT,
                         ids=lambda v: v if v.endswith(".js") else "")
def test_a_factorys_first_paint_does_not_call_back_into_its_caller(module, silent_call):
    """Nothing else in this suite can see this failure, and it is total.

    It took out both the book form's *Edit* and *+ New book* once already: the
    list rebuilt itself on construction, notified, and the caller's `refresh`
    asked the half-assigned `const` for its problems. Python cannot run the
    module, but it can check that the one call which happens during construction
    is the silent form.
    """
    source = (_JS_DIR / module).read_text()
    assert silent_call in source, (
        f"{module}'s first paint must be the non-notifying call `{silent_call}` "
        "-- see the note above this test"
    )


# Comments and string/template literals are not code: a hint that reads
# "Era (optional)" or a template like `hsl(${h} 60% 50%)` would otherwise look
# like a call to a function named `Era` or `hsl`.
_NOT_CODE = re.compile(r"//[^\n]*|/\*.*?\*/|`(?:\\.|[^`\\])*`|'(?:\\.|[^'\\])*'"
                       r'|"(?:\\.|[^"\\])*"', re.DOTALL)
# A call to a bare name -- `foo(...)`, not `x.foo(...)`, and not the `foo(` that
# *declares* one (`function foo(`, `get foo(`, a class method).
_CALL = re.compile(r"(?<!function )(?<!class )(?<!get )(?<!set )(?<![.\w$])"
                   r"([A-Za-z_$][\w$]*)\s*\(")
_NOT_A_HELPER = {
    "if", "for", "while", "switch", "catch", "return", "typeof", "await", "new",
    "delete", "void", "in", "of", "do", "else", "function", "class", "async",
    "constructor", "super", "this",
    "Array", "Boolean", "Date", "Error", "JSON", "Map", "Math", "Number", "Object",
    "Promise", "Set", "String", "URLSearchParams", "ResizeObserver", "AbortController",
    "clearTimeout", "setTimeout", "clearInterval", "setInterval", "fetch",
    "requestAnimationFrame", "queueMicrotask", "parseInt", "parseFloat", "isNaN",
    "encodeURIComponent", "decodeURIComponent", "structuredClone",
    "getComputedStyle", "MutationObserver",
    "document", "window", "console",
}
# `$` is a legal identifier but not a word character, so `\b` will not do.
_EDGE = r"(?![\w$])"


@pytest.mark.parametrize("module", _modules() + _shared_modules(), ids=lambda p: p.name)
def test_a_module_never_calls_a_name_it_has_nothing_to_do_with(module):
    """Catches a refactor that deletes a helper and leaves its callers behind.

    That has taken the book form out twice -- once via a temporal-dead-zone
    callback, once when a splice removed `updateOffer` while its call site
    survived. Both were total (the form threw before rendering anything) and
    both were invisible to every other check here, which look *between* modules
    and never inside one.

    Deliberately narrow rather than a real scope analysis: a name is flagged
    only when the file calls it and then never mentions it again anywhere --
    not as a declaration, not as a parameter, not as an import. A function
    deleted out from under its callers looks exactly like that, and very little
    else does, so it stays quiet about locals, destructuring and callbacks
    without having to understand any of them.
    """
    source = _NOT_CODE.sub(" ", module.read_text())
    imported = {name for _, names in _imports(module) for name in names}
    orphans = []
    for name in sorted(set(_CALL.findall(source)) - _NOT_A_HELPER - imported):
        quoted = re.escape(name)
        # Everything except this name in call position. A declaration survives,
        # because _CALL never matched it in the first place.
        elsewhere = re.sub(rf"(?<!function )(?<!class )(?<!get )(?<!set )(?<![.\w$])"
                           rf"{quoted}\s*\(", " ", source)
        if not re.search(rf"(?<![.\w$]){quoted}{_EDGE}", elsewhere):
            orphans.append(name)
    assert not orphans, (
        f"{module.name} calls {orphans}, which it never declares, imports or "
        "mentions anywhere else -- a deleted helper with live call sites"
    )


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
    # ``calendars``, plural and spelled out: a book keeps a list of parallel
    # reckonings now, and "calendar" would go on passing against it by accident
    # while pinning nothing.
    ("bookform.js", ("title", "overview", "calendars", "world", "terminus")),
    ("plotedit.js", ("title", "overview", "events", "goals", "continues_into",
                     "continues_into_at")),
    # A goal's two references are the whole point of it being a record, and both
    # are easy to drop from a hand-built payload: omitting `depends_on` unpicks
    # the graph, omitting `achieved_at` un-achieves the goal. Neither raises.
    ("goalform.js", ("title", "description", "depends_on", "achieved_at")),
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


def test_the_attachment_list_names_a_calendar_and_does_not_carry_one():
    """The book form's `body()` sends `calendars`, and the check above stops at
    that word — but the *shape* of each entry is built a module away.

    Two halves. Dropping `source` would sever every book's link to the library
    on the next save: no update offer would ever appear again, and nothing would
    raise. Dropping `until_tick` would quietly un-end a calendar that had ended.

    And `descriptor` must stay *absent*. The library is where calendars are
    authored; the server reads the descriptor from it. Sending one back would be
    refused outright now (`INVALID_BOOK`), so this half of the pin is really
    guarding against a well-meaning re-addition breaking every save.
    """
    source = (_JS_DIR / "calendarlist.js").read_text()
    start = source.index("value: () =>")
    block = source[start : source.index("problems:", start)]
    missing = [f for f in ("id", "label", "source", "from_tick", "until_tick")
               if f"{f}:" not in block]
    assert not missing, f"calendarlist.js value() never sends {missing}"
    assert "descriptor:" not in block, (
        "calendarlist.js value() sends a descriptor — a book names a library "
        "calendar, it does not describe one, and the API refuses the payload"
    )


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


_CSS = Path(__file__).resolve().parents[2] / "src" / "visualizer" / "chronos" / "static" / "visualizer.css"


def test_the_stylesheet_lets_hidden_win():
    """Setting `.hidden` must actually hide, whatever classes the node carries.

    `[hidden] { display: none }` lives in the *user-agent* stylesheet, so any
    author rule beats it -- and `!important` is needed rather than mere source
    order, because the author rules that collide with it (`.field-row`,
    `.date-end`) have the same specificity and come later.

    This cost the scene form's Date/Tick toggle: the JS set `.hidden` on both
    rows correctly and neither ever disappeared, because `.field-row` is
    `display: flex`. Nothing else in the suite can see that -- the JS tests run
    against a fake DOM with no CSS at all -- so the rule is pinned here.
    """
    css = _CSS.read_text()
    rule = re.search(r"\[hidden\]\s*\{([^}]*)\}", css)
    assert rule, "no [hidden] rule: an element with a display of its own will not hide"
    body = rule.group(1)
    assert "display" in body and "none" in body, f"[hidden] does not set display:none: {body!r}"
    assert "!important" in body, (
        f"[hidden] must be !important to beat same-specificity author rules: {body!r}"
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
