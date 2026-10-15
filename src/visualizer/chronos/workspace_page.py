"""The workspace: the shell a React bundle mounts into.

    GET /?ui=next#/<book>/...

The classic visualiser at ``/`` is this app's own JavaScript (``static/js``);
the workspace is compiled from ``frontend/src/chronos`` (React, TypeScript)
into ``static/workspace/``, like Akasha's research studio and Logos's writing
page. It reads the same hash addresses as the classic page, so any link into
one opens the same place in the other, and ``?ui=next`` is the only difference
until the workspace becomes the default.

The page reveals nothing but who is signed in. Everything it shows comes from
the same JSON API the classic page calls, which authorises every request.
"""

from pathlib import Path

from flask import render_template, request
from flask_login import current_user

from visualizer import vite_assets

WORKSPACE_DIR = Path(__file__).resolve().parent / "static" / "workspace"
MANIFEST = WORKSPACE_DIR / ".vite" / "manifest.json"
ENTRY = "src/chronos/main.tsx"


def manifest_assets(path: Path = MANIFEST) -> vite_assets.BundleAssets:
    """The workspace's entry in the manifest at ``path``, read on every request."""
    return vite_assets.manifest_assets(path, ENTRY)


def is_workspace_request() -> bool:
    return request.args.get("ui") == "next"


def render_workspace(assets: dict | None) -> str:
    return render_template(
        "workspace.html",
        assets=assets,
        base=request.script_root,
        username=current_user.username,
    )
