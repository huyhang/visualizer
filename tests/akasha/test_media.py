"""Image processing, world-library persistence, references, and HTTP policy."""

from datetime import UTC, datetime
from io import BytesIO

import mongomock
import mongomock.gridfs
import pytest
from conftest import COLLECTION, DB, doc_url, login
from PIL import Image, ImageDraw
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
from visualizer.akasha.image_processing import ImageProcessor, _is_lossless_webp
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


def _flat_art(size=(900, 600)):
    """Drawn artwork: few colours, hard edges -- the case resampling inflates."""
    image = Image.new("RGB", size, (18, 22, 48))
    draw = ImageDraw.Draw(image)
    draw.polygon([(0, 400), (250, 180), (520, 400)], fill=(60, 70, 110))
    draw.rectangle([300, 150, 600, 560], fill=(48, 52, 74))
    for x in range(330, 580, 60):
        for y in range(200, 480, 90):
            draw.rectangle([x, y, x + 26, y + 44], fill=(250, 190, 90))
    out = BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def test_a_derivative_is_never_larger_than_what_it_derives_from():
    """Flat art resampled to a thumbnail used to cost twice the original."""
    raw = _flat_art()
    processed = ImageProcessor(1_000_000, 1_000_000, 2048, 360).process(raw, "keep.png")
    assert processed.original.data == raw
    for variant in (processed.display, processed.thumbnail):
        assert len(variant.data) <= len(raw)


def _already_optimal_png():
    """Too small to shrink: re-encoding it can only tie, so both derivatives
    are declined and every variant is the upload itself."""
    out = BytesIO()
    Image.new("RGB", (4, 4), (1, 2, 3)).save(out, "PNG", optimize=True)
    return out.getvalue()


def test_a_declined_derivative_falls_back_to_the_original_bytes():
    """Nothing is fabricated: the variant reports the original's real size."""
    raw = _already_optimal_png()
    processed = ImageProcessor(1_000_000, 1_000_000, 2048, 360).process(raw, "dot.png")
    assert processed.display.sha256 == processed.original.sha256
    assert processed.thumbnail.data == raw
    assert (processed.display.width, processed.display.height) == (4, 4)


def test_shared_variant_bytes_are_stored_once(mongo_client):
    store = MediaStore(mongo_client, id_factory=lambda: IMAGE_ID)
    processed = ImageProcessor(1_000_000, 1_000_000, 2048, 360).process(
        _already_optimal_png(), "dot.png"
    )
    store.create("earth", "mara", "Keep", processed.as_asset())
    files = list(mongo_client["_akasha_media"]["blobs.files"].find())
    assert len(files) < 3
    for variant in ("original", "display", "thumbnail"):
        data, _ = store.read_variant("earth", IMAGE_ID, variant)
        assert data


def test_a_lossless_webp_upload_stays_lossless():
    """Pillow's WebP default is lossy q80; on flat art that also inflates it."""
    image = Image.new("RGB", (400, 300), (240, 230, 210))
    ImageDraw.Draw(image).rectangle([50, 50, 350, 250], fill=(200, 60, 40))
    out = BytesIO()
    image.save(out, "WEBP", lossless=True)
    raw = out.getvalue()

    processed = ImageProcessor(1_000_000, 1_000_000, 2048, 360).process(
        raw, "flag.webp"
    )
    display = Image.open(BytesIO(processed.display.data)).convert("RGB")
    assert display.tobytes() == image.tobytes()
    assert len(processed.display.data) <= len(raw)


def test_a_lossy_webp_upload_is_not_re_encoded_as_lossless():
    photo = Image.effect_noise((900, 700), 48).convert("RGB")
    out = BytesIO()
    photo.save(out, "WEBP", quality=80)
    processed = ImageProcessor(5_000_000, 5_000_000, 400, 100).process(
        out.getvalue(), "noise.webp"
    )
    assert (processed.display.width, processed.display.height) == (400, 311)
    assert len(processed.display.data) < len(out.getvalue())


@pytest.mark.parametrize(
    "raw,expected",
    [
        (b"", False),
        (b"RIFF", False),
        (b"RIFF\x00\x00\x00\x00WEBPVP8L", True),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", False),
        (b"RIFF\x00\x00\x00\x00NOPEVP8L", False),
    ],
)
def test_lossless_detection_reads_the_container_not_a_guess(raw, expected):
    assert _is_lossless_webp(raw) is expected


