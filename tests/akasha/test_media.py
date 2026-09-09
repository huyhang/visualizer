"""Image processing, world-library persistence, references, and HTTP policy."""

from datetime import UTC, datetime
from io import BytesIO

import mongomock
import mongomock.gridfs
import pytest
from conftest import COLLECTION, DB, doc_url, login
from PIL import Image
from werkzeug.security import generate_password_hash

from visualizer.akasha.config import (
    DEFAULT_IMAGE_DISPLAY_MAX_PX,
    DEFAULT_IMAGE_THUMBNAIL_MAX_PX,
    DEFAULT_MAX_IMAGE_BYTES,
    DEFAULT_MAX_IMAGE_PIXELS,
    get_image_display_max_px,
    get_image_thumbnail_max_px,
    get_max_image_bytes,
    get_max_image_pixels,
)
from visualizer.akasha.errors import ImageTooLarge, InvalidImage, MediaInUse
from visualizer.akasha.image_processing import ImageProcessor
from visualizer.akasha.media import (
    document_image_ids,
    image_ids,
    parse_gallery_item,
    parse_image_directive,
    validate_alt_text,
)
from visualizer.akasha.media_service import ArticleMediaReferences, MediaService
from visualizer.akasha.media_store import MediaStore
from visualizer.akasha.store import DocumentStore

mongomock.gridfs.enable_gridfs_integration()

IMAGE_ID = "a" * 32
DIRECTIVE = f"{{{{image:{IMAGE_ID}|right|40|The old tower}}}}"


def _image(format_name="PNG", size=(80, 60), color=(20, 40, 60, 255)):
    mode = "RGB" if format_name == "JPEG" else "RGBA"
    image = Image.new(mode, size, color[: len(mode)])
    out = BytesIO()
    image.save(out, format_name)
    return out.getvalue()


def _upload(client, body=None, alt="A blue map", filename="map.png"):
    return client.post(
        f"/databases/{DB}/media",
        data={
            "collection": COLLECTION,
            "article": "atlas",
            "alt": alt,
            "file": (BytesIO(body or _image()), filename),
        },
    )


def test_image_directive_is_strict_and_extractable():
    placement = parse_image_directive(DIRECTIVE)
    assert placement.media_id == IMAGE_ID
    assert placement.align == "right"
    assert placement.width == 40
    assert placement.caption == "The old tower"
    assert image_ids(f"Before\n{DIRECTIVE}\n{DIRECTIVE}\nAfter") == {IMAGE_ID}
    assert parse_image_directive(f"{{{{image:{IMAGE_ID}|full|40|bad}}}}") is None
    assert parse_image_directive("{{image:not-an-id|center|50|bad}}") is None


def test_gallery_items_and_all_article_references_are_extractable():
    other_id = "b" * 32
    item = parse_gallery_item(f"{IMAGE_ID}|A caption|with a separator")
    assert item.media_id == IMAGE_ID
    assert item.caption == "A caption|with a separator"
    assert parse_gallery_item("bad|caption") is None
    assert document_image_ids(
        {
            "body": DIRECTIVE,
            "gallery": [f"{other_id}|Gallery caption"],
            "profile_image": other_id,
        }
    ) == {IMAGE_ID, other_id}


def test_alt_text_is_required_normalised_and_bounded():
    assert validate_alt_text("  A   blue map  ") == "A blue map"
    with pytest.raises(InvalidImage):
        validate_alt_text(" ")
    with pytest.raises(InvalidImage):
        validate_alt_text("x" * 301)


def test_processor_keeps_original_and_builds_bounded_variants():
    raw = _image("PNG", (800, 400))
    processed = ImageProcessor(100_000, 1_000_000, 500, 100).process(
        raw, "folder/map.png"
    )
    assert processed.filename == "map.png"
    assert processed.original.data == raw
    assert (processed.width, processed.height) == (800, 400)
    assert (processed.display.width, processed.display.height) == (500, 250)
    assert (processed.thumbnail.width, processed.thumbnail.height) == (100, 50)
    assert processed.display.mime_type == "image/png"


