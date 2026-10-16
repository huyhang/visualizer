"""Standalone production entrypoint for Logos, on its own port.

The combined deployment (``visualizer.wsgi``) is the one the stack ships with;
this exists so a single service can be run alone in development, exactly as
akasha, chronos and prithvi each can.
"""

from visualizer.akasha.config import (
    get_mongo_client,
    get_rate_limit_storage_uri,
    get_secret_key,
    get_secure_cookies,
    get_service_links,
    get_versions_keep,
)
from visualizer.akasha.store import DocumentStore
from visualizer.auth import AuthStore
from visualizer.chronos.store import StoryStore
from visualizer.gpubox import worker_from_env
from visualizer.observability import runtime as observability_runtime

from .app import create_app
from .config import get_section_revisions_keep
from .gateways import InProcessArticleGateway, InProcessChronosGateway
from .llm_review import RemoteReviewer
from .llm_review_jobs import LlmReviewStore
from .store import LogosStore

_client = get_mongo_client()
_auth_store = AuthStore(_client)
_observability = observability_runtime.start(_client, _auth_store)
_worker = worker_from_env()

app = create_app(
    LogosStore(_client, section_revisions_keep=get_section_revisions_keep()),
    InProcessChronosGateway(StoryStore(_client)),
    InProcessArticleGateway(DocumentStore(_client, versions_keep=get_versions_keep())),
    _auth_store,
    secret_key=get_secret_key(),
    secure_cookies=get_secure_cookies(),
    rate_limit_storage_uri=get_rate_limit_storage_uri(),
    links=get_service_links(),
    observability=_observability,
    reviewer=RemoteReviewer(_worker) if _worker is not None else None,
    llm_reviews=LlmReviewStore(_client) if _worker is not None else None,
)
