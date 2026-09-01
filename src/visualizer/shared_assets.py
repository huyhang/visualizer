"""Static assets both services load, served once from the package root.

Akasha and Chronos are separate Flask apps with separate ``static/`` folders and
**no build step** (``test_ui_assets`` rejects bare/bundler specifiers), so a
module in one tree cannot import from the other. Until this existed, anything
both needed was copied -- and the copies drifted.

The trick is *where* it is served rather than where it lives. Each app exposes
the shared directory beneath its own static path::

    akasha  (mounted at /)          /static/js/shared/slug.js
    chronos (mounted at /timeline)  /timeline/static/js/shared/slug.js
    chronos (standalone, own port)  /static/js/shared/slug.js

so a module in either tree writes the same **relative** specifier --
``./shared/slug.js`` -- and it resolves at every mount, including the
per-service entrypoints used in development. An absolute ``/shared/...`` would
resolve to whichever app happens to own ``/``, which is the gateway's business
and not something the browser code should encode (the same reason ``api.js``
computes ``BASE`` instead of hardcoding a prefix).

Page-level assets that are not modules -- the service navigation's stylesheet --
go through the sibling ``shared_static`` route. Those are named by ``url_for``
from a template rather than imported by a specifier, so they need no relative
path of their own; ``url_for`` already supplies each host app's prefix.
"""

from pathlib import Path

from flask import Flask, send_from_directory

SHARED_STATIC = Path(__file__).resolve().parent / "static"
SHARED_JS = SHARED_STATIC / "js"

# Beneath each app's own ``/static`` rather than a sibling of it, so the
# specifier stays relative. More static path segments than Flask's
# ``/static/<path:filename>``, so Werkzeug prefers this rule -- asserted by
# ``test_shared_assets``.
_URL = "/static/js/shared/<path:filename>"
_SHARED_URL = "/static/shared/<path:filename>"


def register_shared_assets(app: Flask) -> None:
    """Serve the package-level shared assets under this app's static path."""

    @app.get(_URL, endpoint="shared_js")
    def shared_js(filename: str):
        return send_from_directory(SHARED_JS, filename)

    @app.get(_SHARED_URL, endpoint="shared_static")
    def shared_static(filename: str):
        return send_from_directory(SHARED_STATIC, filename)