@pytest.mark.parametrize(
    "format_name,mime_type", [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")]
)
def test_processor_accepts_the_supported_static_formats(format_name, mime_type):
    processed = ImageProcessor(100_000, 100_000, 50).process(
        _image(format_name), f"image.{format_name.lower()}"
    )
    assert processed.original.mime_type == mime_type
    assert processed.display.mime_type == mime_type


def test_processor_rejects_invalid_bytes_and_both_size_limits():
    with pytest.raises(InvalidImage):
        ImageProcessor(100, 100, 10).process(b"not an image", "x.png")
    with pytest.raises(ImageTooLarge):
        ImageProcessor(4, 100, 10).process(_image(size=(2, 2)), "x.png")
    with pytest.raises(ImageTooLarge):
        ImageProcessor(100_000, 3, 10).process(_image(size=(2, 2)), "x.png")


def test_gridfs_store_round_trip_and_delete():
    client = mongomock.MongoClient()
    processor = ImageProcessor(100_000, 100_000, 50, 20)
    image = processor.process(_image(), "map.png")
    store = MediaStore(
        client,
        clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
        id_factory=lambda: IMAGE_ID,
    )
    created = store.create(DB, "alice", "A map", image)
    assert created["id"] == IMAGE_ID
    assert created["created_at"] == "2026-01-01T00:00:00+00:00"
    assert "file_id" not in created["variants"]["original"]
    data, details = store.read_variant(DB, IMAGE_ID, "original")
    assert data == image.original.data
    assert details["sha256"] == image.original.sha256
    store.delete(DB, IMAGE_ID)
    assert store.list(DB) == []


def test_references_include_current_and_retained_article_versions(mongo_client):
    store = DocumentStore(mongo_client)
    store.create_collection(DB, COLLECTION)
    store.create(DB, COLLECTION, "atlas", {"body": DIRECTIVE})
    store.update(DB, COLLECTION, "atlas", {"body": "Now text"}, expected_rev=1)
    refs = ArticleMediaReferences(mongo_client).references(DB, IMAGE_ID)
    assert refs == [
        {
            "collection": COLLECTION,
            "article": "atlas",
            "revision": 1,
            "current": False,
        }
    ]


def test_references_include_gallery_and_profile_images(mongo_client):
    store = DocumentStore(mongo_client)
    store.create_collection(DB, COLLECTION)
    store.create(
        DB,
        COLLECTION,
        "atlas",
        {"gallery": [f"{IMAGE_ID}|Map"], "profile_image": IMAGE_ID},
    )
    refs = ArticleMediaReferences(mongo_client).references(DB, IMAGE_ID)
    assert refs[0]["article"] == "atlas"
    assert refs[0]["current"] is True


def test_upload_list_and_serve_variants(client):
    client.post(doc_url("atlas"), json={"title": "Atlas"})
    uploaded = _upload(client)
    assert uploaded.status_code == 201
    media = uploaded.get_json()
    assert media["alt"] == "A blue map"
    assert media["format"] == "PNG"
    assert media["can_manage"] is True
    assert media["original_url"].endswith("/original")

    listed = client.get(f"/databases/{DB}/media").get_json()
    assert listed["count"] == 1
    response = client.get(media["display_url"])
    assert response.status_code == 200
    assert response.content_type == "image/png"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.cache_control.private


def test_upload_requires_a_real_supported_image_and_alt_text(client):
    assert _upload(client, body=b"broken").status_code == 400
    assert _upload(client, alt=" ").status_code == 400
    response = client.post(
        f"/databases/{DB}/media",
        data={"collection": COLLECTION, "article": "atlas", "alt": "Missing"},
    )
    assert response.status_code == 400


def test_upload_requires_write_access(app, auth_store):
    auth_store.create_user("reader", generate_password_hash("reader-pass"))
    auth_store.add_grant(
        "reader", DB, COLLECTION, "atlas", ["read"], granted_by="admin"
    )
    reader = app.test_client()
    login(reader, "reader", "reader-pass")
    assert _upload(reader).status_code == 403


def test_normal_delete_is_blocked_by_current_or_historical_reference(client):
    uploaded = _upload(client).get_json()
    directive = f"{{{{image:{uploaded['id']}|center|60|A caption}}}}"
    client.post(
        doc_url("atlas"),
        json={"body": directive, "gallery": [f"{uploaded['id']}|A caption"]},
    )
    blocked = client.delete(f"/databases/{DB}/media/{uploaded['id']}")
    assert blocked.status_code == 409
    assert blocked.get_json()["references"][0]["current"] is True

    client.put(doc_url("atlas"), json={"body": "Removed"}, headers={"If-Match": "1"})
    history_blocked = client.delete(f"/databases/{DB}/media/{uploaded['id']}")
    assert history_blocked.status_code == 409
    assert history_blocked.get_json()["references"][0]["revision"] == 1

    forced = client.delete(f"/databases/{DB}/media/{uploaded['id']}?force=1")
    assert forced.status_code == 200
    assert forced.get_json()["broken_references"]
    assert client.get(uploaded["original_url"]).status_code == 404


def test_gallery_attachment_without_inline_placement_blocks_delete(client):
    uploaded = _upload(client).get_json()
    client.post(
        doc_url("atlas"),
        json={
            "gallery": [f"{uploaded['id']}|View from the gate"],
            "profile_image": uploaded["id"],
        },
    )

    blocked = client.delete(f"/databases/{DB}/media/{uploaded['id']}")
    assert blocked.status_code == 409
    assert blocked.get_json()["references"][0]["current"] is True


def test_narrow_reader_sees_only_images_used_by_readable_articles(
    app, client, auth_store
):
    first = _upload(client, alt="Visible").get_json()
    second = _upload(client, alt="Hidden").get_json()
    client.post(
        doc_url("atlas"),
        json={
            "body": f"{{{{image:{first['id']}|center|60|Seen}}}}",
            "gallery": [f"{first['id']}|Seen"],
        },
    )
    auth_store.create_user("reader", generate_password_hash("reader-pass"))
    auth_store.add_grant(
        "reader", DB, COLLECTION, "atlas", ["read"], granted_by="admin"
    )
    reader = app.test_client()
    assert login(reader, "reader", "reader-pass").status_code == 200

    listed = reader.get(f"/databases/{DB}/media").get_json()["media"]
    assert [item["id"] for item in listed] == [first["id"]]
    assert listed[0]["can_manage"] is False
    assert reader.get(first["thumbnail_url"]).status_code == 200
    assert reader.get(second["thumbnail_url"]).status_code == 403


def test_only_uploader_or_world_owner_may_manage_media(app, client, auth_store):
    media = _upload(client).get_json()
    auth_store.create_user("editor", generate_password_hash("editor-pass"))
    auth_store.add_grant(
        "editor", DB, COLLECTION, "atlas", ["read", "write"], granted_by="admin"
    )
    editor = app.test_client()
    login(editor, "editor", "editor-pass")
    assert editor.patch(
        f"/databases/{DB}/media/{media['id']}", json={"alt": "Changed"}
    ).status_code == 403


def test_blocked_delete_does_not_reveal_unreadable_article_names(
    app, client, auth_store
):
    auth_store.create_user("artist", generate_password_hash("artist-pass"))
    auth_store.add_grant(
        "artist", DB, COLLECTION, "atlas", ["read", "write"], granted_by="admin"
    )
    artist = app.test_client()
    login(artist, "artist", "artist-pass")
    media = _upload(artist).get_json()
    client.post(
        doc_url("secret"),
        json={
            "body": f"{{{{image:{media['id']}|center|50|Hidden}}}}",
            "gallery": [f"{media['id']}|Hidden"],
        },
    )

    blocked = artist.delete(f"/databases/{DB}/media/{media['id']}")
    assert blocked.status_code == 409
    assert blocked.get_json()["references"] == []


def test_uploader_can_change_alt_text_and_delete_an_unused_image(client):
    media = _upload(client).get_json()
    url = f"/databases/{DB}/media/{media['id']}"
    changed = client.patch(url, json={"alt": "An updated description"})
    assert changed.status_code == 200
    assert changed.get_json()["alt"] == "An updated description"
    assert client.delete(url).status_code == 200
    assert client.get(url).status_code == 404


def test_media_configuration_defaults_and_validation(monkeypatch):
    for name in (
        "AKASHA_MAX_IMAGE_BYTES",
        "AKASHA_MAX_IMAGE_PIXELS",
        "AKASHA_IMAGE_DISPLAY_MAX_PX",
        "AKASHA_IMAGE_THUMBNAIL_MAX_PX",
    ):
        monkeypatch.delenv(name, raising=False)
    assert get_max_image_bytes() == DEFAULT_MAX_IMAGE_BYTES
    assert get_max_image_pixels() == DEFAULT_MAX_IMAGE_PIXELS
    assert get_image_display_max_px() == DEFAULT_IMAGE_DISPLAY_MAX_PX
    assert get_image_thumbnail_max_px() == DEFAULT_IMAGE_THUMBNAIL_MAX_PX

    monkeypatch.setenv("AKASHA_MAX_IMAGE_BYTES", "0")
    with pytest.raises(RuntimeError):
        get_max_image_bytes()


def test_service_refuses_delete_without_force(mongo_client):
    store = DocumentStore(mongo_client)
    store.create_collection(DB, COLLECTION)
    processor = ImageProcessor(100_000, 100_000, 50)
    media_store = MediaStore(mongo_client, id_factory=lambda: IMAGE_ID)
    service = MediaService(
        media_store, processor, ArticleMediaReferences(mongo_client)
    )
    service.upload(DB, "alice", "x.png", _image(), "A map")
    store.create(
        DB, COLLECTION, "atlas", {"body": DIRECTIVE, "gallery": [f"{IMAGE_ID}|Map"]}
    )
    with pytest.raises(MediaInUse):
        service.delete(DB, IMAGE_ID)


def test_image_becomes_deletable_after_referencing_history_is_pruned(mongo_client):
    documents = DocumentStore(mongo_client, versions_keep=2)
    documents.create_collection(DB, COLLECTION)
    media_store = MediaStore(mongo_client, id_factory=lambda: IMAGE_ID)
    service = MediaService(
        media_store,
        ImageProcessor(100_000, 100_000, 50),
        ArticleMediaReferences(mongo_client),
    )
    service.upload(DB, "alice", "x.png", _image(), "A map")
    documents.create(
        DB, COLLECTION, "atlas", {"body": DIRECTIVE, "gallery": [f"{IMAGE_ID}|Map"]}
    )
    documents.update(DB, COLLECTION, "atlas", {"body": "Removed"})
    documents.update(DB, COLLECTION, "atlas", {"body": "Still removed"})

    assert service.delete(DB, IMAGE_ID) == []
    assert media_store.list(DB) == []
