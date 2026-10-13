"""The worker stands alone: it imports nothing from the stack, and vice versa.

That is what lets ``docker/Dockerfile.worker`` copy only this package onto the
GPU box -- and what would let it move to its own repository unchanged. The one
thing the two sides share is the contract document, read at runtime.
"""

import ast
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "visualizer"
WORKER = SRC / "gpu_worker"
# Third-party packages the worker may use; each is installed by
# requirements-worker.txt (werkzeug with flask, referencing with jsonschema).
WORKER_DEPENDENCIES = {"flask", "werkzeug", "jsonschema", "referencing"}


def imports(path: Path):
    """Absolute module names imported by one file (relative imports skipped)."""
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module


def test_the_worker_imports_only_itself_the_stdlib_and_its_dependencies():
    offenders = []
    for path in WORKER.rglob("*.py"):
        for name in imports(path):
            top = name.split(".")[0]
            if name == "visualizer.gpu_worker" or name.startswith("visualizer.gpu_worker."):
                continue
            if top in sys.stdlib_module_names or top in WORKER_DEPENDENCIES:
                continue
            offenders.append(f"{path.relative_to(SRC)}: {name}")
    assert not offenders, offenders


def test_nothing_in_the_stack_imports_the_worker():
    offenders = [
        f"{path.relative_to(SRC)}: {name}"
        for path in SRC.rglob("*.py") if WORKER not in path.parents
        for name in imports(path) if name.startswith("visualizer.gpu_worker")
    ]
    assert not offenders, offenders
