"""Single-origin composition of the services.

They already share one MongoDB, one ``_auth`` store, one secret and always ship
together, and each cross-service question is asked in-process through a small
injected gateway rather than over HTTP -- chronos and prithvi read akasha's
``DocumentStore``, logos reads chronos's ``StoryStore`` and akasha's, and chronos
asks logos whether prose depends on what it is about to delete. This mounts them
behind one WSGI callable so a single port/origin serves all of them (akasha at
``/``, the others under prefixes): one reverse-proxy entry, one cookie, no CORS
-- the natural shape for the Synology reverse-proxy deployment.

The composition is a plain function taking already-built apps, so it is
trivially unit-testable; ``visualizer.wsgi`` does the real wiring. Prithvi and
logos are optional so that the smaller calls this function has always accepted
keep working, and so a test can compose only the parts it cares about.
"""

from werkzeug.middleware.dispatcher import DispatcherMiddleware

# Where chronos lives under the shared origin. Flask sets SCRIPT_NAME to this for
# mounted requests, so chronos's own ``url_for`` (templates, static) is prefixed
# automatically; its hand-written fetch paths read the prefix from
# ``request.script_root`` (injected into the page as ``window.__BASE__``).
DEFAULT_CHRONOS_PREFIX = "/timeline"
DEFAULT_PRITHVI_PREFIX = "/prithvi"
DEFAULT_LOGOS_PREFIX = "/logos"


def combine(
    akasha_app,
    chronos_app,
    chronos_prefix: str = DEFAULT_CHRONOS_PREFIX,
    *,
    prithvi_app=None,
    prithvi_prefix: str = DEFAULT_PRITHVI_PREFIX,
    logos_app=None,
    logos_prefix: str = DEFAULT_LOGOS_PREFIX,
):
    """Serve ``akasha_app`` at ``/`` and each other app under its prefix."""
    mounts = {chronos_prefix: chronos_app}
    if prithvi_app is not None:
        mounts[prithvi_prefix] = prithvi_app
    if logos_app is not None:
        mounts[logos_prefix] = logos_app
    return DispatcherMiddleware(akasha_app, mounts)
