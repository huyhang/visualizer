"""Single-origin composition of the two services.

akasha and chronos already share one MongoDB, one ``_auth`` store, one secret and
always ship together -- chronos even calls akasha in-process (the ``EntityGate``
wraps akasha's ``DocumentStore``). This mounts them behind one WSGI callable so a
single port/origin serves both (akasha at ``/``, chronos under a prefix): one
reverse-proxy entry, one cookie, no CORS -- the natural shape for the Synology
reverse-proxy deployment.

The composition is a plain function taking the two already-built apps, so it is
trivially unit-testable; ``visualizer.wsgi`` does the real wiring.
"""

from werkzeug.middleware.dispatcher import DispatcherMiddleware

# Where chronos lives under the shared origin. Flask sets SCRIPT_NAME to this for
# mounted requests, so chronos's own ``url_for`` (templates, static) is prefixed
# automatically; its hand-written fetch paths read the prefix from
# ``request.script_root`` (injected into the page as ``window.__BASE__``).
DEFAULT_CHRONOS_PREFIX = "/timeline"


def combine(akasha_app, chronos_app, chronos_prefix: str = DEFAULT_CHRONOS_PREFIX):
    """Serve ``akasha_app`` at ``/`` and ``chronos_app`` under ``chronos_prefix``."""
    return DispatcherMiddleware(akasha_app, {chronos_prefix: chronos_app})
