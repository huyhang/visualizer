"""The whole stack, wired: every service over one MongoDB, behind one origin.

akasha at ``/``, chronos at ``/timeline``, prithvi at ``/prithvi``, logos at
``/logos``. One ``AuthStore`` is shared between them (exactly as the split
deployment already shares Mongo), so a single login covers all of them and
there is no cross-service HTTP.

``build_application`` takes what its two callers disagree about: the Mongo
client, and optionally the GPU-box worker. ``visualizer.wsgi`` hands it a real
``MongoClient`` for gunicorn and lets the worker come from ``GPU_WORKER_URL``;
``visualizer.devserver`` hands it an in-memory client and, if asked, a fake box.
Every other setting is read from the environment by the same ``config``
helpers either way, so the dev server runs the production wiring rather than a
copy of it.
"""

import os

from visualizer.akasha.app import create_app as create_akasha_app
from visualizer.akasha.config import (
    get_glb_limits,
    get_image_processor,
    get_rate_limit_storage_uri,
    get_secret_key,
    get_secure_cookies,
    get_versions_keep,
)
from visualizer.akasha.media_service import build_media_service
from visualizer.akasha.research import RemoteResearcher
from visualizer.akasha.research_jobs import ResearchJobStore
from visualizer.akasha.store import DocumentStore
from visualizer.auth import AuthStore
from visualizer.chronos.app import create_app as create_chronos_app
from visualizer.chronos.entity_gate import InProcessEntityGate
from visualizer.chronos.errors import ChronosError
from visualizer.chronos.store import CalendarStore, StoryStore
from visualizer.gpubox import worker_from_env
from visualizer.logos.app import create_app as create_logos_app
from visualizer.logos.config import get_section_revisions_keep
from visualizer.logos.gateways import (
    InProcessArticleGateway as InProcessLogosArticleGateway,
)
from visualizer.logos.gateways import InProcessChronosGateway, LogosReferenceGate
from visualizer.logos.llm_review import RemoteReviewer
from visualizer.logos.llm_review_jobs import LlmReviewStore
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


def build_application(client, gpu_worker=None):
    """The combined WSGI callable, every service wired over ``client``.

    ``gpu_worker`` defaults to whatever ``GPU_WORKER_URL`` configures, which is
    usually nothing: research and LLM review then report themselves off and the
    stack runs as it always has.
    """
    worker = gpu_worker if gpu_worker is not None else worker_from_env()
    auth_store = AuthStore(client)
    doc_store = DocumentStore(client, versions_keep=get_versions_keep())
    secret = get_secret_key()
    secure = get_secure_cookies()
    ratelimit = get_rate_limit_storage_uri()
    # All four share one recorder and one background flusher: they are the
    # same process, and the service label on each sample keeps them apart.
    observability = observability_runtime.start(client, auth_store)

    # Behind one origin the service nav's links are relative paths, not
    # cross-origin URLs. Overridable, but these are the right defaults here.
    akasha_url = os.environ.get("AKASHA_URL", "/")
    chronos_url = os.environ.get("CHRONOS_URL", DEFAULT_CHRONOS_PREFIX)
    prithvi_url = os.environ.get("PRITHVI_URL", DEFAULT_PRITHVI_PREFIX)
    logos_url = os.environ.get("LOGOS_URL", DEFAULT_LOGOS_PREFIX)

    story_store = StoryStore(client)
    logos_store = LogosStore(
        client, section_revisions_keep=get_section_revisions_keep()
    )

    def book_world(book: str) -> str | None:
        """Which world a book is set in -- what makes sharing a book share it too.

        Passed into akasha rather than looked up there: the account page serves
        one of the two routes that can share a book, and this is the one fact
        about Chronos it needs to behave the same as the other.
        """
        try:
            return story_store.get_book(book).get("world")
        except ChronosError:
            return None

    akasha_app = create_akasha_app(
        doc_store,
        auth_store,
        secret_key=secret,
        book_world=book_world,
        user_cleanup=logos_store.purge_user,
        secure_cookies=secure,
        rate_limit_storage_uri=ratelimit,
        akasha_url=akasha_url,
        chronos_url=chronos_url,
        prithvi_url=prithvi_url,
        logos_url=logos_url,
        observability=observability,
        media_service=build_media_service(
            client, get_image_processor(), get_glb_limits()
        ),
        researcher=RemoteResearcher(worker) if worker is not None else None,
        research_jobs=ResearchJobStore(client) if worker is not None else None,
    )
    chronos_app = create_chronos_app(
        story_store,
        InProcessEntityGate(doc_store),
        auth_store,
        calendar_store=CalendarStore(client),
        manuscript_gate=LogosReferenceGate(logos_store),
        secret_key=secret,
        secure_cookies=secure,
        rate_limit_storage_uri=ratelimit,
        akasha_url=akasha_url,
        chronos_url=chronos_url,
        prithvi_url=prithvi_url,
        logos_url=logos_url,
        observability=observability,
    )
    logos_app = create_logos_app(
        logos_store,
        InProcessChronosGateway(story_store),
        InProcessLogosArticleGateway(doc_store),
        auth_store,
        secret_key=secret,
        secure_cookies=secure,
        rate_limit_storage_uri=ratelimit,
        akasha_url=akasha_url,
        chronos_url=chronos_url,
        prithvi_url=prithvi_url,
        logos_url=logos_url,
        observability=observability,
        reviewer=RemoteReviewer(worker) if worker is not None else None,
        llm_reviews=LlmReviewStore(client) if worker is not None else None,
    )
    prithvi_app = create_prithvi_app(
        PrithviStore(
            client,
            map_revisions_keep=get_map_revisions_keep(),
            pin_revisions_keep=get_pin_revisions_keep(),
        ),
        InProcessArticleGateway(doc_store),
        auth_store,
        secret_key=secret,
        max_svg_bytes=get_max_svg_bytes(),
        secure_cookies=secure,
        rate_limit_storage_uri=ratelimit,
        akasha_url=akasha_url,
        chronos_url=chronos_url,
        prithvi_url=prithvi_url,
        logos_url=logos_url,
        observability=observability,
    )

    # One WSGI callable: akasha at "/", chronos at "/timeline", prithvi at
    # "/prithvi", logos at "/logos".
    return combine(
        akasha_app,
        chronos_app,
        prithvi_app=prithvi_app,
        logos_app=logos_app,
    )
