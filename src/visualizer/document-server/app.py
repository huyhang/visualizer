"""Flask application factory.

``create_app`` receives its ``DocumentStore`` by injection so the same routing
code runs against an in-memory Mongo in tests and a real Mongo in production.

Routes are namespaced by database and collection so every call must name both,
plus a document id for the single-document operations::

    POST   /databases/<db>/collections/<col>                  create collection
    POST   /databases/<db>/collections/<col>/documents/<id>   create document
    GET    /databases/<db>/collections/<col>/documents/<id>   get
    PUT    /databases/<db>/collections/<col>/documents/<id>   update (replace)
    DELETE /databases/<db>/collections/<col>/documents/<id>   delete
    GET    /databases/<db>/collections/<col>/search?key=&text=  search
"""

from flask import Flask, jsonify, request

from errors import DocumentServerError
from store import DocumentStore
from validation import validate_document, validate_search_terms

_COLLECTION_ROUTE = "/databases/<database>/collections/<collection>"
_DOC_ROUTE = "/databases/<database>/collections/<collection>/documents/<doc_id>"
_SEARCH_ROUTE = "/databases/<database>/collections/<collection>/search"


def create_app(store: DocumentStore) -> Flask:
    app = Flask(__name__)
    _register_routes(app, store)
    _register_error_handlers(app)
    return app


def _register_routes(app: Flask, store: DocumentStore) -> None:
    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.post(_COLLECTION_ROUTE)
    def create_collection(database, collection):
        return jsonify(store.create_collection(database, collection)), 201

    @app.post(_DOC_ROUTE)
    def create(database, collection, doc_id):
        document = validate_document(request.get_json(silent=True))
        return jsonify(store.create(database, collection, doc_id, document)), 201

    @app.get(_DOC_ROUTE)
    def get(database, collection, doc_id):
        return jsonify(store.get(database, collection, doc_id))

    @app.put(_DOC_ROUTE)
    def update(database, collection, doc_id):
        document = validate_document(request.get_json(silent=True))
        return jsonify(store.update(database, collection, doc_id, document))

    @app.delete(_DOC_ROUTE)
    def delete(database, collection, doc_id):
        store.delete(database, collection, doc_id)
        return "", 204

    @app.get(_SEARCH_ROUTE)
    def search(database, collection):
        key, text = validate_search_terms(
            request.args.get("key"), request.args.get("text")
        )
        results = store.search(database, collection, key=key, text=text)
        return jsonify({"results": results, "count": len(results)})


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(DocumentServerError)
    def handle_domain_error(err: DocumentServerError):
        return jsonify({"error": err.message}), err.status_code
