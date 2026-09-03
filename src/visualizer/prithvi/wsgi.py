"""Standalone entrypoint: Prithvi alone, on its own port, for development.

The combined deployment goes through ``visualizer.wsgi`` instead, where all
four services share one client, one auth store and one origin. This exists for
the same reason the other two per-service entrypoints do: so one service can be
run and watched without the others in the way.
"""

from visualizer.akasha.config import (
    get_akasha_url,
    get_chronos_url,
    get_logos_url,
    get_mongo_client,
    get_prithvi_url,
    get_rate_limit_storage_uri,
    get_secret_key,
    get_secure_cookies,
)
from visualizer.akasha.store import DocumentStore
from visualizer.auth import AuthStore
from visualizer.observability import runtime as observability_runtime

from .app import create_app
from .articles import InProcessArticleGateway
from .config import (
    get_map_revisions_keep,
    get_max_svg_bytes,
    get_pin_revisions_keep,
)
from .store import PrithviStore

_client = get_mongo_client()
_auth_store = AuthStore(_client)
_observability = observability_runtime.start(_client, _auth_store)

app = create_app(
    PrithviStore(
        _client,
        map_revisions_keep=get_map_revisions_keep(),
        pin_revisions_keep=get_pin_revisions_keep(),
    ),
    InProcessArticleGateway(DocumentStore(_client)),
    _auth_store,
    secret_key=get_secret_key(),
    max_svg_bytes=get_max_svg_bytes(),
    secure_cookies=get_secure_cookies(),
    rate_limit_storage_uri=get_rate_limit_storage_uri(),
    akasha_url=get_akasha_url(),
    chronos_url=get_chronos_url(),
    prithvi_url=get_prithvi_url(),
    logos_url=get_logos_url(),
    observability=_observability,
)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5004)