def test_lossless_detection_walks_past_an_extended_header():
    """A VP8X file carries its bitstream after the header and ICC chunks."""
    body = b"VP8X" + (10).to_bytes(4, "little") + b"\x00" * 10
    body += b"ICCP" + (3).to_bytes(4, "little") + b"abc\x00"  # odd size, padded
    body += b"VP8L" + (4).to_bytes(4, "little") + b"data"
    assert _is_lossless_webp(b"RIFF" + b"\x00" * 4 + b"WEBP" + body) is True


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
    created = store.create(DB, "alice", "A map", image.as_asset())
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


def test_orphans_lists_only_what_nothing_points_at(client, media_service):
    client.post(doc_url("atlas"), json={"title": "Atlas"})
    unused = _upload(client, filename="unused.png").get_json()["id"]
    used = _upload(client, filename="used.png").get_json()["id"]
    client.put(
        doc_url("atlas"),
        json={
            "title": "Atlas",
            "body": f"{{{{image:{used}|center|60|In the prose}}}}",
            "gallery": [f"{used}|In the prose"],
        },
    )

    plain = client.get(f"/databases/{DB}/media").get_json()
    assert "orphans" not in plain

    listed = client.get(f"/databases/{DB}/media?orphans=1").get_json()
    assert listed["orphans"] == [unused]


def test_an_image_held_only_by_history_is_not_called_an_orphan(client):
    """It would be listed as removable and then refuse to be removed."""
    client.post(doc_url("atlas"), json={"title": "Atlas"})
    media_id = _upload(client, filename="retired.png").get_json()["id"]
    client.put(
        doc_url("atlas"),
        json={
            "title": "Atlas",
            "body": f"{{{{image:{media_id}|center|60|Once}}}}",
            "gallery": [f"{media_id}|Once"],
        },
    )
    client.put(doc_url("atlas"), json={"title": "Atlas", "body": "The image is gone"})

    listed = client.get(f"/databases/{DB}/media?orphans=1").get_json()
    assert listed["orphans"] == []
    assert client.delete(f"/databases/{DB}/media/{media_id}").status_code == 409


def test_orphans_are_scoped_to_what_the_caller_can_see(app, auth_store, client):
    client.post(doc_url("atlas"), json={"title": "Atlas"})
    _upload(client, filename="secret.png")
    auth_store.create_user("outsider", generate_password_hash("pw"), role="user")
    auth_store.add_grant(
        "outsider", DB, COLLECTION, "atlas", ["read"], granted_by="admin"
    )
    outsider = app.test_client()
    login(outsider, "outsider", "pw")

    listed = outsider.get(f"/databases/{DB}/media?orphans=1").get_json()
    assert listed["orphans"] == []


def test_a_portrait_photo_hangs_the_same_way_up_in_every_variant():
    """Exif rotation is stripped from nothing and reported by everything: the
    lightbox serves the archive, so it must not disagree with the article."""
    exif = Image.Exif()
    exif[274] = 6  # stored landscape, displayed portrait
    exif[271] = "SecretCam"
    out = BytesIO()
    Image.effect_noise((400, 300), 40).convert("RGB").save(out, "JPEG", exif=exif)
    raw = out.getvalue()

    processed = ImageProcessor(1_000_000, 1_000_000, 2048, 360).process(raw, "me.jpg")
    assert (processed.width, processed.height) == (300, 400)
    for variant in (processed.original, processed.display, processed.thumbnail):
        assert variant.width < variant.height, "reported shape is the stored one"
    archived = Image.open(BytesIO(processed.original.data))
    assert archived.getexif().get(274) == 6
    assert archived.getexif().get(271) is None


def test_a_record_written_before_dioramas_still_reads(mongo_client):
    """The live library predates the `kind`/`facts` shape. Both are read; only
    the newer one is written, so an existing world needs no migration."""
    legacy = {
        "_id": IMAGE_ID,
        "world": "earth",
        "uploader": "mara",
        "filename": "corwin.png",
        "alt": "Corwin's profile",
        "format": "PNG",
        "width": 900,
        "height": 600,
        "created_at": "2026-09-08T21:08:57.653336+00:00",
        "variants": {
            "display": {
                "file_id": "f1", "mime_type": "image/png",
                "width": 900, "height": 600, "bytes": 9709, "sha256": "abc",
            }
        },
    }
    mongo_client["_akasha_media"]["media"].insert_one(dict(legacy))

    public = MediaStore(mongo_client).get("earth", IMAGE_ID)
    assert public["kind"] == "image"          # defaulted, not stored
    assert (public["format"], public["width"], public["height"]) == ("PNG", 900, 600)
    assert public["variants"]["display"]["width"] == 900
    assert public["variants"]["display"]["bytes"] == 9709
    assert "file_id" not in public["variants"]["display"]
