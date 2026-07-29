"""Production entrypoint.

Wires a real MongoDB client into both stores and exposes ``app`` for WSGI
servers (e.g. ``gunicorn wsgi:app`` from this directory).

There is no admin bootstrap: the first account registered via ``/register``
becomes the administrator, and every account after it is a plain user.
"""

from .app import create_app
from .auth_store import AuthStore
from .config import get_mongo_client, get_secret_key
from .store import DocumentStore

_client = get_mongo_client()
_auth_store = AuthStore(_client)

app = create_app(DocumentStore(_client), _auth_store, secret_key=get_secret_key())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
