"""The reader's ES modules, named up front so the browser can fetch them at once.

The reader has no build step: ``app.js`` imports its modules, which import
theirs, and a browser only learns of each layer once the one before has
arrived -- a round trip per layer before the page can run. The shell lists
every module ``app.js`` reaches as ``<link rel="modulepreload">``, so they are
all asked for while the page itself is still being read.

The list is read from the modules' own ``import`` lines, so it cannot drift
from them; it is worked out once per process, since the files only change
with a deploy (or a restart of the development server).
"""

import re
from functools import cache
from pathlib import Path

JS_DIR = Path(__file__).resolve().parent / "static" / "js"
ENTRY = "app.js"

# A static import of a sibling module: `import { a } from "./x.js"`, `import "./x.js"`.
_IMPORT = re.compile(r'import\s+(?:[\w${},\s*]+?\s+from\s+)?["\'](\./[^"\']+)["\']')


def module_graph(js_dir: Path = JS_DIR, entry: str = ENTRY) -> list[str]:
    """Every module ``entry`` reaches, by its path under ``js_dir``, in the
    order they are first met (the entry itself excluded: the page loads it)."""
    reached: list[str] = []
    queue = [entry]
    seen = {entry}
    while queue:
        current = js_dir / queue.pop(0)
        if not current.is_file():
            continue
        for target in _IMPORT.findall(current.read_text()):
            name = (current.parent / target).resolve().relative_to(js_dir.resolve()).as_posix()
            if name not in seen:
                seen.add(name)
                reached.append(name)
                queue.append(name)
    return reached


@cache
def reader_modules() -> tuple[str, ...]:
    """The reader's modules to preload, read once per process."""
    return tuple(module_graph())
