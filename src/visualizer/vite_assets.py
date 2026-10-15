"""Pages drawn by a bundle from ``frontend/``: finding the files a build made.

Vite compiles each React surface into its app's static folder and writes a
manifest naming the hashed files; a page shell reads that manifest to know
what to link. Akasha's research studio and Logos's writing page both work
this way, so the lookup lives here rather than in either app.

The manifest is read on every request: a rebuild (``npm run watch``) shows up
on the next reload, and the file is a few hundred bytes. Nothing here needs
Node at run time, and a build that is missing comes back as ``None`` so the
shell can say so instead of serving a blank page.
"""

import json
from collections.abc import Callable
from pathlib import Path

BundleAssets = Callable[[], dict | None]


def entry_assets(manifest: dict, entry: str) -> dict | None:
    """The script and stylesheets the page links, from a Vite manifest.

    Paths are relative to the build's folder. ``None`` when the manifest has
    no such entry -- a build of something else, or of nothing.
    """
    chunk = manifest.get(entry)
    if not isinstance(chunk, dict) or not isinstance(chunk.get("file"), str):
        return None
    styles = list(chunk.get("css") or [])
    # CSS imported by shared chunks is listed on those chunks, not the entry.
    for name in chunk.get("imports") or []:
        styles += (manifest.get(name) or {}).get("css") or []
    return {"script": chunk["file"], "styles": list(dict.fromkeys(styles))}


def manifest_assets(path: Path, entry: str) -> BundleAssets:
    """A lookup of ``entry`` in the manifest at ``path``, read afresh each call."""

    def load() -> dict | None:
        try:
            return entry_assets(json.loads(path.read_text()), entry)
        except (OSError, ValueError):
            return None

    return load
