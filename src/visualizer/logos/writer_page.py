"""The writing page: the shell a React bundle mounts into.

    GET /?book=…&volume=…&section=…&mode=write[&draft=…][&block=…][&panel=…]

The reader and the contents page are this app's own JavaScript; the writing
page is compiled from ``frontend/src/logos`` (React, TypeScript, Tiptap) into
``static/writer/``, like Akasha's research studio. Its address is the one the
writer always had, so every link into it -- the reader's Edit, the contents
page, the series Review's coaching rows -- keeps working.

The page reveals nothing but who is signed in. Everything it shows comes from
the manuscript, draft and review APIs, which authorise every call; a reader
without write access is sent back to the reader by the bundle when the
manuscript says so.
"""

from pathlib import Path

from flask import render_template, request
from flask_login import current_user

from visualizer import vite_assets

WRITER_DIR = Path(__file__).resolve().parent / "static" / "writer"
MANIFEST = WRITER_DIR / ".vite" / "manifest.json"
ENTRY = "src/logos/main.tsx"


def manifest_assets(path: Path = MANIFEST) -> vite_assets.BundleAssets:
    """The writer's entry in the manifest at ``path``, read on every request."""
    return vite_assets.manifest_assets(path, ENTRY)


def is_writer_request() -> bool:
    return request.args.get("mode") == "write"


def render_writer(assets: dict | None) -> str:
    return render_template(
        "writer.html",
        assets=assets,
        base=request.script_root,
        username=current_user.username,
    )
