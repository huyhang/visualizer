"""Production entrypoint for Chronos.

Wires the real seams together, all sharing one MongoClient with akasha
(constraint #1: Chronos always ships alongside it). Kept tiny -- all the
env/IO lives in ``akasha.config``, injected here.
"""

from visualizer.akasha.config import (
    get_mongo_client,
    get_rate_limit_storage_uri,
    get_secret_key,
    get_secure_cookies,
)
from visualizer.akasha.store import DocumentStore
from visualizer.auth import AuthStore

from .app import create_app
from .entity_gate import InProcessEntityGate
from .store import StoryStore

_client = get_mongo_client()
app = create_app(
    story_store=StoryStore(_client),
    entity_gate=InProcessEntityGate(DocumentStore(_client)),
    auth_store=AuthStore(_client),
    secret_key=get_secret_key(),
    secure_cookies=get_secure_cookies(),
    rate_limit_storage_uri=get_rate_limit_storage_uri(),
)
