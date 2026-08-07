"""HTTP-level tests for the Flask app against an in-memory MongoDB."""

from conftest import collection_url, doc_url, search_url


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_create_collection_returns_201(client):
    resp = client.post(collection_url(database="newdb", collection="newcol"))
    assert resp.status_code == 201
    assert resp.get_json() == {"database": "newdb", "collection": "newcol"}


def test_create_collection_duplicate_returns_409(client):
    client.post(collection_url(database="newdb", collection="newcol"))
    resp = client.post(collection_url(database="newdb", collection="newcol"))
    assert resp.status_code == 409


def test_create_document_in_missing_collection_returns_404(client):
    resp = client.post(doc_url("x", collection="ghost"), json={"a": 1})
    assert resp.status_code == 404


def test_create_document_in_missing_database_returns_404(client):
    resp = client.post(
        doc_url("x", database="ghostdb", collection="ghost"), json={"a": 1}
    )
    assert resp.status_code == 404


def test_create_collection_then_document(client):
    client.post(collection_url(database="newdb", collection="newcol"))
    resp = client.post(
        doc_url("d1", database="newdb", collection="newcol"), json={"a": 1}
    )
    assert resp.status_code == 201


def test_create_returns_201(client):
    resp = client.post(doc_url("a1"), json={"name": "Aragorn"})
    assert resp.status_code == 201
    assert resp.get_json() == {"id": "a1", "document": {"name": "Aragorn"}, "rev": 1}


def test_create_rejects_non_dict_body(client):
    resp = client.post(doc_url("a1"), json=[1, 2, 3])
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_create_rejects_invalid_json(client):
    resp = client.post(
        doc_url("a1"), data="not json", content_type="application/json"
    )
    assert resp.status_code == 400


def test_create_duplicate_returns_409(client):
    client.post(doc_url("a1"), json={"name": "Aragorn"})
    resp = client.post(doc_url("a1"), json={"name": "Strider"})
    assert resp.status_code == 409


def test_get_returns_document(client):
    client.post(doc_url("a1"), json={"name": "Aragorn"})
    resp = client.get(doc_url("a1"))
    assert resp.status_code == 200
    assert resp.get_json() == {"id": "a1", "document": {"name": "Aragorn"}, "rev": 1}


def test_get_missing_returns_404(client):
    assert client.get(doc_url("ghost")).status_code == 404


def test_update_replaces_and_returns_200(client):
    client.post(doc_url("a1"), json={"name": "Aragorn", "age": 87})
    resp = client.put(doc_url("a1"), json={"name": "Elessar"})
    assert resp.status_code == 200
    assert client.get(doc_url("a1")).get_json()["document"] == {"name": "Elessar"}


def test_update_missing_returns_404(client):
    assert client.put(doc_url("ghost"), json={"x": 1}).status_code == 404


def test_delete_returns_204_then_404(client):
    client.post(doc_url("a1"), json={"name": "Aragorn"})
    assert client.delete(doc_url("a1")).status_code == 204
    assert client.get(doc_url("a1")).status_code == 404


def test_delete_missing_returns_404(client):
    assert client.delete(doc_url("ghost")).status_code == 404


def _seed(client):
    client.post(doc_url("aragorn"), json={"name": "Aragorn", "weapon": "sword"})
    client.post(doc_url("legolas"), json={"name": "Legolas", "weapon": "bow"})
    client.post(doc_url("gimli"), json={"name": "Gimli", "axe": "battle axe"})


def test_search_requires_a_term(client):
    resp = client.get(search_url())
    assert resp.status_code == 400


def test_search_by_key(client):
    _seed(client)
    body = client.get(search_url(), query_string={"key": "weapon"}).get_json()
    assert body["count"] == 2
    assert {r["id"] for r in body["results"]} == {"aragorn", "legolas"}


def test_search_by_text(client):
    _seed(client)
    body = client.get(search_url(), query_string={"text": "battle"}).get_json()
    assert {r["id"] for r in body["results"]} == {"gimli"}


def test_search_by_key_and_text(client):
    _seed(client)
    body = client.get(
        search_url(), query_string={"key": "weapon", "text": "bow"}
    ).get_json()
    assert {r["id"] for r in body["results"]} == {"legolas"}


def test_collections_are_independent(client):
    client.post(collection_url(collection="c1"))
    client.post(doc_url("a1", collection="c1"), json={"name": "one"})
    assert client.get(doc_url("a1", collection="c2")).status_code == 404
