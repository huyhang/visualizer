"""Combined production entrypoint: both services on one port/origin.

akasha at ``/``, chronos at ``/timeline``. One ``MongoClient`` and one
``AuthStore`` are shared between them (exactly as the split deployment already
shares Mongo), so a single login covers both and there is no cross-service HTTP.
Run with ``gunicorn visualizer.wsgi:application``.

The per-service entrypoints (``visualizer.akasha.wsgi`` / ``visualizer.chronos.wsgi``)
still exist for running a service standalone in development.
"""

import os

from visualizer.akasha.app import create_app as create_akasha_app
from visualizer.akasha.config import (
    get_mongo_client,
    get_rate_limit_storage_uri,
    get_secret_key,
    get_secure_cookies,
    get_versions_keep,
)
from visualizer.akasha.store import DocumentStore
from visualizer.auth import AuthStore
from visualizer.chronos.app import create_app as create_chronos_app
from visualizer.chronos.entity_gate import InProcessEntityGate
from visualizer.chronos.store import StoryStore

from .gateway import DEFAULT_CHRONOS_PREFIX, combine

_client = get_mongo_client()
_auth_store = AuthStore(_client)
_doc_store = DocumentStore(_client, versions_keep=get_versions_keep())
_secret = get_secret_key()
_secure = get_secure_cookies()
_ratelimit = get_rate_limit_storage_uri()

# Behind one origin the header switcher's links are relative paths, not
# cross-origin URLs. Overridable, but these are the right defaults here.
_akasha_url = os.environ.get("AKASHA_URL", "/")
_chronos_url = os.environ.get("CHRONOS_URL", DEFAULT_CHRONOS_PREFIX)

_akasha_app = create_akasha_app(
    _doc_store,
    _auth_store,
    secret_key=_secret,
    secure_cookies=_secure,
    rate_limit_storage_uri=_ratelimit,
    akasha_url=_akasha_url,
    chronos_url=_chronos_url,
)
_chronos_app = create_chronos_app(
    StoryStore(_client),
    InProcessEntityGate(_doc_store),
    _auth_store,
    secret_key=_secret,
    secure_cookies=_secure,
    rate_limit_storage_uri=_ratelimit,
    akasha_url=_akasha_url,
    chronos_url=_chronos_url,
)

# One WSGI callable for gunicorn: akasha at "/", chronos at "/timeline".
application = combine(_akasha_app, _chronos_app)
