"""The research studio: one page per world, drawn by a React bundle.

    GET /studio/<world>    the shell -- service nav, header, and a root the
                           bundle mounts into

The studio is Akasha's first surface built with a toolchain (React,
TypeScript, Vite; sources in ``frontend/``). Vite compiles it into
``static/studio/`` and writes a manifest naming the hashed files; the shell
reads that manifest to know what to load. Nothing here needs Node at run
time, and the page loads nothing from outside this origin.

The bundle lookup is injected, like every other boundary in this app, so the
page is testable without a build -- and a build that is missing says so on
the page rather than serving a blank one.

The page itself reveals nothing but the world's name, which is in its URL;
everything it shows comes from the research and document APIs, which
authorise every call.
"""

from pathlib import Path

from flask import Flask, render_template, request
from flask_login import current_user, login_required

from visualizer import vite_assets

from .labels import derive_title
from .routing import reject_reserved

STUDIO_DIR = Path(__file__).resolve().parent / "static" / "studio"
MANIFEST = STUDIO_DIR / ".vite" / "manifest.json"
ENTRY = "src/main.tsx"

StudioAssets = vite_assets.BundleAssets


def entry_assets(manifest: dict, entry: str = ENTRY) -> dict | None:
    """The studio's script and stylesheets, relative to ``static/studio/``."""
    return vite_assets.entry_assets(manifest, entry)


def manifest_assets(path: Path = MANIFEST) -> StudioAssets:
    """The studio's entry in the manifest at ``path``, read on every request."""
    return vite_assets.manifest_assets(path, ENTRY)


def register_studio_routes(app: Flask, assets: StudioAssets | None = None) -> None:
    assets = assets or manifest_assets()

    @app.get("/studio/<database>")
    @login_required
    def research_studio(database):
        reject_reserved(database)
        return render_template(
            "studio.html",
            world=database,
            world_title=derive_title(database),
            assets=assets(),
            api_root=request.script_root,
            username=current_user.username,
        )
