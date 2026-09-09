"""HTTP boundary for Akasha's authenticated, world-scoped media library."""

import json
from io import BytesIO

from flask import jsonify, request, send_file, url_for
from flask_login import current_user, login_required

from visualizer.auth import DELETE, READ, WRITE, Forbidden, is_allowed

from .assets import DIORAMA
from .errors import (
    ImageTooLarge,
    InvalidDiorama,
    InvalidImage,
    MediaInUse,
    MediaNotFound,
)
from .media_service import MediaService
from .routing import flag_arg, reject_reserved

_MEDIA = "/databases/<database>/media"
_MEDIA_ITEM = _MEDIA + "/<media_id>"
# Every variant name any kind can carry. An image has the first three, a
# diorama the last two; the content route serves whichever a record holds.
_VARIANTS = ("original", "display", "thumbnail", "model", "poster")


def register_media_routes(app, service: MediaService, auth_store, csrf) -> None:
    @app.get(_MEDIA)
    @login_required
    def list_media(database):
        reject_reserved(database)
        records = service.store.list(database)
        visible = _visible_ids(service, auth_store, database, records)
        shown = records if visible is None else [r for r in records if r["id"] in visible]
        body = {
            "media": [
                _present(r, database, _can_manage(auth_store, database, r))
                for r in shown
            ],
            "count": len(shown),
        }
        if flag_arg("orphans"):
            # Which of these nothing points at any more -- the housekeeping
            # question this feature creates. Scoped to what the caller can
            # already see, so it never discloses an image by omission.
            referenced = service.references.referenced_ids(database)
            body["orphans"] = sorted(
                r["id"] for r in shown if r["id"] not in referenced
            )
        return jsonify(body)

    @app.post(_MEDIA)
    @csrf.exempt
    @login_required
    def upload_media(database):
        reject_reserved(database)
        if (
            request.content_length is not None
            and request.content_length > service.processor.max_bytes + 1024 * 1024
        ):
            raise ImageTooLarge(
                f"An image upload is at most {service.processor.max_bytes} bytes."
            )
        _require_article_write(auth_store, database)
        upload = request.files.get("file")
        if upload is None:
            raise InvalidImage("Choose an image to upload.")
        data = upload.stream.read(service.processor.max_bytes + 1)
        record = service.upload(
            database,
            current_user.username,
            upload.filename,
            data,
            request.form.get("alt"),
        )
        return jsonify(_present(record, database, can_manage=True)), 201

    @app.post(_MEDIA + "/dioramas")
    @csrf.exempt
    @login_required
    def upload_diorama(database):
        reject_reserved(database)
        _require_article_write(auth_store, database)
        model = request.files.get("model")
        if model is None:
            raise InvalidDiorama("Choose a model to upload.")
        cap = service.dioramas.max_bytes if service.dioramas else 0
        data = model.stream.read(cap + 1)
        poster = request.files.get("poster")
        record = service.upload_diorama(
            database,
            current_user.username,
            model.filename,
            data,
            request.form.get("alt"),
            _manifest_field(),
            poster.stream.read(service.processor.max_bytes + 1) if poster else None,
        )
        return jsonify(_present(record, database, can_manage=True)), 201

    @app.put(_MEDIA_ITEM + "/manifest")
    @csrf.exempt
    @login_required
    def replace_manifest(database, media_id):
        """Re-aim a camera without touching the geometry it looks at.

        Two shapes, because there are two callers. A script sends JSON and
        changes only the numbers. The editor sends multipart and includes a
        freshly captured poster, because it has just moved the camera the old
        poster was taken through.
        """
        reject_reserved(database)
        record = service.store.get(database, media_id)
        _require_manager(auth_store, database, record)
        poster = None
        if request.files:
            payload = _manifest_field()
            upload = request.files.get("poster")
            if upload is not None:
                poster = upload.stream.read(service.processor.max_bytes + 1)
        else:
            payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise InvalidDiorama("Provide the manifest as a JSON object.")
        updated = service.update_manifest(database, media_id, payload, poster)
        return jsonify(_present(updated, database, can_manage=True))

    @app.get(_MEDIA_ITEM)
    @login_required
    def get_media(database, media_id):
        reject_reserved(database)
        record = service.store.get(database, media_id)
        _require_visible(service, auth_store, database, record)
        return jsonify(
            _present(record, database, _can_manage(auth_store, database, record))
        )

    @app.patch(_MEDIA_ITEM)
    @csrf.exempt
    @login_required
    def update_media(database, media_id):
        reject_reserved(database)
        record = service.store.get(database, media_id)
        _require_manager(auth_store, database, record)
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise InvalidImage("Provide image metadata as a JSON object.")
        updated = service.update_alt(database, media_id, payload.get("alt"))
        return jsonify(_present(updated, database, can_manage=True))

    @app.delete(_MEDIA_ITEM)
    @csrf.exempt
    @login_required
    def delete_media(database, media_id):
        reject_reserved(database)
        record = service.store.get(database, media_id)
        _require_manager(auth_store, database, record)
        try:
            references = service.delete(database, media_id, force=flag_arg("force"))
        except MediaInUse as error:
            # The library holds two kinds; say which one is being refused.
            noun = "diorama" if record.get("kind") == DIORAMA else "image"
            raise MediaInUse(
                f"This {noun} is still used by an article or retained revision.",
                _readable_references(auth_store, database, error.references),
            ) from None
        return jsonify(
            {
                "deleted": media_id,
                "broken_references": _readable_references(
                    auth_store, database, references
                ),
            }
        )

    @app.get(_MEDIA_ITEM + "/<variant>")
    @login_required
    def media_content(database, media_id, variant):
        reject_reserved(database)
        if variant not in _VARIANTS:
            raise MediaNotFound(f"Image variant '{variant}' does not exist.")
        record = service.store.get(database, media_id)
        _require_visible(service, auth_store, database, record)
        data, details = service.store.read_variant(database, media_id, variant)
        response = send_file(
            BytesIO(data),
            mimetype=details["mime_type"],
            download_name=details["filename"],
            as_attachment=False,
            conditional=True,
            etag=details["sha256"],
        )
        # ``send_file(conditional=True)`` sets ``no-cache``, which would make
        # the browser revalidate every figure on every page view and cancel the
        # max-age below. Clear it: image bytes are immutable (a new upload gets
        # a new id), so they can sit in a private cache for a day. The ETag
        # still gives a cheap 304 once that day is up.
        response.cache_control.no_cache = None
        response.cache_control.private = True
        response.cache_control.max_age = 86400
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response


