"""Dioramas over HTTP: upload, serve, re-aim, and the rules they inherit.

The point of putting dioramas in the media library rather than beside it is
that they get the library's answers for free -- who may add one, who may see
one, and what stops one being deleted out from under an article. Those are
tested here against the diorama path specifically, because "it should inherit
that" is a claim, not a guarantee.
"""

import json
import struct
from io import BytesIO

import pytest
from conftest import COLLECTION, DB, doc_url, login
from PIL import Image
from werkzeug.security import generate_password_hash

MEDIA = f"/databases/{DB}/media"
DIORAMAS = f"{MEDIA}/dioramas"


def _glb(vertices=240, images=0, binary=b""):
    document = {
        "asset": {"version": "2.0"},
        "accessors": [{"count": vertices, "type": "VEC3", "componentType": 5126}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "nodes": [{"mesh": 0}],
        "materials": [{"name": "stone"}],
    }
    if images:
        document["bufferViews"] = [{"byteOffset": 0, "byteLength": len(binary)}]
        document["images"] = [{"bufferView": 0}] * images
    raw = json.dumps(document).encode()
    raw += b" " * (-len(raw) % 4)
    body = struct.pack("<II", len(raw), 0x4E4F534A) + raw
    if binary:
        padded = binary + b"\x00" * (-len(binary) % 4)
        body += struct.pack("<II", len(padded), 0x004E4942) + padded
    return struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body


def _poster(size=(240, 160)):
    out = BytesIO()
    Image.effect_noise(size, 32).convert("RGB").save(out, "PNG")
    return out.getvalue()


def _manifest(**overrides):
    return json.dumps({"title": "The Tea Garden", **overrides})


def _upload(client, model=None, poster=None, manifest=None, alt="A walled garden"):
    data = {
        "collection": COLLECTION,
        "article": "atlas",
        "alt": alt,
        "manifest": manifest if manifest is not None else _manifest(),
        "model": (BytesIO(model or _glb()), "garden.glb"),
    }
    if poster is not None:
        data["poster"] = (BytesIO(poster), "poster.png")
    return client.post(DIORAMAS, data=data)


@pytest.fixture
def article(client):
    client.post(doc_url("atlas"), json={"title": "Atlas"})
    return client


# -- the happy path ----------------------------------------------------------


def test_a_model_is_stored_with_its_measurements_and_its_manifest(article):
    created = _upload(article)
    assert created.status_code == 201
    body = created.get_json()

    assert body["kind"] == "diorama"
    assert body["filename"] == "garden.glb"
    assert body["model"]["vertices"] == 240
    assert body["model"]["textures"] == 0
    assert body["manifest"]["title"] == "The Tea Garden"
    assert body["manifest"]["camera_elevation"] == 25   # a default, filled in
    assert body["model_url"].endswith("/model")
    assert "thumbnail_url" not in body, "a diorama has no image variants"


def test_the_model_is_served_back_byte_for_byte(article):
    model = _glb(vertices=99)
    media_id = _upload(article, model=model).get_json()["id"]

    served = article.get(f"{MEDIA}/{media_id}/model")
    assert served.status_code == 200
    assert served.data == model
    assert served.headers["Content-Type"].startswith("model/gltf-binary")
    assert served.headers["X-Content-Type-Options"] == "nosniff"


def test_a_poster_is_stored_as_an_ordinary_bounded_image(article):
    body = _upload(article, poster=_poster()).get_json()
    assert set(body["variants"]) == {"model", "poster"}
    assert body["variants"]["poster"]["mime_type"] == "image/png"
    # bounded by the image pipeline's display cap, not stored at full size
    assert body["variants"]["poster"]["width"] <= 512
    assert article.get(f"{MEDIA}/{body['id']}/poster").status_code == 200


def test_a_diorama_without_a_poster_is_allowed(article):
    body = _upload(article).get_json()
    assert set(body["variants"]) == {"model"}
    assert "poster_url" not in body


# -- re-aiming without re-uploading ------------------------------------------


def test_the_manifest_can_be_replaced_without_touching_the_geometry(article):
    body = _upload(article).get_json()
    media_id, before = body["id"], body["model"]

    updated = article.put(
        f"{MEDIA}/{media_id}/manifest",
        json={"title": "The Tea Garden", "camera_azimuth": 200,
              "camera_elevation": -10, "rotation_speed": 0, "auto_rotate": False},
    )
    assert updated.status_code == 200
    after = updated.get_json()
    assert after["manifest"]["camera_azimuth"] == 200
    assert after["manifest"]["auto_rotate"] is False
    assert after["model"] == before, "the measurements describe a file that did not change"
    assert article.get(f"{MEDIA}/{media_id}/model").status_code == 200


def test_a_manifest_the_viewer_could_not_honour_is_refused(article):
    media_id = _upload(article).get_json()["id"]
    refused = article.put(
        f"{MEDIA}/{media_id}/manifest",
        json={"title": "t", "camera_elevation": 90},
    )
    assert refused.status_code == 400
    assert "camera_elevation" in refused.get_json()["error"]


def test_an_image_cannot_be_re_aimed(client):
    """The manifest route belongs to dioramas; images have no camera."""
    client.post(doc_url("atlas"), json={"title": "Atlas"})
    image = client.post(MEDIA, data={
        "collection": COLLECTION, "article": "atlas", "alt": "A map",
        "file": (BytesIO(_poster()), "map.png"),
    }).get_json()
    refused = client.put(f"{MEDIA}/{image['id']}/manifest", json={"title": "t"})
    assert refused.status_code == 400
    assert "not a diorama" in refused.get_json()["error"]


# -- what the gate refuses, through the route --------------------------------


def test_a_model_that_reaches_outside_itself_is_refused_at_the_door(article):
    document = {
        "asset": {"version": "2.0"},
        "buffers": [{"uri": "https://example.invalid/tracker.bin"}],
    }
    raw = json.dumps(document).encode()
    raw += b" " * (-len(raw) % 4)
    body = struct.pack("<II", len(raw), 0x4E4F534A) + raw
    hostile = struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body

    refused = _upload(article, model=hostile)
    assert refused.status_code == 400
    assert "outside the file" in refused.get_json()["error"]


def test_a_model_over_the_byte_cap_is_refused(article):
    padded = _glb() + b"\x00" * (1024 * 1024)
    refused = _upload(article, model=padded)
    assert refused.status_code in (400, 413)


def test_something_that_is_not_a_model_is_refused(article):
    refused = _upload(article, model=_poster())
    assert refused.status_code == 400


def test_a_diorama_still_needs_alt_text(article):
    refused = _upload(article, alt="   ")
    assert refused.status_code == 400


def test_a_manifest_that_is_not_json_is_refused(article):
    refused = _upload(article, manifest="{not json")
    assert refused.status_code == 400
    assert "not valid JSON" in refused.get_json()["error"]


def test_a_diorama_needs_a_title(article):
    refused = _upload(article, manifest=json.dumps({}))
    assert refused.status_code == 400
    assert "needs a title" in refused.get_json()["error"]


# -- the rules it inherits from the library ----------------------------------


def test_uploading_a_diorama_needs_write_access_to_the_article(app, auth_store, article):
    auth_store.create_user("reader", generate_password_hash("pw"), role="user")
    auth_store.add_grant("reader", DB, COLLECTION, "atlas", ["read"], granted_by="admin")
    outsider = app.test_client()
    login(outsider, "reader", "pw")
    assert _upload(outsider).status_code == 403


def test_a_diorama_shown_by_an_article_cannot_be_deleted(article):
    media_id = _upload(article).get_json()["id"]
    article.put(
        doc_url("atlas"),
        json={
            "title": "Atlas",
            "body": f"{{{{image:{media_id}|center|60|The garden}}}}",
            "gallery": [f"{media_id}|The garden"],
        },
    )
    blocked = article.delete(f"{MEDIA}/{media_id}")
    assert blocked.status_code == 409
    assert blocked.get_json()["references"]


def test_an_unused_diorama_is_reported_as_an_orphan(article):
    media_id = _upload(article).get_json()["id"]
    listed = article.get(f"{MEDIA}?orphans=1").get_json()
    assert listed["orphans"] == [media_id]


def test_a_diorama_is_charged_to_whoever_uploaded_it(article, mongo_client):
    """The storage view must see the model's bytes, not just its record."""
    from visualizer.observability.usage import MongoDocumentSource

    _upload(article, poster=_poster())
    rows = [
        row for row in MongoDocumentSource(mongo_client).documents()
        if row.resource[0] == "media"
    ]
    assert len(rows) == 1
    assert rows[0].created_by == "admin"
    assert rows[0].total_bytes > len(_glb()), "the GridFS chunks are counted"


def test_re_aiming_also_replaces_the_poster(article):
    """Otherwise the gallery keeps showing the camera that was replaced --
    exactly the staleness keeping presentation separate is meant to avoid."""
    body = _upload(article, poster=_poster()).get_json()
    media_id = body["id"]
    before = body["variants"]["poster"]["sha256"]

    updated = article.put(
        f"{MEDIA}/{media_id}/manifest",
        data={
            "manifest": _manifest(camera_azimuth=200),
            "poster": (BytesIO(_poster((300, 200))), "poster.png"),
        },
    )
    assert updated.status_code == 200
    after = updated.get_json()
    assert after["manifest"]["camera_azimuth"] == 200
    assert after["variants"]["poster"]["sha256"] != before
    assert article.get(f"{MEDIA}/{media_id}/poster").status_code == 200


def test_the_replaced_poster_bytes_are_not_left_behind(article, mongo_client):
    """A swapped blob whose file nobody deletes is storage charged forever."""
    media_id = _upload(article, poster=_poster()).get_json()["id"]
    files = mongo_client["_akasha_media"]["blobs.files"]
    before = files.count_documents({})

    article.put(
        f"{MEDIA}/{media_id}/manifest",
        data={
            "manifest": _manifest(camera_elevation=40),
            "poster": (BytesIO(_poster((320, 220))), "poster.png"),
        },
    )
    assert files.count_documents({}) == before, "the old poster was orphaned"


def test_a_manifest_can_still_be_replaced_as_plain_json(article):
    """Scripts have no camera to photograph, so a poster is not required."""
    media_id = _upload(article).get_json()["id"]
    updated = article.put(
        f"{MEDIA}/{media_id}/manifest",
        json={"title": "The Tea Garden", "rotation_speed": 0},
    )
    assert updated.status_code == 200
    assert updated.get_json()["manifest"]["rotation_speed"] == 0


def test_adding_a_poster_to_a_diorama_that_had_none(article):
    created = _upload(article).get_json()
    media_id = created["id"]
    assert "poster" not in created["variants"]
    updated = article.put(
        f"{MEDIA}/{media_id}/manifest",
        data={
            "manifest": _manifest(),
            "poster": (BytesIO(_poster()), "poster.png"),
        },
    )
    assert updated.status_code == 200
    assert "poster" in updated.get_json()["variants"]


def test_re_aiming_needs_the_right_to_manage_it(app, auth_store, article):
    media_id = _upload(article).get_json()["id"]
    auth_store.create_user("bystander", generate_password_hash("pw"), role="user")
    auth_store.add_grant(
        "bystander", DB, COLLECTION, "atlas", ["read", "write"], granted_by="admin"
    )
    other = app.test_client()
    login(other, "bystander", "pw")
    refused = other.put(f"{MEDIA}/{media_id}/manifest", json={"title": "Mine now"})
    assert refused.status_code == 403


def test_a_blocked_delete_says_which_kind_it_is_refusing(article):
    """The library holds two kinds, so 'this image is still used' is wrong
    half the time."""
    media_id = _upload(article).get_json()["id"]
    article.put(
        doc_url("atlas"),
        json={
            "title": "Atlas",
            "body": f"{{{{image:{media_id}|center|60|The garden}}}}",
            "gallery": [f"{media_id}|The garden"],
        },
    )
    blocked = article.delete(f"{MEDIA}/{media_id}")
    assert blocked.status_code == 409
    assert "diorama is still used" in blocked.get_json()["error"]


def test_a_diorama_can_be_deleted_once_nothing_shows_it(article, mongo_client):
    media_id = _upload(article, poster=_poster()).get_json()["id"]
    files = mongo_client["_akasha_media"]["blobs.files"]
    assert files.count_documents({}) == 2       # the model and its poster

    removed = article.delete(f"{MEDIA}/{media_id}")
    assert removed.status_code == 200
    assert article.get(f"{MEDIA}/{media_id}").status_code == 404
    assert files.count_documents({}) == 0, "the model's bytes went with it"
