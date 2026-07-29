"""Production entrypoint.

Wires a real MongoDB client into the store and exposes ``app`` for WSGI servers
(e.g. ``gunicorn wsgi:app`` from this directory).
"""

from app import create_app
from config import get_mongo_client
from store import DocumentStore

app = create_app(DocumentStore(get_mongo_client()))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
