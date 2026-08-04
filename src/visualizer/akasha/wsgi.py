"""Production entrypoint.

Wires a real MongoDB client into both stores and exposes ``app`` for WSGI
servers (e.g. ``gunicorn wsgi:app`` from this directory).

There is no admin bootstrap: the first account registered via ``/register``
becomes the administrator, and every account after it is a plain user.
"""

from visualizer.auth import AuthStore

from .app import create_app
from .config import (
    get_akasha_url,
    get_chronos_url,
    get_mongo_client,
    get_rate_limit_storage_uri,
    get_secret_key,
    get_secure_cookies,
    get_versions_keep,
)
from .store import DocumentStore

_client = get_mongo_client()
_auth_store = AuthStore(_client)

app = create_app(
    DocumentStore(_client, versions_keep=get_versions_keep()),
    _auth_store,
    secret_key=get_secret_key(),
    secure_cookies=get_secure_cookies(),
    rate_limit_storage_uri=get_rate_limit_storage_uri(),
    akasha_url=get_akasha_url(),
    chronos_url=get_chronos_url(),
)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
