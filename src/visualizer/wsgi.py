"""Combined production entrypoint: every service on one port/origin.

akasha at ``/``, chronos at ``/timeline``, prithvi at ``/prithvi``, logos at
``/logos``. One ``MongoClient`` and one ``AuthStore`` are shared between them
(exactly as the split deployment already shares Mongo), so a single login covers
all of them and there is no cross-service HTTP. Run with
``gunicorn visualizer.wsgi:application``.

The per-service entrypoints (``visualizer.akasha.wsgi`` and its siblings) still
exist for running one service standalone in development.
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
from visualizer.chronos.errors import ChronosError
from visualizer.chronos.store import CalendarStore, StoryStore
from visualizer.logos.app import create_app as create_logos_app
from visualizer.logos.config import get_section_revisions_keep
from visualizer.logos.gateways import (
    InProcessArticleGateway as InProcessLogosArticleGateway,
)
from visualizer.logos.gateways import InProcessChronosGateway, LogosReferenceGate
from visualizer.logos.store import LogosStore
from visualizer.observability import runtime as observability_runtime
from visualizer.prithvi.app import create_app as create_prithvi_app
from visualizer.prithvi.articles import InProcessArticleGateway
from visualizer.prithvi.config import (
    get_map_revisions_keep,
    get_max_svg_bytes,
    get_pin_revisions_keep,
)
from visualizer.prithvi.store import PrithviStore

from .gateway import (
    DEFAULT_CHRONOS_PREFIX,
    DEFAULT_LOGOS_PREFIX,
    DEFAULT_PRITHVI_PREFIX,
    combine,
)

_client = get_mongo_client()
_auth_store = AuthStore(_client)
_doc_store = DocumentStore(_client, versions_keep=get_versions_keep())
_secret = get_secret_key()
_secure = get_secure_cookies()
_ratelimit = get_rate_limit_storage_uri()
# All four share one recorder and one background flusher: they are the
# same process, and the service label on each sample keeps them apart.
_observability = observability_runtime.start(_client, _auth_store)

# Behind one origin the service nav's links are relative paths, not
# cross-origin URLs. Overridable, but these are the right defaults here.
_akasha_url = os.environ.get("AKASHA_URL", "/")
_chronos_url = os.environ.get("CHRONOS_URL", DEFAULT_CHRONOS_PREFIX)
_prithvi_url = os.environ.get("PRITHVI_URL", DEFAULT_PRITHVI_PREFIX)
_logos_url = os.environ.get("LOGOS_URL", DEFAULT_LOGOS_PREFIX)

_story_store = StoryStore(_client)
_logos_store = LogosStore(
    _client, section_revisions_keep=get_section_revisions_keep()
)


def _book_world(book: str) -> str | None:
    """Which world a book is set in -- what makes sharing a book share it too.

    Passed into akasha rather than looked up there: the account page serves one
    of the two routes that can share a book, and this is the one fact about
    Chronos it needs to behave the same as the other.
    """
    try:
        return _story_store.get_book(book).get("world")
    except ChronosError:
        return None


_akasha_app = create_akasha_app(
    _doc_store,
    _auth_store,
    secret_key=_secret,
    book_world=_book_world,
    user_cleanup=_logos_store.purge_user,
    secure_cookies=_secure,
    rate_limit_storage_uri=_ratelimit,
    akasha_url=_akasha_url,
    chronos_url=_chronos_url,
    prithvi_url=_prithvi_url,
    logos_url=_logos_url,
    observability=_observability,
)
_chronos_app = create_chronos_app(
    _story_store,
    InProcessEntityGate(_doc_store),
    _auth_store,
    calendar_store=CalendarStore(_client),
    manuscript_gate=LogosReferenceGate(_logos_store),
    secret_key=_secret,
    secure_cookies=_secure,
    rate_limit_storage_uri=_ratelimit,
    akasha_url=_akasha_url,
    chronos_url=_chronos_url,
    prithvi_url=_prithvi_url,
    logos_url=_logos_url,
    observability=_observability,
)
_logos_app = create_logos_app(
    _logos_store,
    InProcessChronosGateway(_story_store),
    InProcessLogosArticleGateway(_doc_store),
    _auth_store,
    secret_key=_secret,
    secure_cookies=_secure,
    rate_limit_storage_uri=_ratelimit,
    akasha_url=_akasha_url,
    chronos_url=_chronos_url,
    prithvi_url=_prithvi_url,
    logos_url=_logos_url,
    observability=_observability,
)
_prithvi_app = create_prithvi_app(
    PrithviStore(
        _client,
        map_revisions_keep=get_map_revisions_keep(),
        pin_revisions_keep=get_pin_revisions_keep(),
    ),
    InProcessArticleGateway(_doc_store),
    _auth_store,
    secret_key=_secret,
    max_svg_bytes=get_max_svg_bytes(),
    secure_cookies=_secure,
    rate_limit_storage_uri=_ratelimit,
    akasha_url=_akasha_url,
    chronos_url=_chronos_url,
    prithvi_url=_prithvi_url,
    logos_url=_logos_url,
    observability=_observability,
)

# One WSGI callable for gunicorn: akasha at "/", chronos at "/timeline",
# prithvi at "/prithvi", logos at "/logos".
application = combine(
    _akasha_app,
    _chronos_app,
    prithvi_app=_prithvi_app,
    logos_app=_logos_app,
)
