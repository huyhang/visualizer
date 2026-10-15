"""Static files a page can keep for a year, and still never run stale.

Flask serves static files with ``Cache-Control: no-cache``: the browser keeps
them but asks the server again on every page, a round trip each. A page with
no build step loads many small files -- the Logos reader, its stylesheets and
eighteen modules -- and over a slow link those questions are most of its load.

So a template names a file with its content in the address,
``versioned("static", "js/app.js")`` -> ``/static/js/app.js?v=3f9c2a...``, and a
request carrying the version of the file as it is *now* is answered as
cacheable for a year and never to be asked about again (``immutable``). A
deploy changes the content, so the page names a new address and the browser
fetches it once. A request with no version, or one that no longer matches,
is answered as before.

Modules find each other by relative imports (``./api.js``), which carry no
version; ``import_map`` maps each module's plain address to its versioned
one, and the browser applies it to every import. A browser without import
maps fetches the plain addresses, uncached as before: slower, never stale.
"""

import hashlib
from functools import lru_cache
from pathlib import Path

from flask import Flask, current_app, request, url_for
from werkzeug.utils import safe_join

from .shared_assets import SHARED_JS, SHARED_STATIC

ONE_YEAR = 365 * 24 * 60 * 60


@lru_cache(maxsize=1024)
def _digest(path: str, mtime_ns: int, size: int) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


def file_version(path: Path | str | None) -> str | None:
    """A short digest of the file's content, or None when there is no such file.
    Read again only when the file's modification time or size changes."""
    if path is None:
        return None
    try:
        stat = Path(path).stat()
    except OSError:
        return None
    return _digest(str(path), stat.st_mtime_ns, stat.st_size)


def _folder(endpoint: str) -> str | None:
    if endpoint == "static":
        return current_app.static_folder
    if endpoint == "shared_static":
        return str(SHARED_STATIC)
    if endpoint == "shared_js":
        return str(SHARED_JS)
    return None


def _path(endpoint: str, filename: str) -> str | None:
    folder = _folder(endpoint)
    return safe_join(folder, filename) if folder else None


def versioned(endpoint: str, filename: str) -> str:
    """``url_for(endpoint, filename=...)`` with the file's version in it."""
    version = file_version(_path(endpoint, filename))
    if version is None:
        return url_for(endpoint, filename=filename)
    return url_for(endpoint, filename=filename, v=version)


def import_map(endpoint: str, filenames) -> dict:
    """Each module's plain address mapped to its versioned one, for
    ``<script type="importmap">``: relative imports then fetch cacheable files."""
    return {
        "imports": {
            url_for(endpoint, filename=name): versioned(endpoint, name) for name in filenames
        }
    }


def install_versioned_static(app: Flask) -> None:
    """Offer ``versioned`` to templates, and cache what it names for a year."""
    app.jinja_env.globals["versioned"] = versioned

    @app.after_request
    def cache_versioned(response):
        asked = request.args.get("v")
        filename = (request.view_args or {}).get("filename")
        if not asked or not filename or response.status_code not in (200, 304):
            return response
        if asked != file_version(_path(request.endpoint or "", filename)):
            return response
        response.cache_control.no_cache = None
        response.cache_control.public = True
        response.cache_control.max_age = ONE_YEAR
        response.cache_control.immutable = True
        return response