def _require_article_write(auth_store, database: str) -> None:
    """Every upload is made *for* an article, and needs write access to it.

    Shared by images and dioramas: one rule, one place, so the two upload paths
    cannot drift into two different answers about who may add to a library.
    """
    collection = request.form.get("collection", "").strip()
    article = request.form.get("article", "").strip()
    if not collection or not article:
        raise InvalidImage("An article context is required for an upload.")
    grants = auth_store.grants_for(current_user.username)
    if not is_allowed(grants, WRITE, database, collection, article):
        raise Forbidden("You do not have 'write' permission on this article.")


def _manifest_field() -> dict:
    """The presentation manifest, sent as a JSON field beside the binaries."""
    raw = request.form.get("manifest")
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InvalidDiorama("The presentation manifest is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise InvalidDiorama("The presentation manifest must be an object.")
    return payload


def _present(record: dict, database: str, can_manage: bool) -> dict:
    presented = dict(record)
    presented["can_manage"] = can_manage
    # Only the variants this record actually holds: a diorama has no thumbnail
    # and an image has no model, and a URL for either would be a dead link.
    for variant in record.get("variants", {}):
        presented[f"{variant}_url"] = url_for(
            "media_content", database=database, media_id=record["id"], variant=variant
        )
    return presented


def _visible_ids(service, auth_store, database, records) -> set[str] | None:
    grants = auth_store.grants_for(current_user.username)
    if is_allowed(grants, READ, database, None, None):
        return None
    visible = {r["id"] for r in records if r["uploader"] == current_user.username}
    visible.update(
        service.references.visible_ids(
            database,
            lambda collection, article: is_allowed(
                grants, READ, database, collection, article
            ),
        )
    )
    return visible


def _require_visible(service, auth_store, database, record) -> None:
    if record["uploader"] == current_user.username:
        return
    visible = _visible_ids(service, auth_store, database, [record])
    if visible is not None and record["id"] not in visible:
        raise Forbidden("You do not have 'read' permission on this image.")


def _require_manager(auth_store, database, record) -> None:
    if not _can_manage(auth_store, database, record):
        raise Forbidden("Only the uploader or world owner may manage this image.")


def _can_manage(auth_store, database, record) -> bool:
    if record["uploader"] == current_user.username:
        return True
    grants = auth_store.grants_for(current_user.username)
    return is_allowed(grants, DELETE, database, None, None)


def _readable_references(auth_store, database, references) -> list[dict]:
    grants = auth_store.grants_for(current_user.username)
    return [
        reference
        for reference in references
        if is_allowed(
            grants,
            READ,
            database,
            reference["collection"],
            reference["article"],
        )
    ]


